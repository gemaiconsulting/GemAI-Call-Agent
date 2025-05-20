"""
API endpoints for handling Twilio calls.
"""
import json
import requests
from datetime import datetime
from twilio.rest import Client
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

async def get_first_message_from_n8n(caller_number: str) -> str:
    try:
        print("🔁 Sending to n8n for personalization (route: 1)...")
        webhook_response = requests.post(
            N8N_WEBHOOK_URL,
            headers={"Content-Type": "application/json"},
            json={
                "route": "1",
                "number": caller_number,
                "data": "empty"
            }
        )

        if webhook_response.ok:
            response_text = webhook_response.text
            try:
                response_data = json.loads(response_text)
                if response_data.get('firstMessage'):
                    fm = response_data['firstMessage']

            # Handle list format (most common from n8n)
                    if isinstance(fm, list) and len(fm) > 0 and isinstance(fm[0], dict):
                        msg = fm[0].get("message", {})
                        content = msg.get("content")
                        if content:
                            print("✅ Extracted content from n8n list format:", content)
                            return content

            # Handle direct object format
                    elif isinstance(fm, dict) and 'message' in fm:
                        content = fm['message'].get('content')
                        if content:
                            print("✅ Extracted content from n8n object format:", content)
                            return content

            # Fallback
                    print("⚠️ Unexpected format. Returning raw:", fm)
                    return str(fm)
            except json.JSONDecodeError:
                print("⚠️ Could not parse n8n JSON. Using raw string.")
                return response_text.strip()
        else:
            print("❌ N8N webhook failed:", webhook_response.status_code)

    except Exception as e:
         print("❌ Error calling n8n webhook:", e)

    return DEFAULT_FIRST_MESSAGE




@router.get("/")
async def root():
    return {"message": "Twilio + Ultravox Media Stream Server is running!"}


@router.post("/incoming-call")
async def incoming_call(request: Request):
    try:
        print("🟡 [Webhook Hit] POST /incoming-call")

        # Parse form data
        try:
            form_data = await request.form()
            form_dict = dict(form_data)
            print("📞 Parsed form data:", form_dict)
        except Exception as fe:
            print("⚠️ Could not parse form data:", str(fe))
            form_dict = {}



        # Extract values
        caller_number = form_dict.get("From", "Unknown")
        call_sid = form_dict.get("CallSid", "Unknown")
        first_message = await get_first_message_from_n8n(caller_number)


        # ✅ Pre-create session for media-stream to find
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

        # Build WebSocket stream URL
        stream_url = f"{PUBLIC_URL.replace('https', 'wss')}/media-stream"
        print("🔗 WebSocket stream URL:", stream_url)
        
        # Escape special XML characters in the first_message
        escaped_first_message = escape(str(first_message))


        # Return TwiML
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
        return Response(content=twiml.strip(), media_type="text/xml")

    except Exception as e:
        print("❌ Error in incoming_call:", str(e))
        error_twiml = f"""
        <?xml version="1.0" encoding="UTF-8"?>
        <Response>
            <Say>There was an internal error. Please try again later.</Say>
        </Response>
        """
        return Response(content=error_twiml.strip(), media_type="text/xml", status_code=500)


@router.post("/call-status")
async def call_status(request: Request):
    try:
        data = await request.form()
        print('\n=== 📱 Twilio Status Update ===')
        print('Status:', data.get('CallStatus'))
        print('Duration:', data.get('CallDuration'))
        print('Timestamp:', data.get('Timestamp'))
        print('Call SID:', data.get('CallSid'))
        print('====== END ======\n')

    except Exception as e:
        print(f"Error in call-status handler: {e}")
        return {"error": str(e)}, 400

    return {"success": True}
