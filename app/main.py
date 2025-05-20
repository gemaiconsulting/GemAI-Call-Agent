"""
Main FastAPI application entry point.
"""
import uvicorn
from fastapi import FastAPI
from app.api.endpoints.calls import router as calls_router
from app.websockets import media_stream
from app.core.config import validate_config

# Create FastAPI app instance
app = FastAPI(title="Ultravox Twilio Voice AI")

# Register WebSocket route
app.include_router(media_stream.router)

# Register REST API endpoints
app.include_router(calls_router)

# Validate config on startup
@app.on_event("startup")
async def startup_event():
    validate_config()
    print("✅ Config validated. Server ready.")

if __name__ == "__main__":
    import os
    port = int(os.getenv("PORT", "8000"))
    print(f"Starting server on port {port}...")
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=True)