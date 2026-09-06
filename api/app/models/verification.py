import uuid
from decimal import Decimal

from sqlalchemy import Boolean, ForeignKey, Numeric
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPk


class VerificationReport(Base, UUIDPk, TimestampMixin):
    """blueprint §10.1 VERIFICATION_REPORT / §14.7 aggregation."""

    __tablename__ = "verification_reports"

    narrative_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("narratives.id"), index=True)
    passed: Mapped[bool] = mapped_column(Boolean)
    checks: Mapped[dict] = mapped_column(JSONB)
    overall_score: Mapped[Decimal] = mapped_column(Numeric(5, 4))

    narrative: Mapped["Narrative"] = relationship(back_populates="verification_reports")
