import os

from dotenv import load_dotenv
from groq import AsyncGroq

from banking_context import LANGUAGES

load_dotenv()
client = AsyncGroq(api_key=os.getenv("GROQ_API_KEY", ""))

_CODE_TO_NAME = {code: name for name, code in LANGUAGES.items()}


async def transcribe_audio(audio_bytes: bytes, filename: str = "audio.webm",
                           language: str | None = None) -> dict:
    """Transcribe with Groq Whisper. `language` is an optional ISO-639-1 hint.

    Returns {"text", "language"} where language is a lowercase name like "hindi".
    """
    kwargs = {"language": language} if language else {}
    response = await client.audio.transcriptions.create(
        model="whisper-large-v3",
        file=(filename, audio_bytes),       # extension tells Whisper the container format
        response_format="verbose_json",     # includes language detection
        **kwargs,
    )
    detected = (getattr(response, "language", None) or "").lower()
    return {
        "text": response.text,
        "language": detected or _CODE_TO_NAME.get(language or "", ""),
    }
