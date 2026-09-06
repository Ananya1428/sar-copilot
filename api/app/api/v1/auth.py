from fastapi import APIRouter

router = APIRouter()


@router.get("/")
def auth_status():
    """Placeholder. JWT login/refresh (blueprint §11.2) arrives with RBAC
    enforcement in a later part."""
    return {"detail": "not implemented yet", "resource": "auth"}
