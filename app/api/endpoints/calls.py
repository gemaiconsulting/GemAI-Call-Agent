"""
API endpoints for handling Twilio calls.
"""
import json
import requests
from datetime import datetime
from twilio.rest import Client
import traceback
from fastapi import APIRouter, Request, Response
from xml.sax.saxutils import escape
from app.core.shared_state import sessions
from app.core.config import (
    PUBLIC_URL,
    DEFAULT_FIRST_MESSAGE,
    TWILIO_ACCOUNT_SID,
    TWILIO_AUTH_TOKEN,
    TWILIO_PHONE_NUMBER,
    N8N_WEBHOOK_URL,
)

router = APIRouter()

# 🔍 Fetch initial greeting message from N8N
async def get_first_message_from_n8n(caller_number: str) -> str:
    print("\n📨 get_first_message_from_n8n() called with:", caller_number)
    try:
        print("🔁 Sending POST to n8n (route: 1)...")
        webhook_response = requests.post(
            N8N_WEBHOOK_URL,
            headers={"Content-Type": "application/json"},
            json={
                "route": "1",
                "number": caller_number,
                "data": "empty"
            }
        )
        print("🌐 N8N webhook response status:", webhook_response.status_code)

        if webhook_response.ok:
            response_text = webhook_response.text
            print("📨 Raw response from N8N:", response_text)

            try:
                response_data = json.loads(response_text)
                print("✅ Parsed JSON from N8N:", response_data)

                if response_data.get('firstMessage'):
                    fm = response_data['firstMessage']
                    print("🔎 Detected firstMessage:", fm)

                    if isinstance(fm, list) and len(fm) > 0 and isinstance(fm[0], dict):
                        msg = fm[0].get("message", {})
                        content = msg.get("content")
                        if content:
                            print("✅ Extracted content from n8n list format:", content)
                            return content

                    elif isinstance(fm, dict) and 'message' in fm:
                        content = fm['message'].get('content')
                        if content:
                            print("✅ Extracted content from n8n object format:", content)
                            return content

                    print("⚠️ Unexpected 'firstMessage' format. Fallback to raw:", fm)
                    return str(fm)

            except json.JSONDecodeError as je:
                print("❌ JSON decoding failed:", je)
                return response_text.strip()
        else:
            print("❌ N8N webhook failed:", webhook_response.status_code, webhook_response.text)

    except Exception as e:
        print("❌ Exception while calling N8N webhook:", e)

    print("🔁 Falling back to DEFAULT_FIRST_MESSAGE.")
    return DEFAULT_FIRST_MESSAGE


@router.get("/")
async def root():
    print("📡 GET / called — health check OK")
    return {"message": "Twilio + Ultravox Media Stream Server is running!"}


@router.post("/incoming-call")
async def incoming_call(request: Request):
    try:
        print("🟡 [Webhook Hit] POST /incoming-call")

        try:
            content_type = request.headers.get("content-type", "")
            if "application/json" in content_type:
                data = await request.json()
                print("📦 Parsed JSON data:", data)
            else:
                form_data = await request.form()
                data = dict(form_data)
                print("📞 Parsed form data:", data)
        except Exception as e:
            print("❌ Failed to parse request:", e)
            data = {}

        # Use `data` instead of `form_dict`
        caller_number = data.get("From", "Unknown")
        call_sid = data.get("CallSid", "Unknown")

        # Fetch first message
        first_message = await get_first_message_from_n8n(caller_number)
        print("💬 First Message returned from N8N handler:", first_message)

        # Create session
        if call_sid and call_sid not in sessions:
            sessions[call_sid] = {
                "callSid": call_sid,
                "callerNumber": caller_number,
                "transcript": "",
                "twilio_ws_active": False,
                "ultravox_ws_active": False,
                "firstMessage": first_message,
                "transcript_sent": False
            }
            print(f"📦 Session created for CallSid: {call_sid}")

        stream_url = f"{PUBLIC_URL.replace('https', 'wss')}/media-stream"
        print("🔗 WebSocket stream URL:", stream_url)

        from xml.sax.saxutils import escape
        escaped_first_message = escape(str(first_message))

        # Respond with TwiML
        twiml = f"""
        <?xml version="1.0" encoding="UTF-8"?>
        <Response>
            <Connect>
                <Stream url="{stream_url}">
                    <Parameter name="firstMessage" value="{escaped_first_message}" />
                    <Parameter name="callerNumber" value="{caller_number}" />
                    <Parameter name="callSid" value="{call_sid}" />
                </Stream>
            </Connect>
        </Response>
        """
        print("✅ Returning TwiML response.")
        return Response(content=twiml.strip(), media_type="application/xml")

    except Exception as e:
        print("❌ Fatal error in /incoming-call route:", e)
        traceback.print_exc()

        error_twiml = f"""
        <?xml version="1.0" encoding="UTF-8"?>
        <Response>
            <Say>There was an internal error. Please try again later.</Say>
        </Response>
        """
        return Response(content=error_twiml.strip(), media_type="text/xml", status_code=500)



@router.post("/call-status")
async def call_status(request: Request):
    print("\n📞 POST /call-status triggered")

    try:
        data = await request.form()
        print('=== 📱 Twilio Status Update ===')
        print('📍 Call Status:', data.get('CallStatus'))
        print('⏱️ Call Duration:', data.get('CallDuration'))
        print('🕒 Timestamp:', data.get('Timestamp'))
        print('📌 Call SID:', data.get('CallSid'))
        print('====== END ======\n')

    except Exception as e:
        print(f"❌ Exception in /call-status handler: {e}")
        return {"error": str(e)}, 400

    return {"success": True}
