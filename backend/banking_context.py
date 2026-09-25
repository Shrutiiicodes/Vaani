import os

BANK_NAME = os.getenv("BANK_NAME", "Demo Bank")

# Customer languages: name (as Whisper reports it) -> ISO-639-1 code.
# Odia is handled by the text pipeline, but Whisper cannot transcribe it and
# no TTS voice exists for it, so it is deliberately absent here.
LANGUAGES = {
    "hindi": "hi", "tamil": "ta", "telugu": "te", "marathi": "mr",
    "bengali": "bn", "gujarati": "gu", "kannada": "kn", "english": "en",
}

BANKING_SYSTEM_PROMPT = f"""
You are an expert banking assistant for {BANK_NAME} branches in India.
You help staff communicate with customers in their native language.

Your responsibilities:
1. Translate customer speech accurately into English for staff
2. Extract banking intent and a structured object of entities (names, amounts, account numbers, etc.)
3. Suggest the correct counter for rerouting
4. Provide a step-by-step process guide for the employee
5. Perform numerical calculations (EMI, FD/RD maturity) using the bank's predefined rates

CRITICAL banking terms — never mistranslate these:
- KYC (Know Your Customer) = identity verification process
- CIBIL Score = credit score in India
- NACH = National Automated Clearing House (auto-debit mandate)
- NPA = Non-Performing Asset (bad loan)
- FD = Fixed Deposit, RD = Recurring Deposit
- EMI = Equated Monthly Installment
- NEFT/RTGS/IMPS = fund transfer modes
- Jan Dhan = PM Jan Dhan Yojana (basic savings scheme)
- Passbook = physical transaction record book
- Cheque bounce = insufficient funds rejection

When translating TO English: be literal but natural. Preserve numbers, account types, amounts exactly.
When translating FROM English to vernacular: use simple, friendly language a rural customer understands.
Never add information that wasn't in the original. Never omit amounts or account details.
"""

INTENT_CATEGORIES = [
    "account_opening", "balance_enquiry", "cash_transaction", "fd_rd_enquiry",
    "loan_enquiry", "kyc_update", "complaint", "fund_transfer",
    "account_closure", "nomination_update", "cheque_services",
    "mudra_loan", "kisan_credit_card", "debit_card_services",
    "tax_certificate_request", "other"
]

COUNTERS = {
    "inquiry_desk": "Inquiry Desk (General enquiries)",
    "cash_counter": "Cash Counter (Withdrawals, Deposits, Currency Change)",
    "service_counter": "Service Counter (Passbook, Cheques, Account updates, Locker, Remittance)",
    "investment_counter": "Investment Counter (Mutual Funds, FDs, Investments)",
    "specialized_counter": "Specialized Counter (DMAT, LOAN, FOREX, TRADE, INSURANCE)",
    "operational_supervisor": "Operational Supervisor (Escalations, Detailed Process Follow-ups)",
    "branch_manager": "Branch Manager (High Value Transactions, HNI, Final Escalations)"
}

# Counter for each intent. Routing is branch policy, so it lives in a table rather
# than being left to the LLM (which sent complaints to the service counter).
# "other" has no entry: the LLM's suggestion is used there.
INTENT_COUNTERS = {
    "account_opening": "service_counter",
    "balance_enquiry": "inquiry_desk",
    "cash_transaction": "cash_counter",
    "fd_rd_enquiry": "investment_counter",
    "loan_enquiry": "specialized_counter",
    "mudra_loan": "specialized_counter",
    "kisan_credit_card": "specialized_counter",
    "kyc_update": "service_counter",
    "complaint": "operational_supervisor",
    "fund_transfer": "service_counter",
    "account_closure": "service_counter",
    "nomination_update": "service_counter",
    "cheque_services": "service_counter",
    "debit_card_services": "service_counter",
    "tax_certificate_request": "service_counter",
}

PROCESS_GUIDES = {
    "account_opening": ["Ask for Aadhaar card and PAN card", "Ask for passport-size photograph", "Ask if mobile number is linked to Aadhaar", "Fill account opening form (AOF)", "Collect minimum balance (₹500 for basic savings)"],
    "balance_enquiry": ["Ask for account number or passbook", "Verify identity (ID proof or signature)", "Share balance or print passbook entries", "Suggest mobile banking / missed-call balance for next time"],
    "cash_transaction": ["Ask whether it is a withdrawal or a deposit", "Withdrawal: collect withdrawal slip or cheque and verify signature", "Deposit: collect pay-in slip, count and verify notes", "For cash above ₹50,000: collect PAN (or Form 60)", "Update passbook or hand over the receipt"],
    "kyc_update": ["Ask for current Aadhaar card", "Ask for PAN card if available", "Verify address — ask for address proof if changed", "Fill KYC update form", "Inform customer: processing takes 2–3 working days"],
    "loan_enquiry": ["Ask for type of loan: home, personal, gold, kisan, vehicle", "Ask for monthly income or salary slip", "Ask for existing loans or EMIs", "Check CIBIL score eligibility", "Share interest rate and EMI calculator result"],
    "fd_rd_enquiry": ["Ask for tenure preference (6 months to 10 years)", "Share current interest rate", "Ask for amount to be invested", "Confirm nomination details", "Ask if auto-renewal is required"],
    "complaint": ["Listen and note the issue in the customer's words", "Ask for account number and transaction date / reference", "Register the complaint in the grievance system", "Share the complaint reference number", "Escalate to the operational supervisor if unresolved"],
    "fund_transfer": ["Ask for beneficiary account number and IFSC", "Confirm transfer amount", "Ask for transfer mode: NEFT / RTGS / IMPS", "Verify sender's account balance", "Collect transfer form or use net banking"],
    "account_closure": ["Ask for the reason for closure (try to retain)", "Collect passbook, unused cheque leaves and debit card", "Fill account closure form with signature", "Settle balance by cash (small amounts) or transfer", "Close linked standing instructions and mandates"],
    "cheque_services": ["Ask for type: new chequebook / stop payment / cheque status", "Verify account number and CIF", "For stop payment: collect cheque number and reason", "For new chequebook: confirm delivery address"],
    "nomination_update": ["Ask for nominee name, relationship, date of birth", "Ask for nominee Aadhaar or ID proof", "Fill nomination form (DA-1)", "Get customer signature", "Update in CBS system"],
    "mudra_loan": ["Ask for business type and loan amount needed (Shishu <50k, Kishore 50k-5L, Tarun 5L-10L)", "Ask for business proof or registration", "Ask for last 6 months bank statement", "Check existing loan obligations", "Fill Mudra loan application form"],
    "kisan_credit_card": ["Ask for land ownership proof or lease agreement", "Ask for crop details and cultivation area", "Ask for last season's income proof", "Check existing agricultural loans", "Fill KCC application form"],
    "debit_card_services": ["Ask for type: new card / block card / PIN change / upgrade", "Verify customer identity with Aadhaar OTP", "For block: confirm card number last 4 digits", "For new card: confirm address for delivery"],
    "tax_certificate_request": ["Ask for account type: FD / savings / loan", "Ask for financial year needed", "Verify PAN linked to account", "Check if Form 15G/15H submitted", "Generate TDS certificate from CBS"]
}

FORM_TEMPLATES = {
    "account_opening": ["full_name", "dob", "gender", "father_name", "mother_name", "address", "mobile", "email", "aadhaar_number", "pan_number", "occupation", "annual_income", "account_type", "nominee_name", "nominee_relation", "nominee_dob"],
    "kyc_update": ["account_number", "full_name", "new_address", "mobile", "email", "aadhaar_number", "pan_number"],
    "loan_application": ["applicant_name", "dob", "mobile", "loan_type", "loan_amount", "tenure_months", "monthly_income", "employment_type", "existing_emis", "property_address"],
    "fund_transfer": ["sender_account", "beneficiary_name", "beneficiary_account", "ifsc_code", "amount", "transfer_mode", "remarks", "transfer_date"],
    "fd_opening": ["account_number", "deposit_amount", "tenure_months", "interest_payout_mode", "auto_renewal", "nominee_name"]
}

# Which form the staff should see for an intent.
INTENT_FORMS = {
    "account_opening": "account_opening",
    "kyc_update": "kyc_update",
    "loan_enquiry": "loan_application",
    "mudra_loan": "loan_application",
    "kisan_credit_card": "loan_application",
    "fund_transfer": "fund_transfer",
    "fd_rd_enquiry": "fd_opening",
}

# ── Indicative rates (demo values, not any real bank's card rates) ────────────
# The frontend renders these via /api/rates, so this is the single source.
LOAN_RATES = {  # category -> (display label, % p.a.)
    "home_loan": ("Home Loan", 8.50),
    "personal_loan": ("Personal Loan", 11.50),
    "vehicle_loan": ("Vehicle Loan", 8.80),
    "education_loan": ("Education Loan", 8.50),
    "gold_loan": ("Gold Loan", 9.00),
    "msme": ("MSME / Business", 9.50),
    "mudra": ("Mudra (Shishu)", 9.50),
    "kcc": ("Kisan Credit Card", 7.00),
}
DEFAULT_LOAN_RATE = 10.0

# Free-text loan categories the LLM emits -> LOAN_RATES key.
LOAN_CATEGORY_ALIASES = {
    "home": "home_loan", "housing": "home_loan", "housing_loan": "home_loan",
    "personal": "personal_loan",
    "vehicle": "vehicle_loan", "car": "vehicle_loan", "car_loan": "vehicle_loan",
    "auto": "vehicle_loan", "two_wheeler": "vehicle_loan", "bike": "vehicle_loan",
    "education": "education_loan", "student": "education_loan",
    "gold": "gold_loan",
    "business": "msme", "business_loan": "msme", "msme_loan": "msme",
    "mudra_loan": "mudra",
    "kisan": "kcc", "kisan_credit_card": "kcc", "kisan_credit": "kcc",
    "agri": "kcc", "agriculture": "kcc", "agricultural": "kcc", "farm": "kcc",
}

# FD slabs: (max tenure in days, label, general % p.a., senior citizen % p.a.).
# RD uses the same slab rate as an FD of equal tenure.
FD_SLABS = [
    (14, "7 – 14 days", 3.00, 3.50),
    (29, "15 – 29 days", 3.00, 3.50),
    (45, "30 – 45 days", 3.50, 4.00),
    (90, "46 – 90 days", 4.50, 5.00),
    (179, "91 – 179 days", 4.50, 5.00),
    (364, "180 – 364 days", 5.50, 6.00),
    (365, "1 year", 6.70, 7.20),
    (730, "1 – 2 years", 6.80, 7.30),
    (1095, "2 – 3 years", 6.50, 7.00),
    (1825, "3 – 5 years", 6.50, 7.00),
    (3650, "5 – 10 years", 6.50, 7.00),
]
