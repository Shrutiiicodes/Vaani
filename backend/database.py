from sqlalchemy import create_engine, Column, String, Float, Text, DateTime, Integer
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import datetime, json

DATABASE_URL = "sqlite:///./banking_sessions.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()


class BankingSession(Base):
    __tablename__ = "sessions"

    id = Column(String, primary_key=True)          # UUID, generated frontend or backend
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
    customer_language = Column(String, default="hindi")
    detected_intent = Column(String, nullable=True)


class ConversationTurn(Base):
    __tablename__ = "conversation_turns"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String, nullable=False)    # FK to sessions.id
    role = Column(String)                          # "customer" or "staff"
    original_text = Column(Text)
    translated_text = Column(Text)
    language = Column(String)
    intent = Column(String, nullable=True)
    confidence = Column(Float, nullable=True)
    entities = Column(Text, default="{}")          # JSON string
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)

    def entities_dict(self):
        return json.loads(self.entities or "{}")


def init_db():
    Base.metadata.create_all(bind=engine)