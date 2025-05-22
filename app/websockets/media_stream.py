"""
WebSocket handlers for Twilio and Ultravox media streaming.
"""
import json
import uuid
import asyncio
import audioop
import base64
import traceback
import websockets
from datetime import datetime
from fastapi import WebSocket, WebSocketDisconnect
from app.utils.websocket_utils import safe_close_websocket
from app.core.config import LOG_EVENT_TYPES
from app.services.n8n_service import send_transcript_to_n8n
from app.services.ultravox_service import create_ultravox_call
from app.core.prompts import SYSTEM_MESSAGE
from app.core.shared_state import sessions
from fastapi import APIRouter
from app.services.n8n_service import send_action_to_n8n

router = APIRouter()

@router.websocket("/media-stream")
async def media_stream(websocket: WebSocket):
    """
    Handles the Twilio <Stream> WebSocket and connects to Ultravox via WebSocket.
    Includes transcoding audio between Twilio's G.711 µ-law and Ultravox's s16 PCM.
    """
    await websocket.accept()
    print('🟢 Client connected to /media-stream (Twilio)')

    call_sid = None
    session = None
    stream_sid = ''
    uv_ws = None
    twilio_task = None
    twilio_ws_active = True
    ultravox_ws_active = False

    async def handle_ultravox():
        printed_name = None
        printed_email = None
        nonlocal uv_ws, session, stream_sid, call_sid, twilio_task, twilio_ws_active, ultravox_ws_active
        try:
            uv_ws.ping_timeout = 10.0
            uv_ws.close_timeout = 5.0

            async for raw_message in uv_ws:
                if session and session.get('hanging_up', False):
                    print("🔴 Ultravox session marked for hangup. Exiting...")
                    break

                if isinstance(raw_message, bytes):
                    try:
                        mu_law_bytes = audioop.lin2ulaw(raw_message, 2)
                        payload_base64 = base64.b64encode(mu_law_bytes).decode('ascii')
                        if twilio_ws_active:
                            await websocket.send_text(json.dumps({
                                "event": "media",
                                "streamSid": stream_sid,
                                "media": { "payload": payload_base64 }
                            }))
                    except Exception as e:
                        print(f"❌ Audio transcoding/sending error: {e}")
                        twilio_ws_active = False
                    continue

                try:
                    msg_data = json.loads(raw_message)
                except Exception:
                    print(f"❌ Invalid JSON from Ultravox: {raw_message}")
                    continue

                msg_type = msg_data.get("type") or msg_data.get("eventType")

                if msg_type == "transcript":
                    role = msg_data.get("role")
                    text = msg_data.get("text") or msg_data.get("delta")
                    final = msg_data.get("final", False)

                    if not role or not text:
                        continue

                    role_cap = role.capitalize()
                    session['transcript'] += f"{role_cap}: {text}\n"
                    lower_text = text.lower().strip()

                    # Print name once
                    if any(p in lower_text for p in ["my name is", "this is", "i'm", "i am"]):
                        name = text.strip()
                        if name != printed_name:
                            session["callerName"] = name
                            printed_name = name
                            print("📩 Name:", name)

                    # Print email once
                    if "@" in text and "." in text:
                        email = text.strip()
                        if email != printed_email:
                            session["callerEmail"] = email
                            printed_email = email
                            print("📧 Email:", email)

                    # Trigger booking
                    if "book" in lower_text and "appointment" in lower_text and not session.get("realtime_payload_sent"):
                        print("📤 Booking intent detected. Sending to N8N...")
                        await send_action_to_n8n(
                            action="book_call",
                            session_id=call_sid,
                            caller_number=session.get("callerNumber"),
                            extra_data={
                                "data": json.dumps({
                                    "name": session.get("callerName", "Unknown"),
                                    "email": session.get("callerEmail", "Unknown"),
                                    "purpose": text,
                                    "datetime": session.get("appointmentTime"),
                                    "calendar_id": session.get("calendar_id", "primary")
                                })
                            }
                        )
                        session["realtime_payload_sent"] = True
                        print("✅ Realtime booking data sent.")

                    if final:
                        emoji = "🤖" if role_cap == "Agent" else "👤"
                        print(f"{emoji} {role_cap}: {text.strip()}")

                elif msg_type == "client_tool_invocation":
                    print(f"🛠️ Tool invoked: {msg_data.get('toolName')} ({msg_data.get('invocationId')})")
                    from app.services.tools_service import handle_tool_invocation
                    await handle_tool_invocation(
                        uv_ws,
                        msg_data.get("toolName", ""),
                        msg_data.get("invocationId"),
                        msg_data.get("parameters", {})
                    )

                elif msg_type == "state":
                    state = msg_data.get("state")
                    print(f"🔄 Agent state: {state}")
                    if state == "ready":
                        invocation_id = str(uuid.uuid4())
                        print("🚀 Agent ready. Checking returning user...")
                        await uv_ws.send(json.dumps({
                            "type": "client_tool_invocation",
                            "toolName": "check_returning_user",
                            "invocationId": invocation_id,
                            "parameters": {
                                "caller_number": session.get("callerNumber", "Unknown")
                            }
                        }))

                elif msg_type == "debug":
                    debug_message = msg_data.get("message")
                    print(f"🐛 Debug: {debug_message}")
                    try:
                        nested = json.loads(debug_message)
                        if nested.get("type") == "toolResult":
                            print(f"✅ Tool '{nested.get('toolName')}' result:", json.dumps(nested.get("output"), indent=2))
                    except json.JSONDecodeError:
                        print(f"⚠️ Couldn't parse debug: {debug_message}")

                elif msg_type in LOG_EVENT_TYPES:
                    print(f"📣 Ultravox event: {msg_type} - {msg_data}")

                elif msg_type != "playback_clear_buffer":
                    print(f"❓ Unknown message type: {msg_type} - {msg_data}")

        except websockets.exceptions.ConnectionClosedError as e:
            print(f"🔌 Ultravox WebSocket closed unexpectedly: {e}")
        except websockets.exceptions.ConnectionClosedOK as e:
            print(f"🔚 Ultravox WebSocket closed normally: {e}")
        except Exception as e:
            print(f"❌ Unhandled error in handle_ultravox: {e}")
            traceback.print_exc()
        finally:
            ultravox_ws_active = False
            if session:
                session['ultravox_ws_active'] = False


    # Define handler for Twilio messages
    async def handle_twilio():
        nonlocal call_sid, session, stream_sid, uv_ws, twilio_ws_active, ultravox_ws_active
        try:
            while True:
                message = await websocket.receive_text()
                data = json.loads(message)

                if data.get('event') == 'start':
                    print("🔔 Twilio 'start' event received")
                    stream_sid = data['start']['streamSid']
                    call_sid = data['start']['callSid']
                    custom_parameters = data['start'].get('customParameters', {})
                    print(f"CallSid: {call_sid}, StreamSid: {stream_sid}")

                    raw_first_message = custom_parameters.get('firstMessage', "Hello, how can I assist you?")
                    first_message = raw_first_message['message']['content'] if isinstance(raw_first_message, dict) and 'message' in raw_first_message else str(raw_first_message)
                    caller_number = custom_parameters.get('callerNumber', 'Unknown')

                    if call_sid and call_sid in sessions:
                        session = sessions[call_sid]
                        session['callerNumber'] = caller_number
                        session['streamSid'] = stream_sid
                        session['transcript'] = ""
                    else:
                        print(f"❌ Session not found for CallSid: {call_sid}")
                        await websocket.close()
                        return

                    print("📞 Caller Number:", caller_number)
                    print("🗨️ First Message:", first_message)

                    from app.core.prompts import SYSTEM_MESSAGE
                    uv_join_url = await create_ultravox_call(
                        system_prompt=SYSTEM_MESSAGE,
                        first_message=first_message,
                        agent_id=caller_number,
                        voice="Tanya-English"
                    )

                    if not uv_join_url:
                        print("❌ Ultravox joinUrl is empty. Aborting call.")
                        await websocket.close()
                        return

                    try:
                        uv_ws = await websockets.connect(
                            uv_join_url,
                            ping_interval=20.0,
                            ping_timeout=10.0,
                            close_timeout=5.0
                        )
                        print("✅ Ultravox WebSocket connected")

                        ultravox_ws_active = True
                        if call_sid and call_sid in sessions:
                            sessions[call_sid]['uv_ws'] = uv_ws
                            sessions[call_sid]['ultravox_ws_active'] = True
                            sessions[call_sid]['twilio_ws_active'] = twilio_ws_active
                    except Exception as e:
                        print(f"❌ Failed to connect Ultravox WebSocket: {e}")
                        traceback.print_exc()
                        twilio_ws_active = False
                        await safe_close_websocket(websocket, name="Twilio WebSocket (connection failure)")
                        return

                    uv_task = asyncio.create_task(handle_ultravox())
                    print("🎯 Ultravox handler task started")

                elif data.get('event') == 'media':
                    payload_base64 = data['media']['payload']
                    try:
                        mu_law_bytes = base64.b64decode(payload_base64)
                    except Exception as e:
                        print(f"❌ Error decoding base64: {e}")
                        continue

                    try:
                        pcm_bytes = audioop.ulaw2lin(mu_law_bytes, 2)
                    except Exception as e:
                        print(f"❌ Error transcoding µ-law to PCM: {e}")
                        continue

                    if ultravox_ws_active and uv_ws and uv_ws.state == websockets.protocol.State.OPEN:
                        try:
                            await uv_ws.send(pcm_bytes)
                        except Exception as e:
                            print(f"❌ Error sending PCM to Ultravox: {e}")
                            ultravox_ws_active = False

        except WebSocketDisconnect:
            print(f"🔌 Twilio WebSocket disconnected (CallSid={call_sid})")
            twilio_ws_active = False

            if ultravox_ws_active and uv_ws and uv_ws.state == websockets.protocol.State.OPEN:
                ultravox_ws_active = False
                if session:
                    session['ultravox_ws_active'] = False
                    session['twilio_ws_active'] = False
                await safe_close_websocket(uv_ws, name="Ultravox WebSocket (Twilio disconnect)")

            if session and not session.get('transcript_sent', False):
                transcript_text = session.get("transcript", "").lower()
                if "dock tour" in transcript_text and "confirmation email" in transcript_text:
                    session["route"] = 3
                    print("🧭 Route set to 3 based on transcript content")
                await send_transcript_to_n8n(session)

        except Exception as e:
            print(f"❌ Error in handle_twilio: {e}")
            traceback.print_exc()

    twilio_task = asyncio.create_task(handle_twilio())
    try:
        await twilio_task
    except asyncio.CancelledError:
        print("🛑 Twilio handler task cancelled")
    finally:
        twilio_ws_active = False
        ultravox_ws_active = False

        if session:
            session['twilio_ws_active'] = False
            session['ultravox_ws_active'] = False

        if uv_ws and uv_ws.state == websockets.protocol.State.OPEN:
            try:
                await safe_close_websocket(uv_ws, name="Ultravox WebSocket (cleanup)")
            except Exception as e:
                print(f"❌ Cleanup error: {e}")

    if session and call_sid:
        if not session.get('realtime_payload_sent', False) and not session.get('transcript_sent', False):
            try:
                transcript_text = session.get("transcript", "").lower()
                if "dock tour" in transcript_text and "confirmation email" in transcript_text:
                    session["route"] = 3
                    print("🧭 Route set to 3 based on transcript content")
                await send_transcript_to_n8n(session)
            except Exception as e:
                print(f"❌ Final transcript send error: {e}")

            print(f"🧹 Cleaning up session for CallSid={call_sid}")
            sessions.pop(call_sid, None)
