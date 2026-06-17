import os, json, re, math
from .models import LLMTranslationOutput
from groq import Groq
from dotenv import load_dotenv
from .banking_context import BANKING_SYSTEM_PROMPT, INTENT_CATEGORIES, PROCESS_GUIDES, COUNTERS, FORM_TEMPLATES, BANK_RATES

load_dotenv()
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

MODEL = "llama-3.3-70b-versatile"

MONEY_FOLLOWUP_EN = (
    "Are you looking to withdraw cash from your account, "
    "take a loan, or break a Fixed Deposit (FD)?"
)

MONEY_KEYWORDS = [
    "money", "cash", "paisa", "paise", "pesa", "rupee", "rupees",
    "funds", "amount", "give me", "want money", "need money",
    "chahiye", "chahie", "돈", "பணம்", "డబ్బు", "హಣ", "പണം"
]


def _strip_fences(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("```"):
        parts = raw.split("```")
        raw = parts[1] if len(parts) > 1 else raw
        if raw.startswith("json"):
            raw = raw[4:]
    return raw.strip()


def _is_money_ambiguous(text: str, intent: str, confidence: float) -> bool:
    text_lower = text.lower()
    has_money_keyword = any(kw in text_lower for kw in MONEY_KEYWORDS)
    if has_money_keyword and (intent == "other" or confidence < 0.55):
        return True
    word_count = len(text_lower.split())
    if has_money_keyword and word_count <= 6:
        return True
    return False


async def translate_customer_speech(text: str, source_lang: str, conversation_history: list | None = None, active_form_type: str | None = None) -> dict:
    convo_context = ""
    if conversation_history:
        valid_turns = [t for t in conversation_history if t.get('text')]
        convo_context = "\nConversation context so far:\n" + "\n".join([
            f"{t['role'].upper()}: {t['text']}" for t in valid_turns
        ])

    target_fields = ""
    if active_form_type and active_form_type in FORM_TEMPLATES:
        target_fields = f"\nThe employee is looking at a {active_form_type} form. Extract: {', '.join(FORM_TEMPLATES[active_form_type])}"

    prompt = f"""
The customer is speaking in {source_lang}.
Customer said: "{text}"
{convo_context}
{target_fields}

Possible intents: {', '.join(INTENT_CATEGORIES)}
Possible counters: {json.dumps(COUNTERS)}

Analyze the transcript and conversation context:
1. Translate to accurate English.
2. Detect the banking intent.
3. Extract ALL mentioned entities (names, amounts, tenures, account numbers, dates, phone numbers, pan, aadhaar, nomadic/beneficiary details, etc.).
#    - IMPORTANT: If a list of fields to "Extract" was provided above (for the form), use those EXACT names as the keys in your "entities" object
   - Look at the ENTIRE conversation context to find these values.
4. Identify calculation inputs (ONLY THE AMOUNT AND TENURE). Do NOT ask for interest rates; those are handled by the bank system.
5. If the user wants a loan, identify the LOAN TYPE (home, personal, vehicle, education, kisan, gold, mudra, msme).

Respond ONLY with a JSON object (no markdown):
{{
  "english_translation": "<translation>",
  "intent": "<intent>",
  "confidence": <confidence>,
  "suggested_counter": "<counter_id>",
  "entities": {{"account_number": "...", "full_name": "...", "amount": "...", "tenure_months": "...", "loan_type": "home|personal|..."  }},
  "calculation_inputs": {{ "type": "emi|fd|rd|eligibility|none", "p": <principal_amount>, "n": <tenure_months>, "income": <monthly_income_for_eligibility>, "loan_category": "<type>" }}
}}
"""
    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": BANKING_SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ],
        temperature=0.1
    )

    raw_res: str = ""
    try:
        raw_res = response.choices[0].message.content or ""
        parsed_json = json.loads(_strip_fences(raw_res))

        # Clean any number fields the LLM may have returned as strings
        calc = parsed_json.get("calculation_inputs", {})
        for field in ("p", "n", "income"):
            if field in calc:
                calc[field] = clean_number(calc[field])
        parsed_json["calculation_inputs"] = calc

        # Validate with Pydantic — raises ValidationError with clear field-level errors
        validated = LLMTranslationOutput(**parsed_json)
        result = validated.dict()

    except json.JSONDecodeError as e:
        print(f"JSON PARSE FAILED: {e}\nRAW: {raw_res}")
        result = LLMTranslationOutput(english_translation=text).dict()

    except Exception as e:
        print(f"LLM VALIDATION ERROR: {e}\nRAW: {raw_res}")
        result = LLMTranslationOutput(english_translation=text).dict()

    # Extract key fields from result — always defined regardless of which branch ran
    intent: str = result.get("intent", "other")
    confidence: float = result.get("confidence", 0.5)
    english: str = result.get("english_translation", text)

    # Calculation logic using BANK_RATES
    calcs = result.get("calculation_inputs", {})
    if calcs and calcs.get("type") != "none":
        # Pass the extracted loan category if present
        if not calcs.get("loan_category") and result.get("entities", {}).get("loan_type"):
            calcs["loan_category"] = result["entities"]["loan_type"]
        result["calculation_results"] = perform_calculations(calcs)

    # Form logic
    final_form_type = None
    if intent != "other":
        final_form_type = "loan_application" if intent == "loan_enquiry" else intent
    elif active_form_type:
        final_form_type = active_form_type

    if final_form_type and final_form_type in FORM_TEMPLATES:
        # Robust mapping: ensure AI keys match form fields even if AI slips up
        raw_entities = result.get("entities", {})
        prefill = {k: v for k, v in raw_entities.items()}
        
        # Common synonyms for resilient mapping
        aliases = {
            "applicant_name": ["full_name", "name", "customer_name"],
            "loan_amount": ["amount", "loan_value", "principal"],
            "deposit_amount": ["amount", "deposit_value"],
            "mobile": ["phone", "contact", "mobile_number"],
            "tenure_months": ["tenure", "duration", "period","years","months"]
        }
        
        for field in FORM_TEMPLATES[final_form_type]:
            if field in aliases:
                for alt in aliases[field]:
                    if alt in raw_entities and not prefill.get(field):
                        prefill[field] = raw_entities[alt]

        result["form_template"] = {
            "type": final_form_type, 
            "fields": FORM_TEMPLATES[final_form_type], 
            "prefill": prefill
        }

    # Clarification/Process guide logic
    if _is_money_ambiguous(english, intent, confidence) or _is_money_ambiguous(text, intent, confidence):
        result["needs_clarification"] = True
        result["follow_up_question"] = MONEY_FOLLOWUP_EN
        result["process_guide"] = []
    else:
        result["needs_clarification"] = False
        result["follow_up_question"] = None
        result["process_guide"] = PROCESS_GUIDES.get(intent, [])

    return result


def perform_calculations(inputs: dict) -> dict:
    calc_type = inputs.get("type")
    p = clean_number(inputs.get("p"))
    n = clean_number(inputs.get("n"))  # tenure in months
    income = clean_number(inputs.get("income"))
    cat = (inputs.get("loan_category") or "default").lower().replace(" ", "_")
    
    results = {"type": calc_type}

    if calc_type == "emi":
        if p > 0 and n > 0:
            # Use predefined rates from banking_context.py
            rates = BANK_RATES["loan_rates"]
            r = rates.get(cat, rates.get(f"{cat}_loan", rates["default"]))
            mr = r / 12 / 100
            emi = p * mr * math.pow(1 + mr, n) / (math.pow(1 + mr, n) - 1)
            results["emi"] = round(emi)
            results["total_payment"] = int(results["emi"]) * int(n)
            results["total_interest"] = round(results["total_payment"] - p)
            results["rate_used"] = r

    elif calc_type == "fd":
        if p > 0 and n > 0:
            rates = BANK_RATES["deposit_rates"]
            if n >= 60: r = rates["fd_5yr"]
            elif n >= 24: r = rates["fd_2yr"]
            else: r = rates["fd_1yr"]
            
            t = n / 12
            freq = 4
            maturity = p * math.pow(1 + (r / 100 / freq), freq * t)
            results["maturity"] = round(maturity)
            results["interest_earned"] = round(results["maturity"] - p)
            results["rate_used"] = r

    elif calc_type == "rd":
        if p > 0 and n > 0:
            r = BANK_RATES["deposit_rates"]["rd"]
            i = r / 400
            q = n / 3
            m = p * (math.pow(1 + i, q) - 1) / (1 - math.pow(1 + i, -1/3))
            results["maturity"] = round(m)
            results["total_deposited"] = round(p * n)
            results["interest_earned"] = round(results["maturity"] - results["total_deposited"])
            results["rate_used"] = r

    elif calc_type == "eligibility":
        results["max_loan"] = round(income * 60)
        results["suggested_emi_limit"] = round(income * 0.5)

    return results


async def translate_staff_reply(reply: str, target_lang: str) -> str:
    prompt = f"Translate staff reply: {reply} to {target_lang}. Respond with ONLY translation."
    response = client.chat.completions.create(model=MODEL, messages=[{"role": "user", "content": prompt}], temperature=0.1)
    return (response.choices[0].message.content or "").strip()


async def translate_text(text: str, target_lang: str) -> str:
    if not target_lang or target_lang.lower() in ("english", "en"): return text
    response = client.chat.completions.create(model=MODEL, messages=[{"role": "user", "content": f"Translate to {target_lang}: {text}"}], temperature=0.1)
    return (response.choices[0].message.content or "").strip()


async def generate_summary(conversation: list, customer_language: str) -> dict:
    convo_text = "\n".join([f"{turn['role'].upper()}: {turn['text']}" for turn in conversation])
    prompt = f"Summarize in English and {customer_language} (JSON keys english_summary, vernacular_summary): {convo_text}"
    response = client.chat.completions.create(model=MODEL, messages=[{"role": "user", "content": prompt}], temperature=0.2)
    return json.loads(_strip_fences(response.choices[0].message.content or ""))

def clean_number(val) -> float:
    """Strips currency symbols, commas, spaces before casting to float.
    Handles: '₹50,000', '1,00,000', '50k', '$1200', '  30  '
    Returns 0.0 if unparseable.
    """
    if val is None:
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    val = str(val).strip().lower()
    # Handle shorthand: 50k → 50000, 1.5l → 150000
    if val.endswith('k'):
        try:
            return float(val[:-1]) * 1_000
        except ValueError:
            pass
    if val.endswith('l'):
        try:
            return float(val[:-1]) * 1_00_000
        except ValueError:
            pass
    # Strip everything except digits and decimal point
    val = re.sub(r'[^\d.]', '', val)
    try:
        return float(val)
    except ValueError:
        return 0.0