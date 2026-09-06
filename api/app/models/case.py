import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPk


class Case(Base, UUIDPk, TimestampMixin):
    """blueprint §10.1 CASE.

    Table name is `cases`, not `case` — `CASE` is a reserved word in
    PostgreSQL (the `CASE WHEN` expression) and quoting it everywhere
    (as the blueprint's own §10.3 SQL does: `ON "case" (...)`) is more
    friction than it's worth. Same reasoning applies to `user` -> `users`.
    """

    __tablename__ = "cases"

    case_ref: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(16), default="OPEN")
    risk_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 4), nullable=True)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    assigned_to: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    alerts: Mapped[list["Alert"]] = relationship(back_populates="case")
    subjects: Mapped[list["CaseSubject"]] = relationship(back_populates="case")
    evidence_packs: Mapped[list["EvidencePack"]] = relationship(back_populates="case")
    notes: Mapped[list["CaseNote"]] = relationship(back_populates="case")


Index("idx_case_status", Case.status, Case.deadline_at)
