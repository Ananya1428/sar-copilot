"""Check 3 — temporal grounding."""

from app.domain.verification.temporal import check_temporal
from tests.narrative_factories import make_sample_pack


def test_grounded_date_within_period_passes():
    pack = make_sample_pack()
    sentences = [{"text": "The activity occurred on 2024-03-03.", "section": "what_when", "evidence_keys": []}]
    result = check_temporal(sentences, pack)
    assert result.passed


def test_fabricated_date_fails_even_with_a_plausible_looking_evidence_key():
    pack = make_sample_pack()
    sentences = [{"text": "The activity occurred on 2024-05-19.", "section": "what_when", "evidence_keys": ["aggregates.period_start"]}]
    result = check_temporal(sentences, pack)
    assert not result.passed


def test_grounded_date_outside_aggregate_period_fails_as_a_period_violation():
    """2021-06-14 is a REAL date in the pack (relationship_start), so this
    exercises the period-bounds check specifically, not simple fabrication."""
    pack = make_sample_pack()
    sentences = [{"text": "A transaction was recorded on 2021-06-14.", "section": "what_when", "evidence_keys": []}]
    result = check_temporal(sentences, pack)
    assert not result.passed
    assert any("outside the evidence period" in v.message for v in result.violations)


def test_what_when_dates_out_of_order_are_flagged():
    pack = make_sample_pack()
    sentences = [
        {"text": "A transaction occurred on 2024-03-04.", "section": "what_when", "evidence_keys": []},
        {"text": "An earlier transaction occurred on 2024-03-03.", "section": "what_when", "evidence_keys": []},
    ]
    result = check_temporal(sentences, pack)
    assert not result.passed
    assert any("chronological" in v.message for v in result.violations)
