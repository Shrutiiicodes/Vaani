from models import LLMTranslationOutput


def test_valid_output():
    out = LLMTranslationOutput(
        english_translation="I want to open an account", intent="account_opening", confidence=0.92,
        suggested_counter="service_counter", entities={"full_name": "Ramesh"},
        calculation_inputs={"type": "none"},
    )
    assert out.intent == "account_opening"
    assert out.confidence == 0.92


def test_invalid_intent_falls_back():
    assert LLMTranslationOutput(english_translation="x", intent="loan_query").intent == "other"


def test_confidence_is_clamped_and_coerced():
    assert LLMTranslationOutput(english_translation="x", confidence=1.8).confidence == 1.0
    assert LLMTranslationOutput(english_translation="x", confidence="0.7").confidence == 0.7
    assert LLMTranslationOutput(english_translation="x", confidence="high").confidence == 0.5


def test_invalid_counter_falls_back():
    assert LLMTranslationOutput(english_translation="x", suggested_counter="atm").suggested_counter == "inquiry_desk"


def test_unknown_calc_type_becomes_none():
    out = LLMTranslationOutput(english_translation="x", calculation_inputs={"type": "sip"})
    assert out.calculation_inputs.type == "none"


def test_placeholder_entities_are_dropped():
    out = LLMTranslationOutput(english_translation="x", entities={"full_name": "", "amount": "...", "mobile": "98"})
    assert out.entities == {"mobile": "98"}


def test_missing_fields_use_defaults():
    out = LLMTranslationOutput(english_translation="test")
    assert out.intent == "other"
    assert out.confidence == 0.5
    assert out.suggested_counter == "inquiry_desk"
    assert out.needs_clarification is False
