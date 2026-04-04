from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from models import StaffReplyRequest, SummaryRequest
from stt import transcribe_audio
from translate import translate_customer_speech, translate_staff_reply, translate_text, generate_summary
from tts import text_to_speech_base64
from banking_context import COUNTERS
import json

app = FastAPI(title="PS6 Voice Assistant")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)


# ── Route 1: Customer speaks → transcribe + translate + intent ──
@app.post("/api/customer-speak")
async def customer_speak(
    audio: UploadFile = File(...), 
    conversation: str = Form("[]"),
    active_form: str = Form(None)  # pass the current open form type
):
    try:
        audio_bytes = await audio.read()
        convo_history = json.loads(conversation)

        # Step 1: STT
        stt_result = await transcribe_audio(audio_bytes)
        detected_lang = stt_result.get("language") or "hindi"
        raw_text = stt_result.get("text") or ""

        # Step 2: Translate + intent + entities + counters + calculations
        data = await translate_customer_speech(raw_text, detected_lang, convo_history, active_form)

        response_payload = {
            "original_text":       raw_text,
            "detected_language":   detected_lang,
            "english_translation": data["english_translation"],
            "intent":              data["intent"],
            "process_guide":       data["process_guide"],
            "confidence":          data["confidence"],
            "suggested_counter":   data.get("suggested_counter"),
            "counter_name":        COUNTERS.get(data.get("suggested_counter"), "Inquiry Desk"),
            "entities":            data.get("entities", {}),
            "form_template":       data.get("form_template"),
            "calculation_results": data.get("calculation_results"),
            "needs_clarification": data.get("needs_clarification", False),
            "follow_up_question":  data.get("follow_up_question"),
            "follow_up_audio":     None,
            "calculation_tts_audio": None,
        }

        # Step 3: Handle Clarification
        if data.get("needs_clarification") and data.get("follow_up_question"):
            q_english = data["follow_up_question"]
            q_translated = await translate_text(q_english, detected_lang)
            response_payload["follow_up_question_translated"] = q_translated
            response_payload["follow_up_audio"] = text_to_speech_base64(q_translated, detected_lang)

        # Step 4: Handle Calculations TTS
        calc_res = data.get("calculation_results")
        if calc_res and calc_res.get("type") != "none":
            tts_text_en = ""
            if calc_res["type"] == "emi" and "emi" in calc_res:
                tts_text_en = f"Your monthly EMI will be ₹{calc_res['emi']}. Total payment will be ₹{calc_res['total_payment']}."
            elif calc_res["type"] == "fd" and "maturity" in calc_res:
                tts_text_en = f"At maturity, your FD will be worth ₹{calc_res['maturity']}. Interest earned is ₹{calc_res['interest_earned']}."
            elif calc_res["type"] == "rd" and "maturity" in calc_res:
                tts_text_en = f"At maturity, your RD will be worth ₹{calc_res['maturity']}. Interest earned is ₹{calc_res['interest_earned']}."
            elif calc_res["type"] == "eligibility" and "max_loan" in calc_res:
                tts_text_en = f"Your max eligible loan amount is ₹{calc_res['max_loan']}. Your suggested EMI limit is ₹{calc_res['suggested_emi_limit']}."

            if tts_text_en:
                tts_text_vern = await translate_text(tts_text_en, detected_lang)
                response_payload["calculation_tts_audio"] = text_to_speech_base64(tts_text_vern, detected_lang)

        return response_payload

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Route 2: Staff replies → translate back + TTS ──
@app.post("/api/staff-reply")
async def staff_reply(request: StaffReplyRequest):
    try:
        translated = await translate_staff_reply(
            request.reply_text, request.target_language
        )
        audio_b64 = text_to_speech_base64(translated, request.target_language)
        return {
            "translated_reply": translated,
            "audio_base64":     audio_b64
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Route 3: Generate session summary ──
@app.post("/api/summary")
async def session_summary(request: SummaryRequest):
    try:
        summary = await generate_summary(
            request.conversation, request.customer_language
        )
        return summary
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


import os
frontend_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "frontend")

@app.get("/")
async def serve_index():
    return FileResponse(os.path.join(frontend_dir, "index.html"))

app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")