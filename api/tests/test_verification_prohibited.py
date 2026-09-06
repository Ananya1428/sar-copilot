"""Check 4 — prohibited content."""

from app.domain.verification.prohibited import check_prohibited


def test_clean_sentence_passes():
    result = check_prohibited([{"text": "The customer's observed volume exceeded the expected profile.", "section": "why"}])
    assert result.passed


def test_legal_conclusion_is_caught():
    result = check_prohibited([{"text": "The subject committed money laundering.", "section": "how"}])
    assert not result.passed
    assert any(v.token == "committed money laundering" for v in result.violations)


def test_speculation_is_caught():
    result = check_prohibited([{"text": "The subject likely intended to conceal the source of funds.", "section": "why"}])
    assert not result.passed


def test_system_self_reference_is_caught():
    result = check_prohibited([{"text": "The anomaly score flagged this account for review.", "section": "why"}])
    assert not result.passed


def test_judgemental_language_is_caught():
    result = check_prohibited([{"text": "This is clearly suspicious behaviour.", "section": "why"}])
    assert not result.passed


def test_bare_suspicious_is_not_banned():
    """The word "suspicious" alone is legitimate SAR vocabulary — only the
    judgemental intensifier combinations are prohibited."""
    result = check_prohibited([{"text": "This report describes the basis for suspicion of suspicious activity.", "section": "why"}])
    assert result.passed
