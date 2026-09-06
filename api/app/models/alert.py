import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPk


class Alert(Base, UUIDPk, TimestampMixin):
    """blueprint §10.1 ALERT.

    `account_id` is an addition beyond the ERD's field list — an alert has
    to reference the account that triggered it before it's grouped into a
    case; the ERD only shows the eventual `ALERT }o--|| CASE` relationship.
    """

    __tablename__ = "alerts"

    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("accounts.id"), index=True)
    case_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("cases.id"), nullable=True, index=True)
    rule_code: Mapped[str] = mapped_column(String(32))
    score: Mapped[Decimal] = mapped_column(Numeric(5, 4))
    severity: Mapped[str] = mapped_column(String(16))  # LOW | MEDIUM | HIGH
    raised_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    rule_evidence: Mapped[dict] = mapped_column(JSONB, default=dict)

    case: Mapped["Case | None"] = relationship(back_populates="alerts")


Index("idx_alert_case", Alert.case_id, Alert.raised_at.desc())
