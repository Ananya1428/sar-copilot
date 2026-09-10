from collections.abc import Generator

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.domain.auth.security import TokenError, decode_token
from app.domain.auth.users import get_user_by_id
from app.models.user import User

_bearer_scheme = HTTPBearer(auto_error=False)


def get_db() -> Generator[Session, None, None]:
    """DB session dependency (blueprint §11.1)."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Real JWT auth (blueprint §11.3, Part 8a) — replaces the Part 1-7
    stub that always returned a fake analyst. Decodes the bearer token,
    loads the User it names, and 401s on anything short of a valid,
    unexpired access token naming an active user."""
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None:
        raise unauthorized
    try:
        payload = decode_token(credentials.credentials, expected_type="access")
    except TokenError as exc:
        unauthorized.detail = str(exc)
        raise unauthorized from exc

    user = get_user_by_id(db, payload["sub"])
    if user is None or not user.is_active:
        unauthorized.detail = "User not found or inactive"
        raise unauthorized
    return user


def require_role(*roles: str):
    """Role-gate factory enforcing blueprint §11.3's RBAC matrix. Each call
    site passes the exact set of roles that matrix allows for that action —
    deliberately explicit allow-lists rather than a min-role hierarchy,
    since the matrix isn't strictly ordered (e.g. Admin may run detection
    but may not edit narratives, while Analyst is the reverse)."""

    def _guard(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role for this action")
        return user

    return _guard
