BANKING_SYSTEM_PROMPT = """
You are an expert banking assistant for Union Bank of India branches.
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
    "account_opening", "balance_enquiry", "fd_rd_enquiry",
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

PROCESS_GUIDES = {
    "account_opening": ["Ask for Aadhaar card and PAN card", "Ask for passport-size photograph", "Ask if mobile number is linked to Aadhaar", "Fill account opening form (AOF)", "Collect minimum balance (₹500 for basic savings)"],
    "kyc_update": ["Ask for current Aadhaar card", "Ask for PAN card if available", "Verify address — ask for address proof if changed", "Fill KYC update form", "Inform customer: processing takes 2–3 working days"],
    "loan_enquiry": ["Ask for type of loan: home, personal, gold, kisan, vehicle", "Ask for monthly income or salary slip", "Ask for existing loans or EMIs", "Check CIBIL score eligibility", "Share interest rate and EMI calculator result"],
    "fd_rd_enquiry": ["Ask for tenure preference (6 months to 10 years)", "Share current interest rate", "Ask for amount to be invested", "Confirm nomination details", "Ask if auto-renewal is required"],
    "fund_transfer": ["Ask for beneficiary account number and IFSC", "Confirm transfer amount", "Ask for transfer mode: NEFT / RTGS / IMPS", "Verify sender's account balance", "Collect transfer form or use net banking"],
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
    "fd_opening": ["account_number", "deposit_amount", "tenure", "interest_payout_mode", "auto_renewal", "nominee_name"]
}

# ── Union Bank Official Rates (Approximate for 2026) ─────────────────────────
BANK_RATES = {
    "loan_rates": {
        "home_loan": 8.5,
        "personal_loan": 11.5,
        "vehicle_loan": 8.8,
        "gold_loan": 9.0,
        "education_loan": 8.5,
        "msme": 9.5,
        "kcc": 7.0,
        "mudra": 9.5,
        "default": 10.0
    },
    "deposit_rates": {
        "fd_1yr": 6.8,
        "fd_2yr": 7.0,
        "fd_3yr": 7.0,
        "fd_5yr": 6.5,
        "rd": 6.8
    }
}