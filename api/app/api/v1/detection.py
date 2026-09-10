from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.deps import get_current_user, get_db, require_role
from app.domain.detection.orchestrator import run_detection
from app.models.user import User

router = APIRouter()


@router.get("/")
def list_detection_runs(_user: User = Depends(get_current_user)):
    """Placeholder — a persisted history of detection runs (as opposed to
    triggering one) arrives once Part 3's case assembly needs it. RBAC
    §11.3 "View case"-equivalent: any authenticated role."""
    return {"detail": "not implemented yet", "resource": "detection"}


@router.post("/run")
def trigger_detection_run(db: Session = Depends(get_db), _user: User = Depends(require_role("admin"))):
    """Runs the detection layer synchronously (blueprint §11.2 lists this
    as async-via-Celery; Part 3 can move it onto a worker — a sync call is
    fine for a batch job over this dataset's size, per the Part 2 brief).
    RBAC §11.3 "Run detection batch": admin only."""
    summary = run_detection(db)
    db.commit()
    return summary
