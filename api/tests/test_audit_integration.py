"""Integration test: the full pipeline (generate -> detect -> assemble ->
evidence -> narrative) writes audit records for each stage, in order, with
correct prev_hash linkage — and verify_chain() confirms the resulting
chain is intact."""

from datetime import UTC, datetime

from app.domain.audit.ledger import AuditLedger
from app.domain.detection.orchestrator import run_detection
from app.domain.evidence.builder import build_evidence_pack, persist_evidence_pack
from app.domain.evidence.case_assembly import assemble_cases
from app.domain.ingestion.synthetic import generate_dataset
from app.domain.narrative.engine import NarrativeEngine, persist_narrative
from app.models import Case
from app.models.audit import AuditRecord


def test_full_pipeline_produces_an_ordered_intact_audit_chain(db_session, tmp_path):
    test_start = datetime.now(UTC)

    generate_dataset(db_session, n_accounts=60, days=90, seed=123, ground_truth_path=tmp_path / "gt.json")
    db_session.flush()

    run_detection(db_session)
    db_session.flush()

    assemble_cases(db_session)
    db_session.flush()

    case = (
        db_session.query(Case)
        .filter(Case.opened_at >= test_start)
        .order_by(Case.opened_at.desc())
        .first()
    )
    assert case is not None

    pack = build_evidence_pack(db_session, case)
    pack_row = persist_evidence_pack(db_session, case, pack)

    engine = NarrativeEngine()
    result = engine.generate(pack, mode="TEMPLATE", seed=42)
    persist_narrative(db_session, case, pack_row, result)
    db_session.flush()

    records = (
        db_session.query(AuditRecord)
        .filter(AuditRecord.case_id == case.id)
        .order_by(AuditRecord.occurred_at.asc())
        .all()
    )

    actions = [r.action for r in records]
    assert actions == ["CASE_OPENED", "EVIDENCE_BUILT", "NARRATIVE_GENERATED"]

    expected_prev = "0" * 64
    for record in records:
        assert record.prev_hash == expected_prev
        expected_prev = record.record_hash

    result = AuditLedger(db_session).verify_chain(case.id)
    assert result == {"valid": True, "broken_at": None, "reason": None}
