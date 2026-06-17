from database import SessionLocal, BankingSession, ConversationTurn, init_db
import json, uuid
from datetime import datetime, timezone

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_session(db, session_id: str | None = None, language: str = "hindi") -> BankingSession:
    session_id = session_id or str(uuid.uuid4())
    session = BankingSession(id=session_id, customer_language=language)
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def get_session(db, session_id: str):
    return db.query(BankingSession).filter(BankingSession.id == session_id).first()


def get_or_create_session(db, session_id: str, language: str = "hindi") -> BankingSession:
    session = get_session(db, session_id)
    if not session:
        session = create_session(db, session_id, language)
    return session


def add_turn(db, session_id: str, role: str, original: str, translated: str,
             language: str, intent: str | None = None, confidence: float | None = None, entities: dict | None = None):
    turn = ConversationTurn(
        session_id=session_id,
        role=role,
        original_text=original,
        translated_text=translated,
        language=language,
        intent=intent,
        confidence=confidence,
        entities=json.dumps(entities or {})
    )
    db.add(turn)
    db.commit()
    return turn


def get_turns(db, session_id: str) -> list:
    turns = db.query(ConversationTurn)\
              .filter(ConversationTurn.session_id == session_id)\
              .order_by(ConversationTurn.timestamp)\
              .all()
    return [
        {
            "role": t.role,
            "text": t.original_text,
            "translated": t.translated_text,
            "language": t.language,
            "intent": t.intent,
            "entities": t.entities_dict()
        }
        for t in turns
    ]


def update_session_language(db, session_id: str, language: str):
    session = get_session(db, session_id)
    if session:
        session.customer_language = language
        session.updated_at = datetime.now(timezone.utc)