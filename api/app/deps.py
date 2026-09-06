from collections.abc import Generator

from sqlalchemy.orm import Session

from app.database import SessionLocal


def get_db() -> Generator[Session, None, None]:
    """DB session dependency (blueprint §11.1)."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user() -> dict:
    """Stub — real JWT auth + RBAC (blueprint §11.3) arrives in a later part."""
    return {"id": None, "email": None, "role": "analyst"}
