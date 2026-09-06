"""Engine orchestration: section-scoping and retry/fallback, driven by a
controlled mock LLM client — no real Ollama needed for these."""

import json
from unittest.mock import MagicMock

from app.domain.narrative.engine import NarrativeEngine
from app.domain.narrative.llm_client import CompletionResult
from tests.narrative_factories import make_sample_pack


def _good_response(evidence_keys: list[str]) -> str:
    return json.dumps({"sentences": [{"text": "A grounded sentence.", "evidence_keys": evidence_keys}]})


def _evidence_block(prompt: str) -> str:
    """Isolates the EVIDENCE json from a rendered section prompt, excluding
    the ALLOWED_ENTITIES/NUMBERS/DATES lines — those are deliberately
    pack-wide (blueprint §13.4's own section_why.txt example includes them
    globally too), so asserting section-scoping must look only at EVIDENCE."""
    start = prompt.index("EVIDENCE:")
    end = prompt.index("ALLOWED_ENTITIES:")
    return prompt[start:end]


def test_section_scoping_restricts_evidence_sent_to_each_section():
    pack = make_sample_pack()
    mock_llm = MagicMock()
    mock_llm.model_id = "mock-model"

    seen_prompts: list[str] = []

    def fake_complete(system, user, temperature, seed, response_format, max_tokens):
        seen_prompts.append(user)
        return CompletionResult(ok=True, text=_good_response(["subject.primary.legal_name"]))

    mock_llm.complete.side_effect = fake_complete

    engine = NarrativeEngine(llm=mock_llm)
    engine.generate(pack, mode="HYBRID", seed=1)

    who_prompts = [p for p in seen_prompts if "SECTION: Subject identification" in p]
    what_when_prompts = [p for p in seen_prompts if "SECTION: Activity description" in p]
    assert who_prompts and what_when_prompts

    who_evidence = _evidence_block(who_prompts[0])
    what_when_evidence = _evidence_block(what_when_prompts[0])

    # "who" only requires `subjects` — subject data present, transaction refs absent.
    assert "Rajesh Mehta" in who_evidence
    assert "TXN-0001" not in who_evidence

    # "what_when" only requires `transactions` + `aggregates` — the reverse.
    assert "TXN-0001" in what_when_evidence
    assert "Rajesh Mehta" not in what_when_evidence


def test_invalid_json_on_first_attempt_triggers_retry_then_succeeds():
    pack = make_sample_pack()
    mock_llm = MagicMock()
    mock_llm.model_id = "mock-model"

    def fake_complete(system, user, temperature, seed, response_format, max_tokens):
        # engine's first attempt uses seed == base seed (1); retry uses seed + 1.
        if seed == 1:
            return CompletionResult(ok=True, text="not valid json")
        return CompletionResult(ok=True, text=_good_response(["subject.primary.legal_name"]))

    mock_llm.complete.side_effect = fake_complete

    engine = NarrativeEngine(llm=mock_llm, max_attempts=3)
    result = engine.generate(pack, mode="HYBRID", seed=1)

    assert result.mode == "HYBRID"
    assert result.attempts == 2
    assert result.seed == 2


def test_insufficient_evidence_response_triggers_retry():
    pack = make_sample_pack()
    mock_llm = MagicMock()
    mock_llm.model_id = "mock-model"

    def fake_complete(system, user, temperature, seed, response_format, max_tokens):
        if seed == 1:
            return CompletionResult(ok=True, text="INSUFFICIENT_EVIDENCE")
        return CompletionResult(ok=True, text=_good_response(["subject.primary.legal_name"]))

    mock_llm.complete.side_effect = fake_complete

    engine = NarrativeEngine(llm=mock_llm, max_attempts=3)
    result = engine.generate(pack, mode="HYBRID", seed=1)

    assert result.mode == "HYBRID"
    assert result.attempts == 2


def test_sentence_with_no_evidence_keys_is_rejected_as_structural_failure():
    pack = make_sample_pack()
    mock_llm = MagicMock()
    mock_llm.model_id = "mock-model"

    unsupported = json.dumps({"sentences": [{"text": "An ungrounded claim.", "evidence_keys": []}]})

    def fake_complete(system, user, temperature, seed, response_format, max_tokens):
        if seed == 1:
            return CompletionResult(ok=True, text=unsupported)
        return CompletionResult(ok=True, text=_good_response(["subject.primary.legal_name"]))

    mock_llm.complete.side_effect = fake_complete

    engine = NarrativeEngine(llm=mock_llm, max_attempts=3)
    result = engine.generate(pack, mode="HYBRID", seed=1)

    assert result.attempts == 2


def test_exhausting_all_attempts_falls_back_to_template():
    pack = make_sample_pack()
    mock_llm = MagicMock()
    mock_llm.model_id = "mock-model"
    mock_llm.complete.return_value = CompletionResult(ok=True, text="not valid json")

    engine = NarrativeEngine(llm=mock_llm, max_attempts=2)
    result = engine.generate(pack, mode="HYBRID", seed=1)

    assert result.mode == "TEMPLATE_FALLBACK"
    assert result.narrative_text.strip()
    assert "failed after 2 attempt" in result.notes[-1]


def test_freeform_mode_makes_a_single_call():
    pack = make_sample_pack()
    mock_llm = MagicMock()
    mock_llm.model_id = "mock-model"
    mock_llm.complete.return_value = CompletionResult(ok=True, text=_good_response(["subject.primary.legal_name"]))

    engine = NarrativeEngine(llm=mock_llm)
    result = engine.generate(pack, mode="FREEFORM", seed=1)

    assert result.mode == "FREEFORM"
    assert mock_llm.complete.call_count == 1
