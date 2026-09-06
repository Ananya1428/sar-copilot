from fastapi import APIRouter

router = APIRouter()


@router.get("/")
def list_audit_records():
    """Placeholder. Audit trail + hash-chain verification (blueprint §15)
    arrive once cases and narratives generate real audit records."""
    return {"detail": "not implemented yet", "resource": "audit"}
