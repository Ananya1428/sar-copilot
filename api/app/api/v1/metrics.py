from collections import defaultdict

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.deps import get_db
from app.models.narrative import Narrative
from app.models.verification import VerificationReport

router = APIRouter()

CHECK_TYPES = ["numeric", "entity", "temporal", "prohibited", "entailment", "completeness"]


@router.get("/quality")
def quality_metrics(db: Session = Depends(get_db)):
    """blueprint §11.2 GET /metrics/quality — narrative quality dashboard
    data, aggregated across every Narrative + VerificationReport row."""
    narratives = db.scalars(select(Narrative)).all()
    reports = db.scalars(select(VerificationReport)).all()

    reports_by_narrative: dict = defaultdict(list)
    for report in reports:
        reports_by_narrative[report.narrative_id].append(report)

    by_mode: dict = defaultdict(lambda: {"total": 0, "unverified": 0, "passed": 0, "scores": []})
    for narrative in narratives:
        stats = by_mode[narrative.generation_mode]
        stats["total"] += 1
        narrative_reports = reports_by_narrative.get(narrative.id, [])
        if not narrative_reports:
            # No VerificationReport row at all (e.g. predates Part 5's
            # verifier being wired in by default) — this narrative was
            # never actually verified, so it must not count as a fail in
            # pass_rate_by_mode; it's excluded from both that and the mean
            # score below, using the same denominator for each.
            stats["unverified"] += 1
            continue
        # A narrative gets exactly one VerificationReport per
        # persist_narrative()/PATCH call in the current pipeline, but
        # fall back to the newest if that ever changes.
        latest = max(narrative_reports, key=lambda r: r.created_at)
        stats["scores"].append(float(latest.overall_score))
        if latest.passed:
            stats["passed"] += 1

    pass_rate_by_mode = {
        mode: (stats["passed"] / len(stats["scores"]) if stats["scores"] else None) for mode, stats in by_mode.items()
    }
    mean_score_by_mode = {
        mode: (sum(stats["scores"]) / len(stats["scores"]) if stats["scores"] else None) for mode, stats in by_mode.items()
    }
    unverified_count_by_mode = {mode: stats["unverified"] for mode, stats in by_mode.items()}

    failure_count_by_check = dict.fromkeys(CHECK_TYPES, 0)
    for report in reports:
        for check_name in CHECK_TYPES:
            check = report.checks.get(check_name)
            if check is not None and not check.get("passed", True):
                failure_count_by_check[check_name] += 1

    total_narratives = len(narratives)
    versioned_narratives = sum(1 for n in narratives if n.version > 1)
    human_edit_rate = (versioned_narratives / total_narratives) if total_narratives else None

    return {
        "narrative_count": total_narratives,
        "verification_report_count": len(reports),
        "pass_rate_by_mode": pass_rate_by_mode,
        "mean_overall_score_by_mode": mean_score_by_mode,
        "unverified_narratives_by_mode": unverified_count_by_mode,
        "failure_count_by_check": failure_count_by_check,
        "generation_latency": {
            "available": False,
            "note": (
                "generation latency is not persisted anywhere in Parts 1-5 — cli.py's "
                "generate-narrative command times it ad hoc (time.monotonic() around "
                "engine.generate()) but only prints it, never writes it to the DB. "
                "Needs new instrumentation (e.g. a column on Narrative or GenerationResult) "
                "before this can be reported for real."
            ),
        },
        "human_edit_rate": {
            "value": human_edit_rate,
            "narratives_with_version_gt_1": versioned_narratives,
            "total_narratives": total_narratives,
            "note": (
                "counts any narrative with version > 1, which includes both analyst edits "
                "(PATCH /narratives/{id}) and plain regenerations for the same case — "
                "version increments per case regardless of which produced it, so this is "
                "an upper bound on the true edit rate, not a pure edit-only signal."
            ),
        },
    }
