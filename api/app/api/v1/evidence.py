from fastapi import APIRouter

router = APIRouter()


@router.get("/")
def list_evidence():
    """Placeholder. Evidence pack retrieval (blueprint §11.2) arrives once
    the evidence builder exists."""
    return {"detail": "not implemented yet", "resource": "evidence"}
