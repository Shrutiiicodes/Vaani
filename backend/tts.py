import base64, io
from gtts import gTTS
from typing import Optional

LANGUAGE_CODES = {
    "hindi": "hi", "tamil": "ta", "telugu": "te",
    "marathi": "mr", "bengali": "bn", "gujarati": "gu",
    "kannada": "kn", "odia": "or", "english": "en"
}

def is_supported_language(language: str) -> bool:
    return language.lower() in LANGUAGE_CODES

def text_to_speech_base64(text: str, language: str) -> Optional[str]:
    """Return base64 MP3, or None if the language isn't supported (no silent fallback)."""
    lang_code = LANGUAGE_CODES.get(language.lower())
    if lang_code is None:
        return None
    tts = gTTS(text=text, lang=lang_code, slow=False)
    buffer = io.BytesIO()
    tts.write_to_fp(buffer)
    buffer.seek(0)
    return base64.b64encode(buffer.read()).decode("utf-8")