from pydantic import BaseModel, Field, field_validator
from typing import Optional, Literal

class TranslateRequest(BaseModel):
    text: str
    source_language: str
    target_language: str = "english"

class TranslateResponse(BaseModel):
    translated_text: str
    detected_intent: str
    process_guide: list[str]
    confidence: float

class StaffReplyRequest(BaseModel):
    reply_text: str
    target_language: str
    session_id: Optional[str] = None

class StaffReplyResponse(BaseModel):
    translated_reply: str
    audio_base64: Optional[str]

class SummaryRequest(BaseModel):
    conversation: list[dict]=[] # [{role, text, language}]
    customer_language: str="hindi"
    session_id: Optional[str]=None

class SummaryResponse(BaseModel):
    english_summary: str
    vernacular_summary: str

class CalculationInputs(BaseModel):
    type: Literal["emi", "fd", "rd", "eligibility", "none"] = "none"
    p: Optional[float] = None
    n: Optional[float] = None
    income: Optional[float] = None
    loan_category: Optional[str] = None

class LLMTranslationOutput(BaseModel):
    english_translation: str
    intent: str = "other"
    confidence: float = Field(default=0.5)
    suggested_counter: str = "inquiry_desk"
    entities: dict = {}
    calculation_inputs: CalculationInputs = Field(default_factory=CalculationInputs)

    @field_validator("intent", mode="before")
    @classmethod
    def intent_must_be_valid(cls, v: str) -> str:
        valid = [
            "account_opening", "balance_enquiry", "fd_rd_enquiry",
            "loan_enquiry", "kyc_update", "complaint", "fund_transfer",
            "account_closure", "nomination_update", "cheque_services",
            "mudra_loan", "kisan_credit_card", "debit_card_services",
            "tax_certificate_request", "other"
        ]
        return v if v in valid else "other"

    @field_validator("confidence", mode="before")
    @classmethod
    def clamp_confidence(cls, v: float) -> float:
        return max(0.0, min(1.0, v))

    @field_validator("suggested_counter", mode="before")
    @classmethod
    def counter_must_be_valid(cls, v: str) -> str:
        valid = [
            "inquiry_desk", "cash_counter", "service_counter",
            "investment_counter", "specialized_counter",
            "operational_supervisor", "branch_manager"
        ]
        return v if v in valid else "inquiry_desk"

class LoginRequest(BaseModel):
    password: str