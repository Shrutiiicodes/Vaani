from pydantic import BaseModel
from typing import Optional

class TranslateRequest(BaseModel):
    text: str
    source_language: str
    target_language: str = "english"

class TranslateResponse(BaseModel):
    translated_text: str
    detected_intent: str
    process_guide: list[str]
    confidence: float

class StaffReplyRequest(BaseModel):
    reply_text: str
    target_language: str

class StaffReplyResponse(BaseModel):
    translated_reply: str
    audio_base64: str

class SummaryRequest(BaseModel):
    conversation: list[dict]  # [{role, text, language}]
    customer_language: str

class SummaryResponse(BaseModel):
    english_summary: str
    vernacular_summary: str