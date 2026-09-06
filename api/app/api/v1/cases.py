from fastapi import APIRouter

router = APIRouter()


@router.get("/")
def list_cases():
    """Placeholder. Case CRUD + workflow transitions (blueprint §11.2) land
    once the detection layer and evidence pack builder exist."""
    return {"detail": "not implemented yet", "resource": "cases"}
