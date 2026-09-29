from typing import Literal

from pydantic import BaseModel, Field, field_validator

from banking_context import COUNTERS, INTENT_CATEGORIES

SESSION_ID = r"^[A-Za-z0-9-]{8,64}$"


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class StaffCreate(BaseModel):
    username: str = Field(pattern=r"^[a-zA-Z0-9_.-]{3,64}$")
    password: str = Field(min_length=8, max_length=256)
    role: Literal["staff", "admin"] = "staff"


class StaffReplyRequest(BaseModel):
    reply_text: str = Field(min_length=1, max_length=2000)
    target_language: str = Field(pattern=r"^[A-Za-z ]{2,32}$")
    session_id: str | None = Field(default=None, pattern=SESSION_ID)


class SummaryRequest(BaseModel):
    session_id: str = Field(pattern=SESSION_ID)


class CalculationInputs(BaseModel):
    type: Literal["emi", "fd", "rd", "eligibility", "none"] = "none"
    p: float | None = None
    n: float | None = None
    income: float | None = None
    existing_emi: float | None = None
    loan_category: str | None = None

    @field_validator("type", mode="before")
    @classmethod
    def unknown_type_is_none(cls, v):
        return v if v in ("emi", "fd", "rd", "eligibility") else "none"


class LLMTranslationOutput(BaseModel):
    english_translation: str
    intent: str = "other"
    confidence: float = Field(default=0.5)
    suggested_counter: str = "inquiry_desk"
    entities: dict = {}
    calculation_inputs: CalculationInputs = Field(default_factory=CalculationInputs)
    needs_clarification: bool = False

    @field_validator("intent", mode="before")
    @classmethod
    def intent_must_be_valid(cls, v: str) -> str:
        return v if v in INTENT_CATEGORIES else "other"

    @field_validator("confidence", mode="before")
    @classmethod
    def clamp_confidence(cls, v) -> float:
        try:
            return max(0.0, min(1.0, float(v)))
        except (TypeError, ValueError):
            return 0.5

    @field_validator("suggested_counter", mode="before")
    @classmethod
    def counter_must_be_valid(cls, v: str) -> str:
        return v if v in COUNTERS else "inquiry_desk"

    @field_validator("entities", mode="before")
    @classmethod
    def entities_must_be_dict(cls, v):
        # Drop empty values the LLM pads the schema with ("", null, "...").
        if not isinstance(v, dict):
            return {}
        return {k: val for k, val in v.items() if val not in (None, "", "...", "N/A", "null")}
