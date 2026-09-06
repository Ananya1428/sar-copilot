import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPk


class EvidencePack(Base, UUIDPk, TimestampMixin):
    """blueprint §10.1 EVIDENCE_PACK / §10.2 EvidencePack."""

    __tablename__ = "evidence_packs"

    case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("cases.id"), index=True)
    payload: Mapped[dict] = mapped_column(JSONB)
    content_hash: Mapped[str] = mapped_column(String(64))
    built_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    builder_version: Mapped[str] = mapped_column(String(32))

    case: Mapped["Case"] = relationship(back_populates="evidence_packs")
    items: Mapped[list["EvidenceItem"]] = relationship(back_populates="pack")
    narratives: Mapped[list["Narrative"]] = relationship(back_populates="pack")


class EvidenceItem(Base, UUIDPk, TimestampMixin):
    """blueprint §10.1 EVIDENCE_ITEM / §10.2 EvidenceItem — the flattened,
    enumerable-fact index that the later verification pipeline (§14) checks
    every narrative token against."""

    __tablename__ = "evidence_items"

    pack_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("evidence_packs.id"), index=True)
    item_key: Mapped[str] = mapped_column(String(255))
    item_type: Mapped[str] = mapped_column(String(16))  # entity|amount|date|count|location|channel|typology|text
    display_value: Mapped[str] = mapped_column(Text)
    raw_value: Mapped[dict] = mapped_column(JSONB, default=dict)
    source_table: Mapped[str] = mapped_column(String(64))
    source_row_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))

    pack: Mapped["EvidencePack"] = relationship(back_populates="items")


Index("idx_evidence_pack_gin", EvidencePack.payload, postgresql_using="gin", postgresql_ops={"payload": "jsonb_path_ops"})
