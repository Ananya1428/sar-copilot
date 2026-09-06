"""Part 5's engine-wiring requirement: confirm NarrativeEngine's
retry-then-fallback loop actually fires on a GENUINE verification
failure (a real hallucination caught by the real pipeline), not only on
a structural failure (bad JSON, missing evidence_keys — Part 4's
concern, covered in test_narrative_engine.py).

Uses a real `Verifier` (default) with an injected stub entailment
classifier, so this is deterministic and needs no model download."""

import json
from unittest.mock import MagicMock

from app.domain.narrative.engine import NarrativeEngine
from app.domain.narrative.llm_client import CompletionResult
from app.domain.verification.pipeline import Verifier
from tests.narrative_factories import make_sample_pack


def _always_entailing(premise: str, hypothesis: str) -> tuple[str, float]:
    return "entailment", 0.95


def _response(text: str, evidence_keys: list[str]) -> str:
    return json.dumps({"sentences": [{"text": text, "evidence_keys": evidence_keys}]})


def test_hallucinated_number_is_structurally_valid_but_fails_real_verification_and_triggers_retry():
    """The first attempt is well-formed JSON with a cited evidence_key —
    Part 4's structural check alone would accept it — but the number in
    the text is fabricated. The real verifier must catch that and force a
    retry; only the second (clean) attempt should be accepted."""
    pack = make_sample_pack()
    mock_llm = MagicMock()
    mock_llm.model_id = "mock-model"

    hallucinated = _response("A credit of 999999.00 was recorded.", ["transaction.TXN-0001.amount"])
    clean = _response("A credit of 8600.00 was recorded.", ["transaction.TXN-0001.amount"])

    def fake_complete(system, user, temperature, seed, response_format, max_tokens):
        return CompletionResult(ok=True, text=hallucinated if seed == 1 else clean)

    mock_llm.complete.side_effect = fake_complete

    engine = NarrativeEngine(llm=mock_llm, max_attempts=3, verifier=Verifier(entailment_classifier=_always_entailing))
    result = engine.generate(pack, mode="HYBRID", seed=1)

    assert result.mode == "HYBRID"
    assert result.attempts == 2
    assert "999999.00" not in result.narrative_text
    assert any("verification failed" in note for note in result.notes)


def test_persistent_hallucination_exhausts_retries_and_falls_back_to_template():
    pack = make_sample_pack()
    mock_llm = MagicMock()
    mock_llm.model_id = "mock-model"
    mock_llm.complete.return_value = CompletionResult(
        ok=True, text=_response("A credit of 999999.00 was recorded.", ["transaction.TXN-0001.amount"])
    )

    engine = NarrativeEngine(llm=mock_llm, max_attempts=2, verifier=Verifier(entailment_classifier=_always_entailing))
    result = engine.generate(pack, mode="HYBRID", seed=1)

    assert result.mode == "TEMPLATE_FALLBACK"
    assert "999999.00" not in result.narrative_text
    assert any("verification failed" in note for note in result.notes)
    # TEMPLATE_FALLBACK is itself verified (engine._deterministic runs the
    # verifier too) and, being structurally guaranteed grounded, must pass.
    assert result.verification_report is not None
    assert result.verification_report.passed


def test_engine_defaults_to_a_real_verifier_when_none_is_given():
    engine = NarrativeEngine(llm=MagicMock())
    assert isinstance(engine.verifier, Verifier)


def test_verifier_false_opts_out_of_verification_entirely():
    engine = NarrativeEngine(llm=MagicMock(), verifier=False)
    assert engine.verifier is None
