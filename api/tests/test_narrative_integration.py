"""Full pipeline, end to end: Part 1's generator -> Part 2's detection ->
Part 3's case assembly + evidence build -> Part 4's narrative generation
in HYBRID mode against the REAL Ollama service.

Skips (doesn't fail) if Ollama isn't reachable — see test_llm_client_ollama.py.
Scoped to `Case.opened_at >= test_start`, not whole-table queries, for the
same live-shared-DB reason as test_evidence_integration.py.
"""

from datetime import UTC, datetime

import pytest

from app.domain.detection.orchestrator import run_detection
from app.domain.evidence.builder import build_evidence_pack, persist_evidence_pack
from app.domain.evidence.case_assembly import assemble_cases
from app.domain.ingestion.synthetic import generate_dataset
from app.domain.narrative.engine import NarrativeEngine
from app.domain.narrative.llm_client import OllamaClient
from app.models import Case


def test_hybrid_narrative_against_real_ollama(db_session, tmp_path):
    llm = OllamaClient()
    probe = llm.complete(system="Reply with one word.", user="OK", temperature=0.0, seed=1, response_format=None, max_tokens=5)
    if not probe.ok:
        pytest.skip(f"Ollama not reachable: {probe.error}")

    test_start = datetime.now(UTC)

    generate_dataset(db_session, n_accounts=60, days=90, seed=321, ground_truth_path=tmp_path / "gt.json")
    db_session.flush()
    run_detection(db_session)
    db_session.flush()
    summary = assemble_cases(db_session)
    assert summary["cases_created"] > 0

    case = (
        db_session.query(Case)
        .filter(Case.opened_at >= test_start)
        .order_by(Case.opened_at.desc())
        .first()
    )
    assert case is not None

    pack = build_evidence_pack(db_session, case)
    persist_evidence_pack(db_session, case, pack)

    engine = NarrativeEngine(llm=llm)
    result = engine.generate(pack, mode="HYBRID", seed=42)

    assert result.narrative_text.strip()
    assert result.sentences
    for s in result.sentences:
        assert s["evidence_keys"], f"sentence with no evidence_keys: {s['text']!r}"
