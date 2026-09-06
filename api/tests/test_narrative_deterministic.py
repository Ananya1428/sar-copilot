"""TEMPLATE mode must work standalone, with zero LLM calls, and produce a
complete narrative built only from EvidencePack values."""

from unittest.mock import MagicMock

from app.domain.narrative.deterministic import render_all_sections
from app.domain.narrative.engine import NarrativeEngine
from tests.narrative_factories import make_sample_pack


def test_template_mode_makes_zero_llm_calls():
    pack = make_sample_pack()
    mock_llm = MagicMock()
    engine = NarrativeEngine(llm=mock_llm)

    result = engine.generate(pack, mode="TEMPLATE")

    assert result.mode == "TEMPLATE"
    assert result.model_id is None
    mock_llm.complete.assert_not_called()


def test_template_mode_covers_every_section_with_content():
    pack = make_sample_pack()  # includes a country, so "where" isn't empty
    sentences = render_all_sections(pack)

    covered = {s["section"] for s in sentences}
    from app.domain.narrative.sections import SECTION_IDS

    assert covered == set(SECTION_IDS)
    assert all(s["text"].strip() for s in sentences)


def test_template_narrative_uses_only_pack_values():
    pack = make_sample_pack()
    sentences = render_all_sections(pack)
    full_text = " ".join(s["text"] for s in sentences)

    assert "Rajesh Mehta" in full_text
    assert "CUS-4471" in full_text
    assert "ACC-88213" in full_text
    assert "17300.00" in full_text
    assert "STRUCTURING" not in full_text  # the code isn't prose; the label is
    assert "Structuring" in full_text


def test_template_sentences_carry_evidence_keys_except_static_conclusion():
    pack = make_sample_pack()
    sentences = render_all_sections(pack)

    non_conclusion = [s for s in sentences if s["section"] != "conclusion"]
    assert all(s["evidence_keys"] for s in non_conclusion)

    conclusion = [s for s in sentences if s["section"] == "conclusion"]
    assert conclusion  # still present, just evidence-free boilerplate
    assert all(s["evidence_keys"] == [] for s in conclusion)


def test_engine_falls_back_to_template_when_hybrid_mode_has_no_verifier_and_llm_fails():
    """With no LLM reachable, HYBRID must retry then fall back to
    TEMPLATE_FALLBACK rather than ever returning nothing."""
    pack = make_sample_pack()
    mock_llm = MagicMock()
    mock_llm.model_id = "mock-model"
    mock_llm.complete.return_value = MagicMock(ok=False, text=None, error="connection refused")

    engine = NarrativeEngine(llm=mock_llm, max_attempts=2)
    result = engine.generate(pack, mode="HYBRID", seed=1)

    assert result.mode == "TEMPLATE_FALLBACK"
    assert result.narrative_text.strip()
    assert mock_llm.complete.call_count > 0
