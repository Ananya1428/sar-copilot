from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings
from app.deps import get_db
from app.domain.auth.security import TokenError, create_access_token, create_refresh_token, decode_token
from app.domain.auth.users import authenticate_user, get_user_by_id
from app.models.user import User

router = APIRouter()


@router.get("/")
def auth_status():
    """Intentionally left public — a harmless placeholder carrying no data,
    kept only so the router's root path resolves to something."""
    return {"detail": "not implemented yet", "resource": "auth"}


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class RefreshRequest(BaseModel):
    refresh_token: str


def _issue_tokens(user: User) -> TokenResponse:
    return TokenResponse(
        access_token=create_access_token(str(user.id), user.role),
        refresh_token=create_refresh_token(str(user.id), user.role),
        expires_in=settings.access_token_expire_minutes * 60,
    )


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    """blueprint §11.2 POST /auth/login — email + password in, a short-lived
    access JWT plus a refresh JWT out. Deliberately gives the same 401 for
    "no such user" and "wrong password" so the response can't be used to
    enumerate which emails have accounts."""
    user = authenticate_user(db, body.email, body.password)
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password")
    return _issue_tokens(user)


@router.post("/refresh", response_model=TokenResponse)
def refresh(body: RefreshRequest, db: Session = Depends(get_db)) -> TokenResponse:
    """Stateless refresh: a longer-lived refresh JWT (type=refresh) trades
    for a new access+refresh pair. Documented gap (see LIMITATIONS.md): with
    no server-side session/token store, a refresh token can't be revoked
    before it expires — acceptable for a local demo, not for a real
    deployment (that would need a persisted, revocable token table)."""
    try:
        payload = decode_token(body.refresh_token, expected_type="refresh")
    except TokenError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

    user = get_user_by_id(db, payload["sub"])
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")
    return _issue_tokens(user)
