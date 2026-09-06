import uuid

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPk


class CaseSubject(Base, UUIDPk, TimestampMixin):
    """blueprint §10.1 CASE_SUBJECT (link table: CASE involves, CUSTOMER
    appears-as). Field list isn't given in the ERD's detail blocks, so
    `role` mirrors the roles used elsewhere in the spec (§10.2
    SubjectEvidence.role: primary | counterparty | beneficiary | originator)."""

    __tablename__ = "case_subjects"

    case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("cases.id"), index=True)
    customer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("customers.id"), index=True)
    role: Mapped[str] = mapped_column(String(16))  # primary | counterparty | beneficiary | originator

    case: Mapped["Case"] = relationship(back_populates="subjects")
    customer: Mapped["Customer"] = relationship(back_populates="case_subjects")
