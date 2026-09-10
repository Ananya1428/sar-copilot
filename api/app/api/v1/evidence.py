import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.deps import get_db
from app.models.evidence import EvidencePack as EvidencePackRow

router = APIRouter()


@router.get("/{pack_id}")
def get_evidence_pack(pack_id: str, db: Session = Depends(get_db)):
    """Fetch a specific EvidencePack by id, not just "latest for a case"
    (api/v1/cases.py's GET .../evidence only ever returns the newest one).
    A case can have more than one pack once evidence is rebuilt — packs
    are immutable/versioned (blueprint §9.2 P3) — and a narrative generated
    against an older pack still needs its own exact pack fetchable by id
    for anything (like the frontend's Verification Detail screen) that
    wants the evidence a specific narrative version actually used."""
    try:
        pid = uuid.UUID(pack_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid pack id") from None

    row = db.get(EvidencePackRow, pid)
    if row is None:
        raise HTTPException(status_code=404, detail="evidence pack not found")
    return row.payload
