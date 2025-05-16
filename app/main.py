"""
Main FastAPI application entry point.
"""

from fastapi import FastAPI, Request, WebSocket
from fastapi.responses import Response
from app.api.endpoints.calls import router as calls_router
from app.websockets import media_stream
from app.core.config import validate_config
from app.core.shared_state import sessions
import os

# Create FastAPI app instance
app = FastAPI(title="Ultravox Twilio Voice AI")

# Register WebSocket route
app.include_router(media_stream.router)

# Register REST API endpoints
app.include_router(calls_router)

@app.post("/incoming-call")
async def handle_twilio_webhook(request: Request):
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

        # Show raw body for debugging
        raw_body = await request.body()
        print("📦 Raw body:", raw_body.decode())

        # Extract values
        caller_number = form_dict.get("From", "")
        call_sid = form_dict.get("CallSid", "")
        first_message = "Hello"

        # ✅ Pre-create session for the WebSocket to find
        if call_sid and call_sid not in sessions:
            sessions[call_sid] = {
                "callSid": call_sid,
                "callerNumber": caller_number,
                "transcript": "",
                "twilio_ws_active": False,
                "ultravox_ws_active": False,
                "agentId": "1ddb6c91-a9bc-469c-9172-3955807f17f0"
            }

        # Build WebSocket stream URL
        public_url = os.getenv("PUBLIC_URL", "").replace("https://", "")
        stream_url = f"wss://{public_url}/media-stream"
        print("🔗 Final WebSocket URL going to Twilio:", stream_url)

        # Return TwiML response with media stream
        twiml = f"""
        <?xml version="1.0" encoding="UTF-8"?>
        <Response>
            <Connect>
                <Stream url="{stream_url}">
                    <Parameter name="firstMessage" value="{first_message}" />
                    <Parameter name="callerNumber" value="{caller_number}" />
                    <Parameter name="callSid" value="{call_sid}" />
                </Stream>
            </Connect>
        </Response>
        """

        return Response(content=twiml.strip(), media_type="text/xml")

    except Exception as e:
        print("❌ Final error handler triggered:", str(e))
        error_twiml = f"""
        <?xml version="1.0" encoding="UTF-8"?>
        <Response>
            <Say>There was an internal error. Please try again later.</Say>
        </Response>
        """
        return Response(content=error_twiml.strip(), media_type="text/xml", status_code=500)

# Validate config on startup
@app.on_event("startup")
async def startup_event():
    validate_config()
    print("✅ Config validated. Server ready.")
