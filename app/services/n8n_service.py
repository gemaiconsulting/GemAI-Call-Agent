"""
Services for handling webhook communications with detailed logging.
"""
import json
import httpx
import asyncio
from app.core.config import N8N_WEBHOOK_URL

MAX_RETRIES = 3
RETRY_DELAY = 1.5  # seconds


def detect_route(session: dict) -> int:
    """
    Detects the correct route to use in the webhook payload.
    Priority:
    1. Use session["route"] if explicitly set
    2. Default to 2 if nothing is defined
    """
    if "route" in session and isinstance(session["route"], int):
        return session["route"]
    return 2  # Default fallback route


async def send_transcript_to_n8n(session):
    print("\n📝 send_transcript_to_n8n() called")
    caller_number = session.get("callerNumber", "Unknown")
    transcript = session.get("transcript", "")
    route = detect_route(session)

    print(f"📞 Caller Number: {caller_number}")
    print(f"🧭 Selected Route: {route}")

    payload = {
        "route": route,
        "number": caller_number,
        "data": transcript
    }

    await send_to_webhook(payload)
    session['transcript_sent'] = True
    print("✅ Transcript sent flag updated in session")


async def send_to_webhook(payload: dict) -> str:
    print("\n📨 send_to_webhook() called with payload:")
    print(json.dumps(payload, indent=2))

    if not N8N_WEBHOOK_URL:
        error_msg = "❌ N8N_WEBHOOK_URL not set in environment"
        print(error_msg)
        return json.dumps({"error": error_msg})

    attempt = 0
    while attempt < MAX_RETRIES:
        print(f"🌐 Attempting to call webhook (Attempt {attempt + 1}/{MAX_RETRIES})")
        print(f"🔗 URL: {N8N_WEBHOOK_URL}")
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    N8N_WEBHOOK_URL,
                    json=payload,
                    headers={"Content-Type": "application/json"}
                )

                print(f"🔄 Webhook Response Code: {response.status_code}")
                print("📥 Response Body:", response.text)

                if response.status_code == 200:
                    print("✅ N8N webhook call successful")
                    return response.text
                else:
                    print(f"⚠️ Non-200 response: {response.status_code}")

        except httpx.RequestError as e:
            print(f"❌ RequestError on attempt {attempt + 1}: {str(e)}")
        except Exception as e:
            print(f"❌ Unexpected error on attempt {attempt + 1}: {str(e)}")

        attempt += 1
        if attempt < MAX_RETRIES:
            print(f"⏳ Retrying in {RETRY_DELAY} seconds... (Next Attempt: {attempt + 1})")
            await asyncio.sleep(RETRY_DELAY)

    error_summary = f"❌ Failed to reach N8N webhook after {MAX_RETRIES} attempts"
    print(error_summary)
    return json.dumps({"error": error_summary})


async def send_action_to_n8n(action: str, session_id: str, caller_number: str, extra_data: dict = None):
    print(f"\n🚀 send_action_to_n8n() triggered")
    print(f"🔧 Action: {action}")
    print(f"🧾 Session ID: {session_id}")
    print(f"📞 Caller Number: {caller_number}")
    if extra_data:
        print("📦 Extra Data:", json.dumps(extra_data, indent=2))

    payload = {
        "route": 3,
        "action": action,
        "session_id": session_id,
        "caller_number": caller_number,
    }

    if extra_data:
        payload.update(extra_data)

    print("📨 Final Payload to N8N:", json.dumps(payload, indent=2))
    response = await send_to_webhook(payload)
    print(f"📡 N8N responded to action '{action}': {response}")
    return response
