from fastapi import APIRouter

router = APIRouter()


@router.get("/")
def list_narratives():
    """Placeholder. Generation, verification, and diff endpoints
    (blueprint §11.2) arrive with the narrative engine part."""
    return {"detail": "not implemented yet", "resource": "narratives"}
