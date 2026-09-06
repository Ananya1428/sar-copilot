"""Check 5 — semantic entailment. Uses injected stub classifiers so these
tests are deterministic and need no model download — see semantic.py's
module docstring on graceful degradation, and eval/adversarial_cases.py's
`make_stub_classifier` for why a stub is the right tool for testing
PIPELINE wiring rather than real NLI model accuracy."""

from app.domain.verification.semantic import check_entailment, grounded_items
from tests.narrative_factories import make_sample_pack


def _always(label: str, prob: float):
    def classify(premise: str, hypothesis: str) -> tuple[str, float]:
        return label, prob
    return classify


def test_grounded_items_found_by_scanning_text_not_evidence_keys():
    """The core Part 5 distinction: grounding for entailment is derived
    from the sentence TEXT, exactly like checks 1-3 — never from the
    LLM's own (possibly mismatched) evidence_keys."""
    pack = make_sample_pack()
    text = "A credit of 8600.00 was recorded for Rajesh Mehta."
    items = grounded_items(text, pack)
    keys = {item.key for item in items}
    assert "transaction.TXN-0001.amount" in keys
    assert "subject.primary.legal_name" in keys


def test_sentence_with_no_grounded_items_is_skipped_not_penalised():
    pack = make_sample_pack()
    sentences = [{"text": "This report has been prepared for retention.", "section": "conclusion", "evidence_keys": []}]
    result = check_entailment(sentences, pack, classifier=_always("contradiction", 0.0))
    assert result.passed
    assert result.score == 1.0


def test_entailed_sentence_passes():
    pack = make_sample_pack()
    sentences = [{"text": "A credit of 8600.00 was recorded.", "section": "what_when", "evidence_keys": []}]
    result = check_entailment(sentences, pack, classifier=_always("entailment", 0.95))
    assert result.passed
    assert result.score == 0.95


def test_low_entailment_probability_is_flagged():
    pack = make_sample_pack()
    sentences = [{"text": "A credit of 8600.00 was recorded.", "section": "what_when", "evidence_keys": []}]
    result = check_entailment(sentences, pack, classifier=_always("contradiction", 0.05))
    assert not result.passed
    assert result.details["sentence_scores"][0] == 0.05


def test_missing_model_degrades_gracefully_instead_of_failing():
    """Documented degradation call in semantic.py: if the real model can't
    load (no injected classifier, load raises), the check reports itself
    unavailable with a neutral score rather than blocking the pipeline."""
    import app.domain.verification.semantic as semantic_module

    original_singleton, original_error = semantic_module._classifier_singleton, semantic_module._classifier_load_error
    semantic_module._classifier_singleton = None
    semantic_module._classifier_load_error = "simulated unavailable model"
    try:
        pack = make_sample_pack()
        sentences = [{"text": "A credit of 8600.00 was recorded.", "section": "what_when", "evidence_keys": []}]
        result = check_entailment(sentences, pack, classifier=None)
        assert result.passed
        assert result.score == 1.0
        assert result.details.get("unavailable") is True
    finally:
        semantic_module._classifier_singleton = original_singleton
        semantic_module._classifier_load_error = original_error
