import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from translate import perform_calculations, clean_number

# ── clean_number tests ─────────────────────────────────────────────────────

def test_clean_number_rupee_string():
    assert clean_number("₹50,000") == 50000.0

def test_clean_number_indian_comma():
    assert clean_number("1,00,000") == 100000.0

def test_clean_number_shorthand_k():
    assert clean_number("50k") == 50000.0

def test_clean_number_shorthand_l():
    assert clean_number("2l") == 200000.0

def test_clean_number_plain_int():
    assert clean_number(500000) == 500000.0

def test_clean_number_none():
    assert clean_number(None) == 0.0

def test_clean_number_garbage():
    assert clean_number("abc") == 0.0

# ── EMI calculation tests ──────────────────────────────────────────────────

def test_emi_home_loan():
    result = perform_calculations({
        "type": "emi",
        "p": 5000000,   # ₹50L
        "n": 240,       # 20 years
        "loan_category": "home_loan"
    })
    assert result["type"] == "emi"
    assert result["emi"] > 0
    # At 8.5% for 20 years on ₹50L, EMI should be roughly ₹43,000
    assert 40000 < result["emi"] < 48000

def test_emi_personal_loan():
    result = perform_calculations({
        "type": "emi",
        "p": 100000,
        "n": 12,
        "loan_category": "personal_loan"
    })
    assert result["emi"] > 0
    assert result["total_interest"] > 0
    assert result["total_payment"] == result["emi"] * 12

def test_emi_zero_principal():
    result = perform_calculations({"type": "emi", "p": 0, "n": 12})
    # Should not crash, just return no emi key
    assert "emi" not in result

# ── FD calculation tests ───────────────────────────────────────────────────

def test_fd_maturity():
    result = perform_calculations({
        "type": "fd",
        "p": 100000,
        "n": 12   # 1 year
    })
    assert result["maturity"] > 100000
    assert result["interest_earned"] > 0

# ── Eligibility tests ──────────────────────────────────────────────────────

def test_eligibility():
    result = perform_calculations({
        "type": "eligibility",
        "income": 50000
    })
    assert result["max_loan"] == 3000000       # 50000 * 60
    assert result["suggested_emi_limit"] == 25000  # 50000 * 0.5