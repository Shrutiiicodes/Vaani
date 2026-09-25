"""Post-LLM logic, tested with canned LLM outputs (no API key needed)."""
from models import LLMTranslationOutput
from translate import MONEY_FOLLOWUP_EN, calculation_readout, parse_llm_output, postprocess


def llm(**fields) -> dict:
    """A validated LLM output, as translate_customer_speech would pass to postprocess."""
    fields.setdefault("english_translation", "text")
    return LLMTranslationOutput(**fields).model_dump()


# ── Entity normalisation (the eval's recall misses) ───────────────────────────

def test_tenure_years_become_months_and_amount_is_numeric():
    out = postprocess(llm(intent="loan_enquiry", confidence=0.9,
                          entities={"amount": "50 lakhs", "tenure_years": "20", "loan_type": "home"}), "x")
    assert out["entities"]["tenure_months"] == "240"
    assert out["entities"]["amount"] == "5000000"
    assert "tenure_years" not in out["entities"]


def test_tenure_with_unit_text_is_converted():
    out = postprocess(llm(intent="fd_rd_enquiry", confidence=0.9, entities={"tenure": "3 years"}), "x")
    assert out["entities"]["tenure_months"] == "36"


def test_alias_keys_are_canonicalised():
    out = postprocess(llm(intent="nomination_update", confidence=0.9,
                          entities={"relationship": "wife", "name": "Sita", "phone": "9876543210"}), "x")
    assert out["entities"]["nominee_relation"] == "wife"
    assert out["entities"]["full_name"] == "Sita"
    assert out["entities"]["mobile"] == "9876543210"


# ── Calculations wired through postprocess ────────────────────────────────────

def test_emi_prefers_normalised_entities_over_raw_calc_inputs():
    # The LLM put years into n; the entity says 20 years -> 240 months.
    out = postprocess(llm(intent="loan_enquiry", confidence=0.9,
                          entities={"amount": "500000", "tenure_years": "20", "loan_type": "kisan"},
                          calculation_inputs={"type": "emi", "p": 500000, "n": 20}), "x")
    calc = out["calculation_results"]
    assert calc["rate_used"] == 7.0            # kisan -> KCC rate, not the 10% default
    assert calc["total_payment"] == calc["emi"] * 240


def test_no_calculation_when_type_none():
    assert postprocess(llm(intent="balance_enquiry", confidence=0.9), "x")["calculation_results"] is None


def test_readout_text():
    assert "EMI" in calculation_readout({"type": "emi", "emi": 100, "total_payment": 1200})
    assert calculation_readout({"type": "none"}) is None
    assert calculation_readout(None) is None


# ── Forms ─────────────────────────────────────────────────────────────────────

def test_fd_enquiry_opens_fd_form_with_prefill():
    out = postprocess(llm(intent="fd_rd_enquiry", confidence=0.9,
                          entities={"amount": "2 lakh", "tenure_months": "36"}), "x")
    form = out["form_template"]
    assert form["type"] == "fd_opening"
    assert form["prefill"] == {"deposit_amount": "200000", "tenure_months": "36"}


def test_loan_form_maps_full_name_to_applicant_name():
    out = postprocess(llm(intent="loan_enquiry", confidence=0.9, entities={"full_name": "Ravi"}), "x")
    assert out["form_template"]["prefill"]["applicant_name"] == "Ravi"


def test_active_form_kept_when_intent_is_other():
    out = postprocess(llm(intent="other", confidence=0.9, entities={"mobile": "98"}), "x", "kyc_update")
    assert out["form_template"]["type"] == "kyc_update"


# ── Clarification ─────────────────────────────────────────────────────────────

def test_vague_money_request_asks_for_clarification():
    out = postprocess(llm(intent="other", confidence=0.4), "Mujhe paisa chahiye")
    assert out["needs_clarification"] is True
    assert out["follow_up_question"] == MONEY_FOLLOWUP_EN
    assert out["process_guide"] == []


def test_confident_specific_money_request_is_not_second_guessed():
    # Old heuristic forced a clarification for any short sentence mentioning money.
    out = postprocess(llm(intent="cash_transaction", confidence=0.95), "Withdraw 5000 rupees")
    assert out["needs_clarification"] is False
    assert out["process_guide"]


def test_llm_can_flag_ambiguity_itself():
    out = postprocess(llm(intent="loan_enquiry", confidence=0.6, needs_clarification=True), "मुझे पैसे चाहिए")
    assert out["needs_clarification"] is True


def test_non_money_other_intent_does_not_ask():
    assert postprocess(llm(intent="other", confidence=0.9), "Where is the washroom?")["needs_clarification"] is False


# ── Parsing the raw LLM text ──────────────────────────────────────────────────

def test_parse_handles_fences_and_indian_number_strings():
    raw = '```json\n{"english_translation": "hi", "intent": "loan_enquiry", "calculation_inputs": {"type": "emi", "p": "5,00,000", "n": "24"}}\n```'
    out = parse_llm_output(raw, "fallback")
    assert out["intent"] == "loan_enquiry"
    assert out["calculation_inputs"]["p"] == 500000


def test_parse_garbage_falls_back_to_source_text():
    out = parse_llm_output("sorry, I cannot help", "original words")
    assert out["english_translation"] == "original words"
    assert out["intent"] == "other"


def test_parse_non_object_json_falls_back():
    assert parse_llm_output("[1, 2]", "x")["intent"] == "other"
