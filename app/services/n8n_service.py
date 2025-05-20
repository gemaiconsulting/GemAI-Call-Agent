"""
Services for handling webhook communications.
"""
import json
import httpx
import asyncio
from app.core.config import N8N_WEBHOOK_URL

MAX_RETRIES = 3
RETRY_DELAY = 1.5  # seconds


async def send_transcript_to_n8n(session):
    print("📝 Full Transcript:\n", session['transcript'])
    await send_to_webhook({
        "route": "2",
        "number": session.get("callerNumber", "Unknown"),
        "data": session["transcript"]
    })
    session['transcript_sent'] = True


async def send_to_webhook(payload: dict) -> str:
    if not N8N_WEBHOOK_URL:
        error_msg = "❌ N8N_WEBHOOK_URL not set in environment"
        print(error_msg)
        return json.dumps({"error": error_msg})

    attempt = 0
    while attempt < MAX_RETRIES:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    N8N_WEBHOOK_URL,
                    json=payload,
                    headers={"Content-Type": "application/json"}
                )
                if response.status_code == 200:
                    print(f"✅ N8N webhook call success (attempt {attempt + 1})")
                    return response.text
                else:
                    print(f"⚠️ N8N webhook returned {response.status_code}: {response.text}")
        except httpx.RequestError as e:
            print(f"❌ Request error on attempt {attempt + 1}: {e}")
        except Exception as e:
            print(f"❌ Unexpected error on attempt {attempt + 1}: {e}")

        attempt += 1
        print(f"⏳ Retrying in {RETRY_DELAY} seconds... (attempt {attempt + 1}/{MAX_RETRIES})")
        await asyncio.sleep(RETRY_DELAY)

    return json.dumps({"error": f"Failed to reach N8N webhook after {MAX_RETRIES} attempts"})



async def send_action_to_n8n(action: str, session_id: str, caller_number: str, extra_data: dict = None):
    payload = {
        "route": "3",
        "action": action,
        "session_id": session_id,
        "caller_number": caller_number,
    }

    if extra_data:
        payload.update(extra_data)

    response = await send_to_webhook(payload)
    print(f"📡 Action sent to N8N: {action}, response: {response}")
    return response
