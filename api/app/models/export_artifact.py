import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPk


class ExportArtifact(Base, UUIDPk, TimestampMixin):
    """blueprint §10.1 EXPORT_ARTIFACT (NARRATIVE exported_as EXPORT_ARTIFACT),
    §15.2 EXPORTED action."""

    __tablename__ = "export_artifacts"

    narrative_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("narratives.id"), index=True)
    format: Mapped[str] = mapped_column(String(16))  # form111_xml | pdf
    content_hash: Mapped[str] = mapped_column(String(64))
    file_path: Mapped[str] = mapped_column(String(512))
    exported_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    exported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
