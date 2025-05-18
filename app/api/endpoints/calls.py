import json
import requests
import traceback
from datetime import datetime
from twilio.rest import Client
from fastapi import APIRouter, Request, Response
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

def send_action_to_n8n(action, session_id, caller_number, extra_data={}):
    payload = {
        "action": action,
        "callSid": session_id,
        "callerNumber": caller_number,
        "timestamp": datetime.now().isoformat(),
        **extra_data
    }

    try:
        response = requests.post(
            N8N_WEBHOOK_URL,
            headers={"Content-Type": "application/json"},
            json=payload
        )
        print(f"\U0001f4e1 Sent action '{action}' to n8n")
        print("N8N response:", response.text)
    except Exception as e:
        print(f"❌ Error sending to n8n:", e)


@router.get("/")
async def root():
    return {"message": "Twilio + Ultravox Media Stream Server is running!"}


@router.post("/incoming-call")
async def incoming_call(request: Request):
    form_data = await request.form()
    twilio_params = dict(form_data)

    caller_number = twilio_params.get("From", "Unknown")
    session_id = twilio_params.get("CallSid")
    print("Incoming call")
    print("Caller Number:", caller_number)
    print("Session ID (CallSid):", session_id)

    first_message = DEFAULT_FIRST_MESSAGE

    # Save session (firstMessage is sent as a param to MJ, not n8n)
    session = {
        "transcript": "",
        "callerNumber": caller_number,
        "callDetails": twilio_params,
        "firstMessage": first_message,
        "streamSid": None,
        "hanging_up": False,
        "transcript_sent": False,
    }
    sessions[session_id] = session

    # Respond with TwiML to connect to /media-stream
    stream_url = f"{PUBLIC_URL.replace('https', 'wss')}/media-stream"

    twiml_response = f"""<?xml version=\"1.0\" encoding=\"UTF-8\"?>
        <Response>
            <Connect>
                <Stream url=\"{stream_url}\">
                    <Parameter name=\"firstMessage\" value=\"{first_message}\" />
                    <Parameter name=\"callerNumber\" value=\"{caller_number}\" />
                    <Parameter name=\"callSid\" value=\"{session_id}\" />
                </Stream>
            </Connect>
        </Response>"""

    return Response(content=twiml_response, media_type="text/xml")


@router.post("/outgoing-call")
async def outgoing_call(request: Request):
    try:
        data = await request.json()
        phone_number = data.get("phoneNumber")
        first_message = data.get("firstMessage") or DEFAULT_FIRST_MESSAGE

        if not phone_number:
            return {"error": "Phone number is required"}, 400

        print("\U0001f4de Initiating outbound call to:", phone_number)
        print("📝 With the following first message:", first_message)

        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

        call_data = {
            "originalRequest": data,
            "startTime": datetime.now().isoformat(),
        }

        stream_url = f"{PUBLIC_URL.replace('https', 'wss')}/media-stream"

        call = client.calls.create(
            twiml=f'''<Response>
                        <Connect>
                            <Stream url=\"{stream_url}\">
                                <Parameter name=\"firstMessage\" value=\"{first_message}\" />
                                <Parameter name=\"callerNumber\" value=\"{phone_number}\" />
                            </Stream>
                        </Connect>
                    </Response>''',
            to=phone_number,
            from_=TWILIO_PHONE_NUMBER,
            status_callback=f"{PUBLIC_URL}/call-status",
            status_callback_event=["initiated", "ringing", "answered", "completed"]
        )

        print("📱 Twilio call created:", call.sid)

        sessions[call.sid] = {
            "transcript": "",
            "callerNumber": phone_number,
            "callDetails": call_data,
            "firstMessage": first_message,
            "streamSid": None,
            "hanging_up": False,
            "transcript_sent": False,
        }

        return {"success": True, "callSid": call.sid}

    except Exception as error:
        print("❌ Error creating call:", str(error))
        traceback.print_exc()
        return {"error": str(error)}, 500


@router.post("/call-status")
async def call_status(request: Request):
    try:
        data = await request.form()
        print("\n=== 📱 Twilio Status Update ===")
        print("Status:", data.get("CallStatus"))
        print("Duration:", data.get("CallDuration"))
        print("Timestamp:", data.get("Timestamp"))
        print("Call SID:", data.get("CallSid"))
        print("\n====== END ======")

    except Exception as e:
        print(f"Error getting request data: {e}")
        return {"error": str(e)}, 400

    return {"success": True}  # Always acknowledge the webhook