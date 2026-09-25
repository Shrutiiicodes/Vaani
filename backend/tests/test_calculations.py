import pytest

from translate import clean_number, deposit_rate, loan_rate, perform_calculations, to_months

# ── clean_number / to_months ──────────────────────────────────────────────────


@pytest.mark.parametrize("raw, expected", [
    ("₹50,000", 50000.0),
    ("1,00,000", 100000.0),
    ("50k", 50000.0),
    ("2l", 200000.0),
    ("50 lakhs", 5000000.0),
    ("2.5 lakh", 250000.0),
    ("1 crore", 10000000.0),
    ("Rs. 5000", 5000.0),
    ("$1200", 1200.0),
    ("20 years", 20.0),
    (500000, 500000.0),
    (None, 0.0),
    ("abc", 0.0),
])
def test_clean_number(raw, expected):
    assert clean_number(raw) == expected


@pytest.mark.parametrize("raw, expected", [("3 years", 36), ("18 months", 18), ("36", 36), (240, 240), ("5 saal", 60)])
def test_to_months(raw, expected):
    assert to_months(raw) == expected


# ── Rate lookup ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize("category, rate", [
    ("home_loan", 8.5), ("home", 8.5), ("Home Loan", 8.5),
    ("kisan", 7.0), ("kcc", 7.0), ("mudra", 9.5), ("car", 8.8),
    (None, 10.0), ("spaceship", 10.0),
])
def test_loan_rate_aliases(category, rate):
    assert loan_rate(category) == rate


@pytest.mark.parametrize("months, rate", [(1, 3.5), (6, 5.5), (12, 6.7), (24, 6.8), (36, 6.5), (60, 6.5), (200, 6.5)])
def test_deposit_rate_slabs(months, rate):
    assert deposit_rate(months) == rate


# ── EMI ───────────────────────────────────────────────────────────────────────

def test_emi_home_loan():
    result = perform_calculations({"type": "emi", "p": 5000000, "n": 240, "loan_category": "home_loan"})
    # ₹50L at 8.5% for 20 years ≈ ₹43,391
    assert 43000 < result["emi"] < 43800
    assert result["rate_used"] == 8.5


def test_emi_personal_loan():
    result = perform_calculations({"type": "emi", "p": 100000, "n": 12, "loan_category": "personal_loan"})
    assert result["total_interest"] > 0
    assert result["total_payment"] == result["emi"] * 12


def test_emi_zero_principal():
    assert "emi" not in perform_calculations({"type": "emi", "p": 0, "n": 12})


# ── Deposits ──────────────────────────────────────────────────────────────────

def test_fd_maturity():
    result = perform_calculations({"type": "fd", "p": 100000, "n": 12})
    assert result["rate_used"] == 6.7
    assert 106800 < result["maturity"] < 106900   # quarterly compounding at 6.7%


def test_rd_maturity():
    result = perform_calculations({"type": "rd", "p": 1000, "n": 12})
    assert result["total_deposited"] == 12000
    assert result["interest_earned"] > 0


# ── Eligibility ───────────────────────────────────────────────────────────────

def test_eligibility_uses_half_income_as_emi_capacity():
    result = perform_calculations({"type": "eligibility", "income": 50000})
    assert result["suggested_emi_limit"] == 25000
    # Present value of ₹25,000/month for 60 months at the personal-loan rate (11.5%)
    assert 1_130_000 < result["max_loan"] < 1_140_000


def test_eligibility_subtracts_existing_emis():
    free = perform_calculations({"type": "eligibility", "income": 50000})
    busy = perform_calculations({"type": "eligibility", "income": 50000, "existing_emi": 15000})
    assert busy["suggested_emi_limit"] == 10000
    assert busy["max_loan"] < free["max_loan"]


def test_eligibility_never_negative():
    result = perform_calculations({"type": "eligibility", "income": 20000, "existing_emi": 30000})
    assert result["max_loan"] == 0 and result["suggested_emi_limit"] == 0
