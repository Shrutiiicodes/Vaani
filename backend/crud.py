import json
import os
from datetime import UTC

from sqlalchemy import func

from auth import hash_password
from database import BankingSession, ConversationTurn, SessionLocal, Staff, _now


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ── Staff ─────────────────────────────────────────────────────────────────────

def get_staff(db, username: str):
    return db.get(Staff, username)


def create_staff(db, username: str, password: str, role: str = "staff") -> Staff:
    staff = Staff(username=username, password_hash=hash_password(password), role=role)
    db.add(staff)
    db.commit()
    return staff


def sync_bootstrap_admin(db):
    """Make STAFF_USERNAME / STAFF_PASSWORD from the environment a working admin login.

    Runs on every startup, so rotating the password in the env takes effect on restart.
    """
    password = os.getenv("STAFF_PASSWORD")
    if not password:
        return
    username = os.getenv("STAFF_USERNAME", "admin")
    staff = get_staff(db, username)
    if staff is None:
        create_staff(db, username, password, role="admin")
    else:
        staff.password_hash = hash_password(password)
        staff.role = "admin"
        db.commit()


# ── Sessions ──────────────────────────────────────────────────────────────────

def _can_access(session: BankingSession, staff: dict) -> bool:
    return staff.get("role") == "admin" or session.staff_id == staff["sub"]


def get_session_for(db, session_id: str, staff: dict):
    """The session if it exists and this staff member may see it, else None."""
    session = db.get(BankingSession, session_id)
    return session if session and _can_access(session, staff) else None


def claim_session(db, session_id: str, staff: dict):
    """Get or create a session owned by this staff member. None if someone else owns it."""
    session = db.get(BankingSession, session_id)
    if session is None:
        session = BankingSession(id=session_id, staff_id=staff["sub"])
        db.add(session)
        db.commit()
        return session
    return session if _can_access(session, staff) else None


def _utc(dt):
    # SQLite drops tzinfo on the way back; values are always written in UTC.
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def list_sessions(db, staff: dict, limit: int = 50) -> list:
    q = (db.query(BankingSession, func.count(ConversationTurn.id))
         .join(ConversationTurn, ConversationTurn.session_id == BankingSession.id))   # skip empty sessions
    if staff.get("role") != "admin":
        q = q.filter(BankingSession.staff_id == staff["sub"])
    q = q.group_by(BankingSession.id).order_by(BankingSession.updated_at.desc()).limit(limit)
    return [
        {
            "session_id": s.id,
            "staff": s.staff_id,
            "updated_at": _utc(s.updated_at).isoformat() if s.updated_at else None,
            "customer_language": s.customer_language,
            "intent": s.detected_intent,
            "turns": n,
            "summary": json.loads(s.summary) if s.summary else None,
        }
        for s, n in q.all()
    ]


def update_session_language(db, session_id: str, language: str):
    session = db.get(BankingSession, session_id)
    if session:
        session.customer_language = language
        session.updated_at = _now()
        db.commit()


def save_summary(db, session_id: str, summary: dict):
    session = db.get(BankingSession, session_id)
    if session:
        session.summary = json.dumps(summary, ensure_ascii=False)
        db.commit()


# ── Turns ─────────────────────────────────────────────────────────────────────

def add_turn(db, session_id: str, role: str, original: str, translated: str,
             language: str, intent: str | None = None, confidence: float | None = None,
             entities: dict | None = None):
    turn = ConversationTurn(
        session_id=session_id,
        role=role,
        original_text=original,
        translated_text=translated,
        language=language,
        intent=intent,
        confidence=confidence,
        entities=json.dumps(entities or {}, ensure_ascii=False),
    )
    db.add(turn)
    session = db.get(BankingSession, session_id)
    if session:
        session.updated_at = _now()
        if intent and intent != "other":
            session.detected_intent = intent
    db.commit()
    return turn


def get_turns(db, session_id: str) -> list:
    turns = (db.query(ConversationTurn)
             .filter(ConversationTurn.session_id == session_id)
             .order_by(ConversationTurn.timestamp, ConversationTurn.id)
             .all())
    return [
        {
            "role": t.role,
            "text": t.original_text,
            "translated": t.translated_text,
            "language": t.language,
            "intent": t.intent,
            "entities": t.entities_dict(),
        }
        for t in turns
    ]
