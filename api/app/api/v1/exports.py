from fastapi import APIRouter

router = APIRouter()


@router.get("/")
def list_exports():
    """Placeholder. Form 111 / PDF export adapters (blueprint §11.2, §15.2)
    arrive once narratives exist."""
    return {"detail": "not implemented yet", "resource": "exports"}
