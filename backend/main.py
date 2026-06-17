from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from stt import transcribe_audio
from translate import translate_customer_speech, translate_staff_reply, translate_text, generate_summary
from tts import text_to_speech_base64
from banking_context import COUNTERS
from database import init_db
from crud import get_db, get_or_create_session, add_turn, get_turns, update_session_language
import json
import os
from auth import verify_token, create_access_token, verify_staff_password, revoke_token
from models import StaffReplyRequest, SummaryRequest, LoginRequest
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()      # runs on startup
    yield          # app runs here
    # anything after yield runs on shutdown

app = FastAPI(title="PS6 Voice Assistant", lifespan=lifespan)
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler) # type: ignore[arg-type]

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)

# ── Route 1: Customer speaks → transcribe + translate + intent ──
@app.post("/api/customer-speak")
@limiter.limit("20/minute")
async def customer_speak(
    request: Request,
    audio: UploadFile = File(...),
    conversation: str = Form("[]"),
    active_form: str = Form(None),
    session_id: str = Form(None),
    db: Session = Depends(get_db),
    _: dict = Depends(verify_token)
):
    try:
        audio_bytes = await audio.read()

        # ── Use DB history if session_id present, else fall back to frontend-sent history ──
        if session_id:
            get_or_create_session(db, session_id)
            convo_history = get_turns(db, session_id)
        else:
            convo_history = json.loads(conversation)

        # Step 1: STT
        stt_result = await transcribe_audio(audio_bytes)
        detected_lang = stt_result.get("language") or "hindi"
        raw_text = stt_result.get("text") or ""

        # Update language on the session record
        if session_id:
            update_session_language(db, session_id, detected_lang)

        # Step 2: Translate + intent + entities + counters + calculations
        data = await translate_customer_speech(raw_text, detected_lang, convo_history, active_form)

        # ── Persist the customer turn ──
        if session_id:
            add_turn(
                db,
                session_id=session_id,
                role="customer",
                original=raw_text,
                translated=data["english_translation"],
                language=detected_lang,
                intent=data.get("intent"),
                confidence=data.get("confidence"),
                entities=data.get("entities", {})
            )

        response_payload = {
            "original_text":         raw_text,
            "detected_language":     detected_lang,
            "english_translation":   data["english_translation"],
            "intent":                data["intent"],
            "process_guide":         data["process_guide"],
            "confidence":            data["confidence"],
            "suggested_counter":     data.get("suggested_counter"),
            "counter_name":          COUNTERS.get(data.get("suggested_counter") or "inquiry_desk", "Inquiry Desk"),
            "entities":              data.get("entities", {}),
            "form_template":         data.get("form_template"),
            "calculation_results":   data.get("calculation_results"),
            "needs_clarification":   data.get("needs_clarification", False),
            "follow_up_question":    data.get("follow_up_question"),
            "follow_up_audio":       None,
            "calculation_tts_audio": None,
        }

        # Step 3: Handle Clarification TTS
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


# ── Route 2: Staff replies → translate back + TTS + persist ──
@app.post("/api/staff-reply")
async def staff_reply(
    request: StaffReplyRequest,
    db: Session = Depends(get_db),
    _: dict = Depends(verify_token)
):
    try:
        translated = await translate_staff_reply(
            request.reply_text, request.target_language
        )
        audio_b64 = text_to_speech_base64(translated, request.target_language)

        # ── Persist staff turn if session_id was sent ──
        if request.session_id:
            add_turn(
                db,
                session_id=request.session_id,
                role="staff",
                original=request.reply_text,
                translated=translated,
                language="english"
            )

        return {
            "translated_reply": translated,
            "audio_base64":     audio_b64
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Route 3: Generate session summary ──
@app.post("/api/summary")
async def session_summary(request: SummaryRequest, _: dict = Depends(verify_token)):
    try:
        summary = await generate_summary(
            request.conversation, request.customer_language
        )
        return summary
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Route 4: Restore session history (called on page load/refresh) ──
@app.get("/api/session/{session_id}")
@limiter.limit("20/minute")
async def get_session_history(
    session_id: str,
    db: Session = Depends(get_db),
    _:dict=Depends(verify_token)
):
    try:
        turns = get_turns(db, session_id)
        return {"session_id": session_id, "turns": turns}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/login")
@limiter.limit("5/minute")                      # tight limit to slow brute force
async def login(request: Request, body: LoginRequest):
    if not verify_staff_password(body.password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return create_access_token()


@app.post("/api/logout")
async def logout(payload: dict = Depends(verify_token)):
    revoke_token(payload)
    return {"status": "logged out"}

# ── Static files ──
frontend_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "frontend")

@app.get("/")
async def serve_index():
    return FileResponse(os.path.join(frontend_dir, "index.html"))

app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")