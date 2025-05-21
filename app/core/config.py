"""
Application configuration settings with detailed debug logs.
"""
import os
from dotenv import load_dotenv

print("📦 Loading environment variables from .env file...")
load_dotenv(override=True)
print("✅ .env loaded.\n")

# Twilio credentials
TWILIO_ACCOUNT_SID = os.environ.get('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN = os.environ.get('TWILIO_AUTH_TOKEN')
TWILIO_PHONE_NUMBER = os.environ.get('TWILIO_PHONE_NUMBER')

print("🔐 Twilio Config:")
print("  - TWILIO_ACCOUNT_SID:", "✅ Loaded" if TWILIO_ACCOUNT_SID else "❌ MISSING")
print("  - TWILIO_AUTH_TOKEN:", "✅ Loaded" if TWILIO_AUTH_TOKEN else "❌ MISSING")
print("  - TWILIO_PHONE_NUMBER:", TWILIO_PHONE_NUMBER or "❌ MISSING")

# Ultravox credentials
ULTRAVOX_API_KEY = os.environ.get('ULTRAVOX_API_KEY')
ULTRAVOX_MODEL = "fixie-ai/ultravox-70B"
ULTRAVOX_VOICE = "Matthew-English"   # or "Mark"
ULTRAVOX_SAMPLE_RATE = 8000        
ULTRAVOX_BUFFER_SIZE = 60

print("\n🔊 Ultravox Config:")
print("  - ULTRAVOX_API_KEY:", "✅ Loaded" if ULTRAVOX_API_KEY else "❌ MISSING")
print("  - ULTRAVOX_MODEL:", ULTRAVOX_MODEL)
print("  - ULTRAVOX_VOICE:", ULTRAVOX_VOICE)
print("  - ULTRAVOX_SAMPLE_RATE:", ULTRAVOX_SAMPLE_RATE)
print("  - ULTRAVOX_BUFFER_SIZE:", ULTRAVOX_BUFFER_SIZE)

# Webhooks
N8N_WEBHOOK_URL = os.environ.get('N8N_WEBHOOK_URL')
PUBLIC_URL = os.environ.get('PUBLIC_URL')

print("\n🔗 Webhook URLs:")
print("  - N8N_WEBHOOK_URL:", N8N_WEBHOOK_URL or "❌ MISSING")
print("  - PUBLIC_URL:", PUBLIC_URL or "❌ MISSING")

# Server settings
PORT = int(os.environ.get('PORT', '8000'))
print("\n⚙️ Server Port:", PORT)

# Default greeting
DEFAULT_FIRST_MESSAGE = "Hey, this is Sarah from Admiral. How can I assist you today?"
print("🗨️ Default First Message:", DEFAULT_FIRST_MESSAGE)

# Calendar mappings
CALENDARS_LIST = {
    "LOCATION1": "CALENDAR_EMAIL1",
    "LOCATION2": "CALENDAR_EMAIL2",
    "LOCATION3": "CALENDAR_EMAIL3",
    # Add more locations / Calendar IDs as needed
}
print("\n📅 Calendar Configs:")
for loc, cal in CALENDARS_LIST.items():
    print(f"  - {loc}: {cal}")

# Logging event types
LOG_EVENT_TYPES = [
    'response.content.done',
    'response.done',
    'session.created',
    'conversation.item.input_audio_transcription.completed'
]
print("\n📋 Log Event Types:", LOG_EVENT_TYPES)


# Validation function
def validate_config():
    """Validate that all required configuration variables are set."""
    print("\n🧪 Validating configuration...")

    if not all([TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER]):
        print("⚠️ WARNING: Missing Twilio credentials! Please check your .env file.")
    
    if not ULTRAVOX_API_KEY:
        print("⚠️ WARNING: Missing Ultravox API key! Please check your .env file.")
    
    if not N8N_WEBHOOK_URL:
        print("⚠️ WARNING: Missing N8N webhook URL! Please check your .env file.")
    else:
        print("✅ All required configs seem to be present.")

