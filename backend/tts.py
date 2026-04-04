import base64, io
from gtts import gTTS

LANGUAGE_CODES = {
    "hindi": "hi", "tamil": "ta", "telugu": "te",
    "marathi": "mr", "bengali": "bn", "gujarati": "gu",
    "kannada": "kn", "odia": "or", "english": "en"
}

def text_to_speech_base64(text: str, language: str) -> str:
    """Convert text to speech, return base64 encoded MP3."""
    lang_code = LANGUAGE_CODES.get(language.lower(), "hi")
    tts = gTTS(text=text, lang=lang_code, slow=False)
    buffer = io.BytesIO()
    tts.write_to_fp(buffer)
    buffer.seek(0)
    return base64.b64encode(buffer.read()).decode("utf-8")