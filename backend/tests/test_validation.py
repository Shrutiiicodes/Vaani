import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from models import LLMTranslationOutput

def test_valid_output():
    data = {
        "english_translation": "I want to open an account",
        "intent": "account_opening",
        "confidence": 0.92,
        "suggested_counter": "service_counter",
        "entities": {"full_name": "Ramesh"},
        "calculation_inputs": {"type": "none"}
    }
    out = LLMTranslationOutput(**data)
    assert out.intent == "account_opening"
    assert out.confidence == 0.92

def test_invalid_intent_falls_back():
    data = {
        "english_translation": "I want a loan",
        "intent": "loan_query",    # not a valid intent
        "confidence": 0.8,
        "suggested_counter": "specialized_counter",
        "entities": {},
        "calculation_inputs": {"type": "none"}
    }
    out = LLMTranslationOutput(**data)
    assert out.intent == "other"   # validator corrected it

def test_confidence_out_of_range():
    data = {
        "english_translation": "Hello",
        "intent": "other",
        "confidence": 1.8,          # out of range
        "suggested_counter": "inquiry_desk",
        "entities": {},
        "calculation_inputs": {"type": "none"}
    }
    out = LLMTranslationOutput(**data)
    assert out.confidence == 1.0   # clamped

def test_missing_fields_use_defaults():
    out = LLMTranslationOutput(english_translation="test")
    assert out.intent == "other"
    assert out.confidence == 0.5
    assert out.suggested_counter == "inquiry_desk"