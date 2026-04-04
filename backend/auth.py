import os
from fastapi import Header, HTTPException
from dotenv import load_dotenv

load_dotenv()

STAFF_API_KEY = os.getenv("STAFF_API_KEY", "")

async def verify_api_key(x_api_key: str = Header(...)):
    """FastAPI dependency — checks X-Api-Key header on every protected route."""
    if not STAFF_API_KEY:
        raise HTTPException(status_code=500, detail="Server API key not configured")
    if x_api_key != STAFF_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")