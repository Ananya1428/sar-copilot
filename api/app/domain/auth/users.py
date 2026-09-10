"""User lookup/creation (blueprint §11.3, Part 8a). No self-signup UI
exists — accounts are created via `python -m app.cli create-user` or the
`seed` command's demo users."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.auth.security import hash_password, verify_password
from app.models.user import User

VALID_ROLES = {"analyst", "reviewer", "officer", "admin"}


def get_user_by_id(db: Session, user_id: str) -> User | None:
    try:
        uid = uuid.UUID(str(user_id))
    except ValueError:
        return None
    return db.get(User, uid)


def get_user_by_email(db: Session, email: str) -> User | None:
    return db.scalars(select(User).where(User.email == email)).first()


def create_user(db: Session, *, email: str, password: str, full_name: str, role: str = "analyst") -> User:
    if role not in VALID_ROLES:
        raise ValueError(f"invalid role {role!r}; must be one of {sorted(VALID_ROLES)}")
    user = User(email=email, hashed_password=hash_password(password), full_name=full_name, role=role)
    db.add(user)
    db.flush()
    return user


def authenticate_user(db: Session, email: str, password: str) -> User | None:
    """Returns None for both "no such user" and "wrong password" — the
    caller (POST /auth/login) must not distinguish the two in its response,
    or it leaks which emails have accounts."""
    user = get_user_by_email(db, email)
    if user is None or not verify_password(password, user.hashed_password):
        return None
    return user
