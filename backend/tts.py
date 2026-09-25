import asyncio
import base64
import io
import logging
import os

import edge_tts
from gtts import gTTS

from banking_context import LANGUAGES
from cache import async_cache

log = logging.getLogger("vaani")

# edge-tts sounds far better but measured ~1s slower than gTTS per reply; "gtts" trades quality for speed.
ENGINE = os.getenv("TTS_ENGINE", "edge")

# Microsoft neural voices (via edge-tts). Odia has no voice in edge-tts or gTTS.
VOICES = {
    "hindi": "hi-IN-SwaraNeural",
    "tamil": "ta-IN-PallaviNeural",
    "telugu": "te-IN-ShrutiNeural",
    "marathi": "mr-IN-AarohiNeural",
    "bengali": "bn-IN-TanishaaNeural",
    "gujarati": "gu-IN-DhwaniNeural",
    "kannada": "kn-IN-SapnaNeural",
    "english": "en-IN-NeerjaNeural",
}


def is_supported_language(language: str) -> bool:
    return (language or "").lower() in VOICES


async def _edge(text: str, voice: str) -> bytes:
    audio = b""
    async for chunk in edge_tts.Communicate(text, voice).stream():
        if chunk["type"] == "audio":
            audio += chunk["data"]
    return audio


def _gtts(text: str, lang_code: str) -> bytes:
    buffer = io.BytesIO()
    gTTS(text=text, lang=lang_code, slow=False).write_to_fp(buffer)
    return buffer.getvalue()


@async_cache(maxsize=256)
async def text_to_speech_base64(text: str, language: str) -> str | None:
    """Base64 MP3, or None if the language has no voice or both engines fail.

    edge-tts first (better voices, async); gTTS in a thread as the fallback.
    Never raises: a missing voice must not fail the whole request.
    """
    language = (language or "").lower()
    voice = VOICES.get(language)
    if not voice or not text:
        return None
    try:
        audio = await _edge(text, voice) if ENGINE == "edge" else b""
        if audio:
            return base64.b64encode(audio).decode()
    except Exception as e:
        log.warning("edge-tts failed, falling back to gTTS", extra={"fields": {"error": repr(e)}})
    try:
        audio = await asyncio.to_thread(_gtts, text, LANGUAGES[language])
        return base64.b64encode(audio).decode()
    except Exception:
        log.exception("gTTS failed")
        return None
