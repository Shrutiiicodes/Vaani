import copy
import json
import logging
import math
import os
import re

from dotenv import load_dotenv
from groq import AsyncGroq
from pydantic import ValidationError

from banking_context import (
    BANKING_SYSTEM_PROMPT,
    COUNTERS,
    DEFAULT_LOAN_RATE,
    FD_SLABS,
    FORM_TEMPLATES,
    INTENT_CATEGORIES,
    INTENT_COUNTERS,
    INTENT_FORMS,
    LOAN_CATEGORY_ALIASES,
    LOAN_RATES,
    PROCESS_GUIDES,
)
from cache import async_cache
from models import LLMTranslationOutput

load_dotenv()
log = logging.getLogger("vaani")
client = AsyncGroq(api_key=os.getenv("GROQ_API_KEY", ""))

# llama-3.3-70b-versatile (the original model) was retired by Groq; keep this configurable.
# Qwen won the 150-case benchmark on both accuracy and latency (see backend/eval/RESULTS.md);
# openai/gpt-oss-120b is the tested alternative.
MODEL = os.getenv("LLM_MODEL", "qwen/qwen3.8-27b")
HISTORY_TURNS = 10   # ponytail: fixed window keeps prompt size bounded; summarise older turns if context is lost

MONEY_FOLLOWUP_EN = (
    "Are you looking to withdraw cash from your account, "
    "take a loan, or break a Fixed Deposit (FD)?"
)

MONEY_KEYWORDS = [
    "money", "cash", "paisa", "paise", "paisaa", "pesa", "rupee", "rupees", "rupaye", "funds",
    "पैसा", "पैसे", "रुपये", "रुपया",      # Hindi / Marathi
    "টাকা",                                  # Bengali
    "பணம்",                                  # Tamil
    "డబ్బు",                                 # Telugu
    "ಹಣ",                                    # Kannada
    "પૈસા", "રૂપિયા",                        # Gujarati
    "ଟଙ୍କା",                                 # Odia
]

# Keys the prompt asks the LLM to use. Anything else it invents is kept, but
# these are the ones forms, calculations and the eval rely on.
ENTITY_KEYS = [
    "full_name", "account_number", "account_type", "amount", "tenure_months", "loan_type",
    "mobile", "monthly_income", "existing_emis", "nominee_name", "nominee_relation",
    "beneficiary_name", "beneficiary_account", "ifsc_code", "transfer_mode",
    "pan_number", "aadhaar_number", "dob", "address", "cheque_number", "card_last4",
]

# Canonical entity key <- other keys the LLM sometimes emits instead.
ENTITY_ALIASES = {
    "full_name": ["name", "customer_name", "applicant_name"],
    "mobile": ["phone", "phone_number", "mobile_number", "contact"],
    "account_number": ["acc_no", "account_no", "acct_number"],
    "account_type": ["acct_type"],
    "amount": ["loan_amount", "deposit_amount", "principal", "loan_value", "deposit_value"],
    "loan_type": ["loan_category"],
    "nominee_relation": ["relation", "relationship", "nominee_relationship"],
    "nominee_name": ["nominee"],
    "existing_emis": ["existing_emi"],
    "monthly_income": ["income", "salary"],
}

# Form field <- canonical entity key, where the form uses a different name.
FORM_FIELD_SOURCES = {
    "applicant_name": "full_name",
    "loan_amount": "amount",
    "deposit_amount": "amount",
    "sender_account": "account_number",
}

AMOUNT_KEYS = {"amount", "loan_amount", "deposit_amount", "monthly_income", "annual_income", "existing_emis"}

_UNITS = {
    "k": 1e3, "thousand": 1e3, "hazar": 1e3, "hazaar": 1e3,
    "l": 1e5, "lac": 1e5, "lacs": 1e5, "lakh": 1e5, "lakhs": 1e5,
    "cr": 1e7, "crore": 1e7, "crores": 1e7,
}


# ── Parsing helpers ───────────────────────────────────────────────────────────

def clean_number(val) -> float:
    """'₹50,000' -> 50000, '1,00,000' -> 100000, '50k' -> 50000, '2.5 lakh' -> 250000,
    '1 crore' -> 10000000, '20 years' -> 20. Returns 0.0 if unparseable."""
    if val is None or isinstance(val, bool):
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).lower().replace(",", "").replace(" ", "")
    s = re.sub(r"^(rs\.?|inr|₹|\$)", "", s)
    m = re.fullmatch(r"(\d+(?:\.\d+)?)([a-z]*)\.?", s)
    if m and (not m.group(2) or m.group(2) in _UNITS):
        return float(m.group(1)) * _UNITS.get(m.group(2), 1)
    digits = re.search(r"\d+(?:\.\d+)?", s)
    return float(digits.group()) if digits else 0.0


def to_months(val) -> float:
    """'3 years' -> 36, '18 months' -> 18, '36' -> 36."""
    n = clean_number(val)
    return n * 12 if re.search(r"year|yr|saal|varsh", str(val).lower()) else n


def _fmt(n: float) -> str:
    return str(int(n)) if n == int(n) else str(n)


def _strip_fences(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("```"):
        parts = raw.split("```")
        raw = parts[1] if len(parts) > 1 else raw
        if raw.startswith("json"):
            raw = raw[4:]
    return raw.strip()


def _mentions_money(text: str) -> bool:
    text = (text or "").lower()
    return any(kw in text for kw in MONEY_KEYWORDS)


def parse_llm_output(raw: str, fallback_text: str) -> dict:
    """LLM JSON -> validated dict. Falls back to a bare translation, and logs why."""
    try:
        data = json.loads(_strip_fences(raw))
        calc = data.get("calculation_inputs")
        if isinstance(calc, dict):
            for field in ("p", "n", "income", "existing_emi"):
                if field in calc:
                    calc[field] = clean_number(calc[field])
        return LLMTranslationOutput(**data).model_dump()
    except (json.JSONDecodeError, ValidationError, TypeError, AttributeError) as e:
        log.warning("llm_output_unparseable",
                    extra={"fields": {"error": str(e)[:300], "raw": raw[:500]}})
        return LLMTranslationOutput(english_translation=fallback_text).model_dump()


_ACCOUNT_TYPE = re.compile(r"\b(savings?|current|salary)\s+(?:bank\s+)?account\b", re.I)


def normalize_entities(entities: dict, english: str = "") -> dict:
    ent = {str(k).strip().lower().replace(" ", "_"): v for k, v in entities.items()}

    if not ent.get("tenure_months"):
        if ent.get("tenure_years"):
            ent["tenure_months"] = f"{ent['tenure_years']} years"
        else:
            for alt in ("tenure", "duration", "period"):
                if ent.get(alt):
                    ent["tenure_months"] = ent[alt]
                    break
    ent.pop("tenure_years", None)
    if ent.get("tenure_months"):
        months = to_months(ent["tenure_months"])
        if months > 0:
            ent["tenure_months"] = _fmt(months)
        else:
            ent.pop("tenure_months")

    for canon, alts in ENTITY_ALIASES.items():
        if not ent.get(canon):
            for alt in alts:
                if ent.get(alt):
                    ent[canon] = ent[alt]
                    break

    # The LLM often skips account_type when it is only an adjective ("open a savings account");
    # the English translation says it plainly, so read it from there.
    if not ent.get("account_type") and (m := _ACCOUNT_TYPE.search(english or "")):
        ent["account_type"] = "savings" if m.group(1).lower().startswith("saving") else m.group(1).lower()

    for key in AMOUNT_KEYS & ent.keys():
        n = clean_number(ent[key])
        if n > 0:
            ent[key] = _fmt(n)
    return ent


# ── Pipeline ──────────────────────────────────────────────────────────────────

async def _chat(messages: list, json_mode: bool = False, temperature: float = 0.1) -> str:
    """The single place the LLM is called (tests patch this)."""
    kwargs = {"response_format": {"type": "json_object"}} if json_mode else {}
    if MODEL.startswith("openai/gpt-oss"):
        kwargs["reasoning_effort"] = "low"     # classification + translation don't need long reasoning
    response = await client.chat.completions.create(
        model=MODEL, messages=messages, temperature=temperature,
        # Answers are ~200 tokens. An explicit cap stops runaway output and keeps requests
        # under Groq's output-tokens-per-minute limit (Qwen's default max rejected long Odia prompts).
        max_tokens=1500, **kwargs
    )
    return response.choices[0].message.content or ""


def build_prompt(text: str, source_lang: str, history: list | None, active_form: str | None) -> str:
    convo_context = ""
    turns = [t for t in (history or []) if t.get("text")][-HISTORY_TURNS:]
    if turns:
        convo_context = "\nConversation so far (oldest first):\n" + "\n".join(
            f"{t['role'].upper()}: {t.get('translated') or t['text']}" for t in turns
        )

    target_fields = ""
    if active_form in FORM_TEMPLATES:
        target_fields = (f"\nThe employee has a {active_form} form open. Also extract these fields "
                         f"using these exact keys: {', '.join(FORM_TEMPLATES[active_form])}")

    return f"""
The customer is speaking in {source_lang}.
Customer said: "{text}"
{convo_context}
{target_fields}

Possible intents: {', '.join(INTENT_CATEGORIES)}
  (cash_transaction = withdrawing or depositing cash at the counter;
   opening or asking about an FD or RD is fd_rd_enquiry, not account_opening)
Possible counters: {json.dumps(COUNTERS)}

Tasks:
1. Translate the customer's words into accurate, natural English.
2. Pick the single best intent.
3. Extract every entity the customer mentioned (use the whole conversation, not only the last sentence).
   Use these snake_case keys where they fit: {', '.join(ENTITY_KEYS)}.
   Omit anything not mentioned. Never output empty strings or placeholders.
   - amount: plain number of rupees ("50 lakh" -> 5000000).
   - tenure_months: tenure converted to months ("3 years" -> 36).
   - account_type: savings / current / salary / fd / rd, whenever the customer names one.
   - nominee_relation: the nominee's relationship to the customer (wife, son, ...). nominee_name only if a name is said.
4. calculation_inputs: amount and tenure only; never ask for or invent interest rates.
   type = emi for a loan with amount and tenure, fd / rd for a deposit, eligibility when the
   customer gives an income and asks how much they can borrow, otherwise none.
5. needs_clarification = true ONLY when the customer's goal is genuinely unclear, e.g. "I need money"
   could mean a cash withdrawal, a loan, or breaking an FD.

Respond with a single JSON object:
{{
  "english_translation": "<translation>",
  "intent": "<intent>",
  "confidence": <0.0 to 1.0>,
  "suggested_counter": "<counter id>",
  "entities": {{"<key>": "<value>"}},
  "calculation_inputs": {{"type": "emi|fd|rd|eligibility|none", "p": <principal rupees>, "n": <tenure months>, "income": <monthly income>, "existing_emi": <current total monthly EMIs>, "loan_category": "home|personal|vehicle|education|gold|kisan|mudra|msme"}},
  "needs_clarification": false
}}
"""


async def translate_customer_speech(text: str, source_lang: str, conversation_history: list | None = None,
                                    active_form_type: str | None = None) -> dict:
    prompt = build_prompt(text, source_lang, conversation_history, active_form_type)
    raw = await _chat(
        [{"role": "system", "content": BANKING_SYSTEM_PROMPT}, {"role": "user", "content": prompt}],
        json_mode=True,
    )
    parsed = parse_llm_output(raw, text)
    result = postprocess(copy.deepcopy(parsed), text, active_form_type)
    result["llm_output"] = parsed   # validated model output before post-processing (eval replays it)
    return result


def postprocess(result: dict, text: str, active_form_type: str | None = None) -> dict:
    """Pure post-LLM logic: entity normalisation, calculations, form prefill, clarification."""
    intent = result.get("intent", "other")
    confidence = result.get("confidence", 0.5)
    english = result.get("english_translation", text)
    entities = normalize_entities(result.get("entities") or {}, english)
    result["entities"] = entities

    # Calculations — entities are normalised, so prefer them over the raw calc inputs.
    calc = dict(result.get("calculation_inputs") or {})
    result["calculation_results"] = None
    if calc.get("type", "none") != "none":
        calc["loan_category"] = calc.get("loan_category") or entities.get("loan_type")
        if entities.get("amount"):
            calc["p"] = clean_number(entities["amount"])
        if entities.get("tenure_months"):
            calc["n"] = clean_number(entities["tenure_months"])
        if not calc.get("income") and entities.get("monthly_income"):
            calc["income"] = clean_number(entities["monthly_income"])
        if not calc.get("existing_emi") and entities.get("existing_emis"):
            calc["existing_emi"] = clean_number(entities["existing_emis"])
        result["calculation_results"] = perform_calculations(calc)

    # Form prefill
    form_type = INTENT_FORMS.get(intent) or (active_form_type if active_form_type in FORM_TEMPLATES else None)
    result["form_template"] = None
    if form_type:
        fields = FORM_TEMPLATES[form_type]
        prefill = {}
        for field in fields:
            value = entities.get(field) or entities.get(FORM_FIELD_SOURCES.get(field, ""))
            if value:
                prefill[field] = value
        result["form_template"] = {"type": form_type, "fields": fields, "prefill": prefill}

    # Clarification: the LLM's own judgement, plus a keyword backstop for vague money requests.
    money = _mentions_money(text) or _mentions_money(english)
    if result.get("needs_clarification") or (money and (intent == "other" or confidence < 0.55)):
        # An unclear request has no settled intent yet; record it as "other" so the stored turn,
        # session history and summary match what staff see (the question, not a guessed intent).
        result["intent"] = intent = "other"
        result["suggested_counter"] = "inquiry_desk"
        result["needs_clarification"] = True
        result["follow_up_question"] = MONEY_FOLLOWUP_EN
        result["process_guide"] = []
    else:
        result["needs_clarification"] = False
        result["follow_up_question"] = None
        result["process_guide"] = PROCESS_GUIDES.get(intent, [])

    result["suggested_counter"] = INTENT_COUNTERS.get(intent, result.get("suggested_counter") or "inquiry_desk")
    return result


# ── Calculations ──────────────────────────────────────────────────────────────

def loan_rate(category: str | None) -> float:
    key = (category or "").lower().strip().replace(" ", "_")
    key = LOAN_CATEGORY_ALIASES.get(key, key)
    if key not in LOAN_RATES and f"{key}_loan" in LOAN_RATES:
        key = f"{key}_loan"
    return LOAN_RATES[key][1] if key in LOAN_RATES else DEFAULT_LOAN_RATE


def deposit_rate(months: float) -> float:
    days = months * 365 / 12
    for max_days, _label, general, _senior in FD_SLABS:
        if days <= max_days:
            return general
    return FD_SLABS[-1][2]


def perform_calculations(inputs: dict) -> dict:
    calc_type = inputs.get("type")
    p = clean_number(inputs.get("p"))
    n = clean_number(inputs.get("n"))  # tenure in months
    results = {"type": calc_type}

    if calc_type == "emi" and p > 0 and n > 0:
        r = loan_rate(inputs.get("loan_category"))
        mr = r / 12 / 100
        emi = p * mr * math.pow(1 + mr, n) / (math.pow(1 + mr, n) - 1)
        results["emi"] = round(emi)
        results["total_payment"] = results["emi"] * int(n)
        results["total_interest"] = round(results["total_payment"] - p)
        results["rate_used"] = r

    elif calc_type == "fd" and p > 0 and n > 0:
        r = deposit_rate(n)
        maturity = p * math.pow(1 + r / 100 / 4, 4 * n / 12)   # quarterly compounding
        results["maturity"] = round(maturity)
        results["interest_earned"] = round(results["maturity"] - p)
        results["rate_used"] = r

    elif calc_type == "rd" and p > 0 and n > 0:
        r = deposit_rate(n)
        i = r / 400
        m = p * (math.pow(1 + i, n / 3) - 1) / (1 - math.pow(1 + i, -1 / 3))
        results["maturity"] = round(m)
        results["total_deposited"] = round(p * n)
        results["interest_earned"] = round(results["maturity"] - results["total_deposited"])
        results["rate_used"] = r

    elif calc_type == "eligibility":
        income = clean_number(inputs.get("income"))
        existing = clean_number(inputs.get("existing_emi"))
        # ponytail: flat 50% FOIR rule; real underwriting also weighs CIBIL, age and employer.
        emi_capacity = max(income * 0.5 - existing, 0)
        r = loan_rate(inputs.get("loan_category") or "personal_loan")
        months = n if n > 0 else 60
        mr = r / 12 / 100
        results["max_loan"] = round(emi_capacity * (1 - math.pow(1 + mr, -months)) / mr)
        results["suggested_emi_limit"] = round(emi_capacity)
        results["rate_used"] = r
        results["tenure_months"] = int(months)

    return results


def calculation_readout(calc: dict | None) -> str | None:
    """English sentence read aloud to the customer for a calculation result."""
    calc = calc or {}
    t = calc.get("type")
    if t == "emi" and "emi" in calc:
        return f"Your monthly EMI will be ₹{calc['emi']}. Total payment will be ₹{calc['total_payment']}."
    if t in ("fd", "rd") and "maturity" in calc:
        return (f"At maturity, your {t.upper()} will be worth ₹{calc['maturity']}. "
                f"Interest earned is ₹{calc['interest_earned']}.")
    if t == "eligibility" and "max_loan" in calc:
        return (f"Your maximum eligible loan amount is ₹{calc['max_loan']}. "
                f"Your suggested EMI limit is ₹{calc['suggested_emi_limit']}.")
    return None


# ── Translation & summary ─────────────────────────────────────────────────────

async def translate_staff_reply(reply: str, target_lang: str) -> str:
    prompt = (
        f"Translate the following bank staff reply into {target_lang} for the customer. "
        f"Use simple, friendly language the customer understands, and preserve all amounts, "
        f"account details, and banking terms exactly as defined. "
        f"Respond with ONLY the translation, no preamble.\n\n"
        f"Staff reply: {reply}"
    )
    out = await _chat([{"role": "system", "content": BANKING_SYSTEM_PROMPT},
                       {"role": "user", "content": prompt}])
    return out.strip()


@async_cache(maxsize=256)
async def translate_text(text: str, target_lang: str) -> str:
    if not target_lang or target_lang.lower() in ("english", "en"):
        return text
    out = await _chat([
        {"role": "system", "content": BANKING_SYSTEM_PROMPT},
        {"role": "user", "content": f"Translate to {target_lang}. Respond with ONLY the translation.\n\n{text}"},
    ])
    return out.strip()


async def generate_summary(conversation: list, customer_language: str) -> dict:
    lines = []
    for turn in conversation:
        line = f"{turn['role'].upper()}: {turn['text']}"
        if turn["role"] == "customer" and turn.get("translated"):
            line += f"  (English: {turn['translated']})"
        lines.append(line)
    prompt = (
        "Summarise this bank branch conversation for the bank's records. Return a JSON object with "
        "keys english_summary (2-4 sentences: what the customer needed, key details and amounts, "
        f"next steps) and vernacular_summary (the same summary in {customer_language}).\n\n"
        + "\n".join(lines)
    )
    raw = await _chat([{"role": "system", "content": BANKING_SYSTEM_PROMPT},
                       {"role": "user", "content": prompt}], json_mode=True, temperature=0.2)
    data = json.loads(_strip_fences(raw))
    return {"english_summary": str(data.get("english_summary", "")),
            "vernacular_summary": str(data.get("vernacular_summary", ""))}
