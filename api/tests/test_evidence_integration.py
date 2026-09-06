"""End-to-end: Part 1's generator -> Part 2's detection -> Part 3's case
assembly + evidence build, on a fresh dataset.

Scoped to `Case.opened_at >= test_start` throughout, not whole-table
queries — the live dev Postgres this runs against can already hold Case
rows committed by earlier manual `assemble-cases` / `build-evidence` CLI
runs (see test_case_assembly.py's docstring for the same discipline)."""

from datetime import UTC, datetime

from app.domain.detection.orchestrator import run_detection
from app.domain.evidence.builder import build_evidence_pack
from app.domain.evidence.case_assembly import assemble_cases
from app.domain.ingestion.synthetic import generate_dataset
from app.models import Alert, Case


def test_full_pipeline_opens_a_case_with_matching_typology_evidence(db_session, tmp_path):
    test_start = datetime.now(UTC)

    generate_dataset(db_session, n_accounts=60, days=90, seed=123, ground_truth_path=tmp_path / "gt.json")
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
    assert len(pack.subjects) == 1
    assert len(pack.transactions) > 0
    assert len(pack.typologies) > 0

    fired_codes = {a.rule_code for a in db_session.query(Alert).filter(Alert.case_id == case.id).all()}
    pack_codes = {t.code for t in pack.typologies}
    assert pack_codes == fired_codes
    assert len(pack_codes) > 0
