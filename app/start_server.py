"""
Entry point for launching the FastAPI server.
"""

import uvicorn
from app.main import app
from app.core.config import PORT

if __name__ == "__main__":
    print(f"🚀 Starting Ultravox Voice AI Server on port {PORT}...")
    uvicorn.run("app.main:app", host="0.0.0.0", port=PORT)