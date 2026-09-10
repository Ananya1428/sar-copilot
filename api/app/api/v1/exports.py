from fastapi import APIRouter

router = APIRouter()


@router.get("/")
def list_exports():
    """Placeholder — carries no real data yet, so left intentionally public
    for now. Form 111 / PDF export adapters (blueprint §11.2, §15.2) arrive
    once narratives exist; when they do, RBAC §11.3 "Sign off / file" and
    the §11.2 API table both say officer-only, and that real endpoint must
    be gated with require_role("officer") at that point."""
    return {"detail": "not implemented yet", "resource": "exports"}
