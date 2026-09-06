from datetime import date

from sqlalchemy import Date, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPk


class Customer(Base, UUIDPk, TimestampMixin):
    """blueprint §10.1 CUSTOMER."""

    __tablename__ = "customers"

    customer_ref: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    legal_name: Mapped[str] = mapped_column(String(255))
    entity_type: Mapped[str] = mapped_column(String(32))  # individual | business
    onboarded_at: Mapped[date] = mapped_column(Date)
    risk_rating: Mapped[str] = mapped_column(String(16), default="LOW")
    occupation: Mapped[str | None] = mapped_column(String(255), nullable=True)
    country: Mapped[str] = mapped_column(String(2))

    accounts: Mapped[list["Account"]] = relationship(back_populates="customer")
    case_subjects: Mapped[list["CaseSubject"]] = relationship(back_populates="customer")
