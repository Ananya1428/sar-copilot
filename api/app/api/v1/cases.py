import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.narratives import _narrative_dict
from app.deps import get_current_user, get_db, require_role
from app.domain.detection.scoring import band_for_score
from app.domain.evidence.builder import build_evidence_pack, persist_evidence_pack
from app.domain.evidence.case_assembly import assemble_cases
from app.domain.evidence.schema import EvidencePack as EvidencePackSchema
from app.domain.narrative.engine import NarrativeEngine, persist_narrative
from app.models.case import Case
from app.models.evidence import EvidencePack as EvidencePackRow
from app.models.user import User

router = APIRouter()


@router.post("/assemble")
def assemble_cases_endpoint(db: Session = Depends(get_db), user: User = Depends(require_role("admin"))):
    """Wires domain/evidence/case_assembly.py's assemble_cases() (blueprint
    §8 Journey B: groups HIGH/MEDIUM alerts into opened Cases), previously
    CLI-only (`python -m app.cli assemble-cases`).

    RBAC: not in blueprint §11.3's matrix (that table predates data entry
    and this endpoint). Gated the same as POST /detection/run — admin
    only — because, like that endpoint, this is a global batch operation
    over every open alert in the system, not scoped to one case/account.
    That's the same "batch" category §11.3 already reserves for admin;
    the per-entity onboarding endpoints in onboarding.py are gated
    differently (any authenticated role) for the opposite reason."""
    summary = assemble_cases(db, actor_id=user.id)
    db.commit()
    return summary


def _case_summary(case: Case) -> dict:
    score = float(case.risk_score) if case.risk_score is not None else None
    return {
        "id": str(case.id),
        "case_ref": case.case_ref,
        "status": case.status,
        "risk_score": score,
        "risk_band": band_for_score(score) if score is not None else None,
        "deadline_at": case.deadline_at.isoformat() if case.deadline_at else None,
    }


def _get_case_or_404(db: Session, case_id: str) -> Case:
    try:
        cid = uuid.UUID(case_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid case id") from None
    case = db.get(Case, cid)
    if case is None:
        raise HTTPException(status_code=404, detail="case not found")
    return case


@router.get("/")
def list_cases(db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    """blueprint §11.2 GET /cases — id, case_ref, status, risk band/score,
    deadline. RBAC §11.3 "View case": any authenticated role."""
    cases = db.scalars(select(Case).order_by(Case.deadline_at)).all()
    return [_case_summary(c) for c in cases]


@router.post("/{case_id}/evidence/rebuild")
def rebuild_evidence(case_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Builds a fresh EvidencePack for this case and persists it as a new,
    immutable row (blueprint §9.2 P3 — never overwrites a prior pack). RBAC
    §11.3 "Generate narrative": any authenticated role."""
    case = _get_case_or_404(db, case_id)
    pack = build_evidence_pack(db, case)
    persist_evidence_pack(db, case, pack, actor_id=user.id)
    db.commit()
    return pack.model_dump(mode="json")


@router.get("/{case_id}/evidence")
def get_latest_evidence(case_id: str, db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    """Returns the most recently built EvidencePack for this case. RBAC
    §11.3 "View case": any authenticated role."""
    case = _get_case_or_404(db, case_id)
    row = _latest_pack_row(db, case)
    if row is None:
        raise HTTPException(status_code=404, detail="no evidence pack built yet for this case")
    return row.payload


def _latest_pack_row(db: Session, case: Case) -> EvidencePackRow | None:
    return db.scalars(
        select(EvidencePackRow).where(EvidencePackRow.case_id == case.id).order_by(EvidencePackRow.built_at.desc())
    ).first()


@router.post("/{case_id}/narrative")
def generate_case_narrative(
    case_id: str, mode: str = "HYBRID", seed: int = 42, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    """Generates a narrative for this case (blueprint §13), reusing the
    case's latest EvidencePack if one already exists rather than building
    a new one on every call — packs are immutable, so an existing one is
    still exactly as valid as a fresh rebuild would be. RBAC §11.3
    "Generate narrative": any authenticated role."""
    case = _get_case_or_404(db, case_id)

    pack_row = _latest_pack_row(db, case)
    if pack_row is None:
        pack = build_evidence_pack(db, case)
        pack_row = persist_evidence_pack(db, case, pack, actor_id=user.id)
    else:
        pack = EvidencePackSchema.model_validate(pack_row.payload)

    engine = NarrativeEngine()
    result = engine.generate(pack, mode=mode, seed=seed)
    narrative_row = persist_narrative(db, case, pack_row, result, actor_id=user.id)
    db.commit()
    db.refresh(narrative_row)

    return {**_narrative_dict(db, narrative_row), "case_ref": case.case_ref, "notes": result.notes}
