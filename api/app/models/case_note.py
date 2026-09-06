import uuid

from sqlalchemy import ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPk


class CaseNote(Base, UUIDPk, TimestampMixin):
    """blueprint §10.1 CASE_NOTE (CASE annotated_by CASE_NOTE)."""

    __tablename__ = "case_notes"

    case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("cases.id"), index=True)
    author_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    body: Mapped[str] = mapped_column(Text)

    case: Mapped["Case"] = relationship(back_populates="notes")
