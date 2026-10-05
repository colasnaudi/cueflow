import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Annotation(Base):
    """A DJ note on the timeline, at a musical position (never exported to Rekordbox)."""

    __tablename__ = "annotations"
    __table_args__ = (
        CheckConstraint("beat BETWEEN 0 AND 3", name="annotations_beat_check"),
        Index("ix_annotations_track", "track_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    track_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tracks.id", ondelete="CASCADE"))
    bar: Mapped[int] = mapped_column(Integer)
    beat: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    kind: Mapped[str] = mapped_column(Text, default="NOTE", server_default="NOTE")
    text: Mapped[str] = mapped_column(Text, default="", server_default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
