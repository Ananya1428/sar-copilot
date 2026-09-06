import uuid
from decimal import Decimal

from sqlalchemy import Boolean, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPk


class Narrative(Base, UUIDPk, TimestampMixin):
    """blueprint §10.1 NARRATIVE."""

    __tablename__ = "narratives"

    pack_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("evidence_packs.id"), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    body: Mapped[str] = mapped_column(Text)
    generation_mode: Mapped[str] = mapped_column(String(24))  # TEMPLATE | HYBRID | FREEFORM | TEMPLATE_FALLBACK
    model_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(16), nullable=True)
    seed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    verified: Mapped[bool] = mapped_column(Boolean, default=False)

    pack: Mapped["EvidencePack"] = relationship(back_populates="narratives")
    sentences: Mapped[list["NarrativeSentence"]] = relationship(back_populates="narrative")
    verification_reports: Mapped[list["VerificationReport"]] = relationship(back_populates="narrative")


class NarrativeSentence(Base, UUIDPk, TimestampMixin):
    """blueprint §10.1 NARRATIVE_SENTENCE.

    `evidence_keys` is an addition beyond the ERD's field list — the
    blueprint's own §14.8 provenance-mapping example shows every sentence
    carrying its cited `EvidenceItem` keys, and Part 5's verification
    pipeline has to re-check exactly those keys per sentence, so this has
    to be a real persisted column, not something reconstructed later.
    """

    __tablename__ = "narrative_sentences"

    narrative_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("narratives.id"), index=True)
    ordinal: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    w_category: Mapped[str | None] = mapped_column(String(16), nullable=True)  # section id, e.g. who|what_when|where|how|why
    evidence_keys: Mapped[list] = mapped_column(JSONB, default=list)
    grounding_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 4), nullable=True)

    narrative: Mapped["Narrative"] = relationship(back_populates="sentences")
