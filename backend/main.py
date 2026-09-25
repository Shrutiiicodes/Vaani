import json
import logging
import os
import sys
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session

import crud
from auth import DUMMY_HASH, check_password, create_access_token, require_admin, revoke_token, verify_token
from banking_context import BANK_NAME, COUNTERS, FD_SLABS, FORM_TEMPLATES, LANGUAGES, LOAN_RATES
from database import SessionLocal, init_db
from models import SESSION_ID, LoginRequest, StaffCreate, StaffReplyRequest, SummaryRequest
from stt import transcribe_audio
from translate import (
    calculation_readout,
    generate_summary,
    translate_customer_speech,
    translate_staff_reply,
    translate_text,
)
from tts import is_supported_language, text_to_speech_base64

MAX_AUDIO_BYTES = 10 * 1024 * 1024
MAX_BODY_BYTES = MAX_AUDIO_BYTES + 64 * 1024


# ── Logging: one JSON object per line ─────────────────────────────────────────

class JsonFormatter(logging.Formatter):
    def format(self, record):
        entry = {"ts": self.formatTime(record), "level": record.levelname, "msg": record.getMessage()}
        entry.update(getattr(record, "fields", {}))
        if record.exc_info:
            entry["exc"] = self.formatException(record.exc_info)
        return json.dumps(entry, ensure_ascii=False, default=str)


log = logging.getLogger("vaani")
if not log.handlers:
    _handler = logging.StreamHandler(sys.stdout)
    _handler.setFormatter(JsonFormatter())
    log.addHandler(_handler)
    log.setLevel(os.getenv("LOG_LEVEL", "INFO"))
    log.propagate = False


def _ms(since: float) -> int:
    return round((time.perf_counter() - since) * 1000)


# ── App ───────────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    with SessionLocal() as db:
        crud.sync_bootstrap_admin(db)
    if not os.getenv("GROQ_API_KEY"):
        log.warning("GROQ_API_KEY is not set; speech and translation calls will fail")
    yield


app = FastAPI(title="Vaani", lifespan=lifespan)

limiter = Limiter(key_func=get_remote_address,
                  enabled=os.getenv("RATE_LIMIT_ENABLED", "true").lower() != "false")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in os.getenv("ALLOWED_ORIGINS", "http://localhost:8000").split(",") if o.strip()],
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
    expose_headers=["X-Request-ID"],
)


@app.middleware("http")
async def request_context(request: Request, call_next):
    length = request.headers.get("content-length", "")
    if length.isdigit() and int(length) > MAX_BODY_BYTES:
        return JSONResponse({"detail": "Request too large"}, status_code=413)
    rid = request.headers.get("x-request-id") or uuid.uuid4().hex
    request.state.request_id = rid
    request.state.timings = {}
    start = time.perf_counter()
    response = await call_next(request)
    response.headers["X-Request-ID"] = rid
    if request.url.path.startswith("/api/"):
        log.info("request", extra={"fields": {
            "request_id": rid, "method": request.method, "path": request.url.path,
            "status": response.status_code, "ms_to_response": _ms(start), **request.state.timings,
        }})
    return response


@app.exception_handler(Exception)
async def unhandled_error(request: Request, exc: Exception):
    rid = getattr(request.state, "request_id", None)
    log.error("unhandled_error", exc_info=exc, extra={"fields": {"request_id": rid, "path": request.url.path}})
    return JSONResponse({"detail": "Internal server error", "request_id": rid}, status_code=500)


# ── Health, auth, staff ───────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/api/login")
@limiter.limit("5/minute")                      # slows brute force
async def login(request: Request, body: LoginRequest, db: Session = Depends(crud.get_db)):
    staff = crud.get_staff(db, body.username)
    ok = check_password(body.password, staff.password_hash if staff else DUMMY_HASH)
    if not (staff and ok):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return create_access_token(staff.username, staff.role)


@app.post("/api/logout")
async def logout(payload: dict = Depends(verify_token)):
    revoke_token(payload)
    return {"status": "logged out"}


@app.post("/api/staff", status_code=201)
async def create_staff(body: StaffCreate, db: Session = Depends(crud.get_db), _: dict = Depends(require_admin)):
    if crud.get_staff(db, body.username):
        raise HTTPException(status_code=409, detail="Username already exists")
    crud.create_staff(db, body.username, body.password, body.role)
    return {"username": body.username, "role": body.role}


# ── Reference data ────────────────────────────────────────────────────────────

@app.get("/api/rates")
async def rates():
    """Bank display name and indicative rates; the frontend renders its tables from this."""
    return {
        "bank_name": BANK_NAME,
        "loans": [{"category": k, "label": label, "rate": r} for k, (label, r) in LOAN_RATES.items()],
        "fd_slabs": [{"label": label, "general": g, "senior": s} for _, label, g, s in FD_SLABS],
        "languages": LANGUAGES,
    }


# ── Sessions ──────────────────────────────────────────────────────────────────

@app.get("/api/sessions")
async def list_sessions(db: Session = Depends(crud.get_db), staff: dict = Depends(verify_token)):
    return {"sessions": crud.list_sessions(db, staff)}


@app.get("/api/session/{session_id}")
@limiter.limit("20/minute")
async def get_session_history(request: Request, session_id: str,
                              db: Session = Depends(crud.get_db), staff: dict = Depends(verify_token)):
    if not crud.get_session_for(db, session_id, staff):
        raise HTTPException(status_code=404, detail="Session not found")
    return {"session_id": session_id, "turns": crud.get_turns(db, session_id)}


# ── Customer turn: audio in, Server-Sent Events out ───────────────────────────

def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def _customer_turn(request_id: str, audio_bytes: bytes, filename: str, session_id: str,
                         active_form: str | None, language_hint: str | None):
    """Yields `transcript`, `analysis`, optional `audio`, then `done` (or `error`)."""
    timings: dict = {}
    start = time.perf_counter()
    try:
        t = time.perf_counter()
        stt = await transcribe_audio(audio_bytes, filename, language_hint)
        timings["stt_ms"] = _ms(t)
        lang = stt["language"] or "hindi"
        text = stt["text"] or ""
        yield _sse("transcript", {"original_text": text, "detected_language": lang,
                                  "tts_supported": is_supported_language(lang)})

        # ponytail: sync DB calls on the event loop; fine for SQLite / a nearby Postgres,
        # move to run_in_threadpool if DB latency shows up in the timings.
        with SessionLocal() as db:
            history = crud.get_turns(db, session_id)

        t = time.perf_counter()
        data = await translate_customer_speech(text, lang, history, active_form)
        timings["llm_ms"] = _ms(t)
        counter = data.get("suggested_counter") or "inquiry_desk"
        yield _sse("analysis", {
            "english_translation": data["english_translation"],
            "intent": data["intent"],
            "confidence": data["confidence"],
            "process_guide": data["process_guide"],
            "suggested_counter": counter,
            "counter_name": COUNTERS.get(counter, COUNTERS["inquiry_desk"]),
            "entities": data["entities"],
            "form_template": data["form_template"],
            "calculation_results": data["calculation_results"],
            "needs_clarification": data["needs_clarification"],
            "follow_up_question": data["follow_up_question"],
        })

        with SessionLocal() as db:
            crud.update_session_language(db, session_id, lang)
            crud.add_turn(db, session_id=session_id, role="customer", original=text,
                          translated=data["english_translation"], language=lang,
                          intent=data["intent"], confidence=data["confidence"], entities=data["entities"])

        # Speak back either the clarification question or the calculation result.
        speech_en, kind = None, None
        if data["needs_clarification"] and data["follow_up_question"]:
            speech_en, kind = data["follow_up_question"], "follow_up"
        elif readout := calculation_readout(data["calculation_results"]):
            speech_en, kind = readout, "calculation"
        if speech_en:
            t = time.perf_counter()
            vernacular = await translate_text(speech_en, lang)
            audio = await text_to_speech_base64(vernacular, lang)
            timings["speech_ms"] = _ms(t)
            yield _sse("audio", {"kind": kind, "text": vernacular, "audio_base64": audio})

        timings["total_ms"] = _ms(start)
        yield _sse("done", {"request_id": request_id, **timings})
    except Exception:
        log.exception("customer_turn_failed", extra={"fields": {"request_id": request_id}})
        yield _sse("error", {"detail": "Processing failed", "request_id": request_id})
    finally:
        timings.setdefault("total_ms", _ms(start))
        log.info("customer_turn", extra={"fields": {"request_id": request_id, **timings}})


@app.post("/api/customer-speak")
@limiter.limit("20/minute")
async def customer_speak(
    request: Request,
    audio: UploadFile = File(...),
    session_id: str = Form(..., pattern=SESSION_ID),
    active_form: str | None = Form(None),
    language: str | None = Form(None),
    staff: dict = Depends(verify_token),
):
    if not (audio.content_type or "").startswith("audio/"):
        raise HTTPException(status_code=415, detail="Expected an audio file")
    if language and language not in LANGUAGES.values():
        raise HTTPException(status_code=400, detail="Unsupported language hint")
    audio_bytes = await audio.read(MAX_AUDIO_BYTES + 1)
    if len(audio_bytes) > MAX_AUDIO_BYTES:
        raise HTTPException(status_code=413, detail="Audio too large (max 10 MB)")
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Empty audio")
    with SessionLocal() as db:
        if crud.claim_session(db, session_id, staff) is None:
            raise HTTPException(status_code=404, detail="Session not found")

    return StreamingResponse(
        _customer_turn(request.state.request_id, audio_bytes, audio.filename or "audio.webm",
                       session_id, active_form if active_form in FORM_TEMPLATES else None, language),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── Staff reply ───────────────────────────────────────────────────────────────

@app.post("/api/staff-reply")
@limiter.limit("30/minute")
async def staff_reply(request: Request, body: StaffReplyRequest,
                      db: Session = Depends(crud.get_db), staff: dict = Depends(verify_token)):
    if body.session_id and not crud.claim_session(db, body.session_id, staff):
        raise HTTPException(status_code=404, detail="Session not found")

    t = time.perf_counter()
    translated = await translate_staff_reply(body.reply_text, body.target_language)
    request.state.timings["llm_ms"] = _ms(t)
    t = time.perf_counter()
    audio_b64 = await text_to_speech_base64(translated, body.target_language)
    request.state.timings["tts_ms"] = _ms(t)

    if body.session_id:
        crud.add_turn(db, session_id=body.session_id, role="staff", original=body.reply_text,
                      translated=translated, language="english")

    return {"translated_reply": translated, "audio_base64": audio_b64, "tts_supported": audio_b64 is not None}


# ── Summary ───────────────────────────────────────────────────────────────────

@app.post("/api/summary")
@limiter.limit("30/minute")
async def session_summary(request: Request, body: SummaryRequest,
                          db: Session = Depends(crud.get_db), staff: dict = Depends(verify_token)):
    session = crud.get_session_for(db, body.session_id, staff)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    turns = crud.get_turns(db, body.session_id)
    if not turns:
        raise HTTPException(status_code=400, detail="No conversation to summarize")

    t = time.perf_counter()
    summary = await generate_summary(turns, session.customer_language or "hindi")
    request.state.timings["llm_ms"] = _ms(t)
    crud.save_summary(db, body.session_id, summary)
    return summary


# ── Static frontend (absent on Vercel, where it is served by the static builder) ──

frontend_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "frontend")
if os.path.isdir(frontend_dir):
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
