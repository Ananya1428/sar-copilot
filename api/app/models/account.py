import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPk


class Account(Base, UUIDPk, TimestampMixin):
    """blueprint §10.1 ACCOUNT.

    `status` is an addition beyond the ERD's field list — needed by the
    synthetic generator (and later the DORMANT_REACTIVATION rule, §12.2)
    to represent an account going quiet before a sudden reactivation.
    """

    __tablename__ = "accounts"

    customer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("customers.id"), index=True)
    account_ref: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    account_type: Mapped[str] = mapped_column(String(32))  # checking | savings | business
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    opened_at: Mapped[date] = mapped_column(Date)
    expected_monthly_volume: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    status: Mapped[str] = mapped_column(String(16), default="active")  # active | dormant | closed

    customer: Mapped["Customer"] = relationship(back_populates="accounts")
    transactions: Mapped[list["Transaction"]] = relationship(back_populates="account")
