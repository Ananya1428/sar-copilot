from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPk


class User(Base, UUIDPk, TimestampMixin):
    """blueprint §10.1 USER. Table name `users`, not `user` — see note on
    `Case` in case.py re: reserved-word table names.

    `role` values match the RBAC matrix in §11.3: analyst | reviewer |
    officer | admin. Auth (login, password hashing, JWT issuance) is a
    later part; this table exists now so FKs from cases/audit_records
    resolve.
    """

    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(16), default="analyst")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
