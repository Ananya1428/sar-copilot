import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.deps import get_db, require_role
from app.domain.audit.ledger import AuditLedger
from app.models.audit import AuditRecord
from app.models.case import Case
from app.models.user import User

router = APIRouter()


def _parse_uuid(value: str, label: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"invalid {label}") from None


def _get_case_or_404(db: Session, case_id: uuid.UUID) -> Case:
    case = db.get(Case, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="case not found")
    return case


def _record_dict(record: AuditRecord) -> dict:
    return {
        "id": str(record.id),
        "case_id": str(record.case_id),
        "actor_id": str(record.actor_id) if record.actor_id else None,
        "action": record.action,
        "before_state": record.before_state,
        "after_state": record.after_state,
        "metadata": record.audit_metadata,
        "prev_hash": record.prev_hash,
        "record_hash": record.record_hash,
        "occurred_at": record.occurred_at.isoformat(),
    }


@router.get("/case/{case_id}")
def get_case_audit_trail(
    case_id: str, db: Session = Depends(get_db), _user: User = Depends(require_role("reviewer", "officer", "admin"))
):
    """blueprint §11.2 GET /audit/case/{id} — the full audit trail for a
    case, chronological, each record's before/after/metadata. RBAC §11.3
    "View audit chain": reviewer, officer, admin — not analyst."""
    cid = _parse_uuid(case_id, "case id")
    case = _get_case_or_404(db, cid)

    records = db.scalars(
        select(AuditRecord).where(AuditRecord.case_id == case.id).order_by(AuditRecord.occurred_at.asc())
    ).all()
    return {"case_id": str(case.id), "case_ref": case.case_ref, "records": [_record_dict(r) for r in records]}


class VerifyChainRequest(BaseModel):
    case_id: str


@router.post("/verify-chain")
def verify_chain(
    body: VerifyChainRequest, db: Session = Depends(get_db), _user: User = Depends(require_role("officer", "admin"))
):
    """blueprint §11.2 POST /audit/verify-chain, §15.1 verify_chain() —
    recomputes the case's whole hash chain and reports the exact record
    where it breaks, if any. RBAC §11.3 "Verify chain integrity": officer,
    admin only."""
    cid = _parse_uuid(body.case_id, "case id")
    _get_case_or_404(db, cid)

    return AuditLedger(db).verify_chain(cid)
