import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.deps import get_db
from app.models.narrative import Narrative

router = APIRouter()


@router.get("/{narrative_id}")
def get_narrative(narrative_id: str, db: Session = Depends(get_db)):
    """Returns a narrative with its sentences and per-sentence evidence_keys."""
    try:
        nid = uuid.UUID(narrative_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid narrative id") from None

    narrative = db.get(Narrative, nid)
    if narrative is None:
        raise HTTPException(status_code=404, detail="narrative not found")

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
