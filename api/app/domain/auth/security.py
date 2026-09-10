"""Password hashing + JWT issuance/verification (blueprint §11.3, Part 8a).

Library choices, documented:
- `bcrypt`, used directly rather than via passlib: passlib is unmaintained
  since 2020 and its bcrypt backend prints a version-detection warning
  against bcrypt>=4.1 (looks for a `__about__` attribute bcrypt no longer
  has). Calling bcrypt directly avoids an abstraction layer that no longer
  tracks its own dependency.
- `PyJWT` (imported as `jwt`) over python-jose: fewer moving parts for a
  single-algorithm (HS256, symmetric — one shared `JWT_SECRET`) use case,
  and a more actively maintained project.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.config import settings


class TokenError(Exception):
    """Raised for any invalid, expired, malformed, or wrong-type token."""


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed_password.encode("utf-8"))
    except ValueError:
        # Malformed hash (e.g. a row whose hashed_password was never
        # actually bcrypt output) — fail closed rather than raising.
        return False


def _create_token(*, subject: str, role: str, token_type: str, expires_delta: timedelta) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "role": role,
        "type": token_type,
        "iat": now,
        "exp": now + expires_delta,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_access_token(user_id: str, role: str) -> str:
    return _create_token(
        subject=user_id,
        role=role,
        token_type="access",
        expires_delta=timedelta(minutes=settings.access_token_expire_minutes),
    )


def create_refresh_token(user_id: str, role: str) -> str:
    return _create_token(
        subject=user_id,
        role=role,
        token_type="refresh",
        expires_delta=timedelta(days=settings.refresh_token_expire_days),
    )


def decode_token(token: str, *, expected_type: str) -> dict:
    """Decodes and validates a JWT, raising TokenError on anything short of
    a well-formed, correctly-signed, unexpired token of the expected type
    (e.g. rejects an access token presented to /auth/refresh)."""
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.ExpiredSignatureError as exc:
        raise TokenError("token has expired") from exc
    except jwt.InvalidTokenError as exc:
        raise TokenError("invalid token") from exc

    if payload.get("type") != expected_type:
        raise TokenError(f"expected a {expected_type} token")
    return payload
