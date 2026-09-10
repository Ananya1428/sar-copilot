import difflib
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.deps import get_current_user, get_db
from app.domain.audit.ledger import AuditLedger
from app.domain.evidence.schema import EvidencePack as EvidencePackSchema
from app.domain.narrative.engine import _next_narrative_version
from app.domain.verification.pipeline import Verifier
from app.models.evidence import EvidencePack as EvidencePackRow
from app.models.narrative import Narrative
from app.models.narrative import NarrativeSentence as NarrativeSentenceRow
from app.models.verification import VerificationReport as VerificationReportRow

router = APIRouter()


def _parse_uuid(value: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid narrative id") from None


def _get_narrative_or_404(db: Session, narrative_id: str) -> Narrative:
    nid = _parse_uuid(narrative_id)
    narrative = db.get(Narrative, nid)
    if narrative is None:
        raise HTTPException(status_code=404, detail="narrative not found")
    return narrative


def _latest_report(db: Session, narrative_id: uuid.UUID) -> VerificationReportRow | None:
    return db.scalars(
        select(VerificationReportRow)
        .where(VerificationReportRow.narrative_id == narrative_id)
        .order_by(VerificationReportRow.created_at.desc())
    ).first()


def _narrative_dict(db: Session, narrative: Narrative) -> dict:
    sentences = sorted(narrative.sentences, key=lambda s: s.ordinal)
    return {
        "id": str(narrative.id),
        "pack_id": str(narrative.pack_id),
        "version": narrative.version,
        "generation_mode": narrative.generation_mode,
        "model_id": narrative.model_id,
        "prompt_version": narrative.prompt_version,
        "seed": narrative.seed,
        "verified": narrative.verified,
        "body": narrative.body,
        "sentences": [
            {
                "ordinal": s.ordinal,
                "text": s.text,
                "section": s.w_category,
                "evidence_keys": s.evidence_keys,
                "grounding_score": float(s.grounding_score) if s.grounding_score is not None else None,
            }
            for s in sentences
        ],
    }


@router.get("/{narrative_id}")
def get_narrative(narrative_id: str, db: Session = Depends(get_db)):
    """Returns a narrative with its sentences and per-sentence evidence_keys."""
    narrative = _get_narrative_or_404(db, narrative_id)
    return _narrative_dict(db, narrative)


class SentenceEdit(BaseModel):
    text: str
    section: str | None = None
    evidence_keys: list[str] = []


class NarrativePatchRequest(BaseModel):
    sentences: list[SentenceEdit]


@router.patch("/{narrative_id}")
def edit_narrative(
    narrative_id: str,
    body: NarrativePatchRequest,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """blueprint §11.2 PATCH /narratives/{id} — an analyst's edited
    sentences become a NEW Narrative row (next version, same pack_id),
    re-verified through the same pipeline Part 5 built, with a
    NARRATIVE_EDITED audit record carrying the before/after diff."""
    narrative = _get_narrative_or_404(db, narrative_id)
    pack_row = db.get(EvidencePackRow, narrative.pack_id)
    if pack_row is None:
        raise HTTPException(status_code=404, detail="evidence pack for this narrative no longer exists")
    pack = EvidencePackSchema.model_validate(pack_row.payload)

    sentences = [{"text": s.text, "section": s.section, "evidence_keys": s.evidence_keys} for s in body.sentences]
    if not sentences:
        raise HTTPException(status_code=400, detail="at least one sentence is required")

    report = Verifier().verify(sentences, pack)

    version = _next_narrative_version(db, pack_row.case_id)
    new_narrative = Narrative(
        pack_id=narrative.pack_id,
        version=version,
        body="\n\n".join(s["text"] for s in sentences),
        generation_mode=narrative.generation_mode,
        model_id=narrative.model_id,
        prompt_version=narrative.prompt_version,
        seed=narrative.seed,
        verified=report.passed,
    )
    db.add(new_narrative)
    db.flush()

    sentence_scores = report.checks["entailment"].details.get("sentence_scores", {})
    for idx, sentence in enumerate(sentences):
        db.add(
            NarrativeSentenceRow(
                narrative_id=new_narrative.id,
                ordinal=idx + 1,
                text=sentence["text"],
                w_category=sentence.get("section"),
                evidence_keys=sentence.get("evidence_keys") or [],
                grounding_score=sentence_scores.get(idx),
            )
        )

    db.add(
        VerificationReportRow(
            narrative_id=new_narrative.id,
            passed=report.passed,
            checks=report.to_jsonable(),
            overall_score=report.overall_score,
        )
    )
    db.flush()

    diff_lines = list(
        difflib.unified_diff(
            narrative.body.splitlines(),
            new_narrative.body.splitlines(),
            fromfile=f"v{narrative.version}",
            tofile=f"v{new_narrative.version}",
            lineterm="",
        )
    )
    AuditLedger(db).append(
        case_id=pack_row.case_id,
        actor_id=user["id"],
        action="NARRATIVE_EDITED",
        before_state={"id": str(narrative.id), "version": narrative.version, "body": narrative.body},
        after_state={"id": str(new_narrative.id), "version": new_narrative.version, "body": new_narrative.body},
        metadata={
            "diff": diff_lines,
            "verification": {"passed": report.passed, "overall_score": float(report.overall_score)},
        },
    )

    db.commit()
    return _narrative_dict(db, new_narrative)


@router.get("/{narrative_id}/diff/{other_version}")
def diff_narrative(narrative_id: str, other_version: int, db: Session = Depends(get_db)):
    """blueprint §11.2 GET /narratives/{id}/diff/{v} — both versions'
    bodies/sentences, a line diff between them, and each version's
    verification score. `other_version` is a version NUMBER, resolved
    against the same case's narrative history (versions increment per
    case, not per evidence pack — see engine.py's _next_narrative_version)."""
    narrative = _get_narrative_or_404(db, narrative_id)
    pack_row = db.get(EvidencePackRow, narrative.pack_id)
    if pack_row is None:
        raise HTTPException(status_code=404, detail="evidence pack for this narrative no longer exists")

    other = db.scalars(
        select(Narrative)
        .join(EvidencePackRow, Narrative.pack_id == EvidencePackRow.id)
        .where(EvidencePackRow.case_id == pack_row.case_id, Narrative.version == other_version)
    ).first()
    if other is None:
        raise HTTPException(status_code=404, detail=f"version {other_version} not found for this case")

    def _versioned(n: Narrative) -> dict:
        report = _latest_report(db, n.id)
        sentences = sorted(n.sentences, key=lambda s: s.ordinal)
        return {
            "id": str(n.id),
            "version": n.version,
            "body": n.body,
            "sentences": [
                {"ordinal": s.ordinal, "text": s.text, "section": s.w_category, "evidence_keys": s.evidence_keys}
                for s in sentences
            ],
            "verification": (
                {"passed": report.passed, "overall_score": float(report.overall_score)} if report is not None else None
            ),
        }

    diff_lines = list(
        difflib.unified_diff(
            other.body.splitlines(),
            narrative.body.splitlines(),
            fromfile=f"v{other.version}",
            tofile=f"v{narrative.version}",
            lineterm="",
        )
    )

    return {
        "case_id": str(pack_row.case_id),
        "this_version": _versioned(narrative),
        "other_version": _versioned(other),
        "diff": diff_lines,
    }
