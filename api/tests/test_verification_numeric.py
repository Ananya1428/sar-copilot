"""Check 1 — numeric grounding. Confirms it scans sentence TEXT, not the
LLM's self-reported `evidence_keys` — the central distinction called out
in the Part 5 brief."""

from app.domain.verification.numeric import check_numeric
from tests.narrative_factories import make_sample_pack


def test_grounded_number_passes():
    pack = make_sample_pack()
    sentences = [{"text": "A credit of 8600.00 was recorded.", "section": "what_when", "evidence_keys": ["transaction.TXN-0001.amount"]}]
    result = check_numeric(sentences, pack)
    assert result.passed
    assert not result.violations


def test_fabricated_number_fails_even_with_a_plausible_looking_evidence_key():
    """The exact case called out in the Part 5 kickoff: a correct-looking
    evidence_key attached to a fabricated number must still fail, because
    the check never trusts evidence_keys — only the text."""
    pack = make_sample_pack()
    sentences = [{"text": "A credit of 99999.00 was recorded.", "section": "what_when", "evidence_keys": ["transaction.TXN-0001.amount"]}]
    result = check_numeric(sentences, pack)
    assert not result.passed
    assert any("99999.00" == v.token for v in result.violations)


def test_wrong_evidence_key_on_a_correct_number_still_passes():
    """The mirror case: the LLM's own evidence_keys namespace mismatch
    (Part 4's known issue) must not cause a false rejection."""
    pack = make_sample_pack()
    sentences = [{"text": "A credit of 8600.00 was recorded.", "section": "what_when", "evidence_keys": ["subjects", "legal_name"]}]
    result = check_numeric(sentences, pack)
    assert result.passed


def test_small_structural_counters_are_exempt():
    pack = make_sample_pack()
    sentences = [{"text": "The first 2 transactions occurred in March.", "section": "what_when", "evidence_keys": []}]
    result = check_numeric(sentences, pack)
    assert result.passed


def test_dates_are_not_mistaken_for_numeric_tokens():
    """2024-03-03 must not be flagged as the ungrounded number 2024 —
    dates are the temporal check's job."""
    pack = make_sample_pack()
    sentences = [{"text": "The activity occurred on 2024-03-03.", "section": "what_when", "evidence_keys": []}]
    result = check_numeric(sentences, pack)
    assert result.passed, result.violations


def test_currency_symbol_and_comma_normalisation():
    pack = make_sample_pack()
    sentences = [{"text": "A credit of $8,600.00 was recorded.", "section": "what_when", "evidence_keys": []}]
    result = check_numeric(sentences, pack)
    assert result.passed
