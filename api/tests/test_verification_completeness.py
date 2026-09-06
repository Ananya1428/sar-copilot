"""Check 6 — completeness."""

from app.domain.verification.completeness import check_completeness
from eval.adversarial_cases import base_sentences
from tests.narrative_factories import make_sample_pack


def test_full_narrative_passes():
    pack = make_sample_pack()
    result = check_completeness(base_sentences(), pack)
    assert result.passed


def test_missing_section_is_flagged():
    pack = make_sample_pack()
    sentences = [s for s in base_sentences() if s["section"] != "why"]
    result = check_completeness(sentences, pack)
    assert not result.passed
    assert any("why" in v.message for v in result.violations)


def test_unmentioned_typology_is_flagged():
    pack = make_sample_pack()
    sentences = [s for s in base_sentences() if s["section"] != "how"]
    sentences.append({"section": "how", "text": "The activity mechanics are described here.", "evidence_keys": []})
    result = check_completeness(sentences, pack)
    assert not result.passed
    assert any("STRUCTURING" in v.message for v in result.violations)
