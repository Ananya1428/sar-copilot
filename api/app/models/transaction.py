import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPk


class Transaction(Base, UUIDPk, TimestampMixin):
    """blueprint §10.1 TRANSACTION.

    Two additions beyond the ERD's field list, both needed for the
    synthetic generator and later evidence/detection work:
    - `txn_ref`: a human-readable reference, mirroring `customer_ref` /
      `account_ref`. The blueprint's own `TransactionEvidence` pydantic
      model (§10.2) already expects a `txn_ref`, so the ERD's omission
      looks like an oversight rather than a deliberate exclusion.
    - `counterparty_account_ref`: set only when the counterparty is one of
      our own accounts (e.g. CIRCULAR_FLOW injections), so the money-flow
      graph (§12.4) can be reconstructed without joining on external refs.
    """

    __tablename__ = "transactions"

    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("accounts.id"), index=True)
    txn_ref: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    executed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    direction: Mapped[str] = mapped_column(String(8))  # credit | debit
    channel: Mapped[str] = mapped_column(String(16))  # cash | wire | ach | card | check
    counterparty_ref: Mapped[str | None] = mapped_column(String(64), nullable=True)
    counterparty_country: Mapped[str | None] = mapped_column(String(2), nullable=True)
    counterparty_account_ref: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    narrative_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_cash: Mapped[bool] = mapped_column(Boolean, default=False)

    account: Mapped["Account"] = relationship(back_populates="transactions")


# blueprint §10.3 key indexes
Index("idx_txn_account_time", Transaction.account_id, Transaction.executed_at.desc())
Index(
    "idx_txn_amount",
    Transaction.amount,
    postgresql_where=Transaction.amount.between(8000, 10000),
)
