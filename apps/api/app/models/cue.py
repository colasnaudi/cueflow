import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Cue(Base):
    __tablename__ = "cues"
    __table_args__ = (
        UniqueConstraint("track_id", "slot", name="cues_track_id_slot_key"),
        CheckConstraint("beat BETWEEN 0 AND 3", name="cues_beat_check"),
        CheckConstraint("type IN ('HOT', 'MEMORY')", name="cues_type_check"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    track_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tracks.id", ondelete="CASCADE"))
    slot: Mapped[str] = mapped_column(Text)
    type: Mapped[str] = mapped_column(Text, default="HOT", server_default="HOT")
    label: Mapped[str | None] = mapped_column(Text)
    bar: Mapped[int] = mapped_column(Integer)
    beat: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    color: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    source: Mapped[str] = mapped_column(Text)
    approved: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    # AUTO: approved on generation, replaced by a re-analysis. USER: validated by the DJ, never replaced.
    approved_by: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
