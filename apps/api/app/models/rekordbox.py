import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class RekordboxTrack(Base):
    """Read-only snapshot of a track as Rekordbox knows it (from its collection XML export)."""

    __tablename__ = "rekordbox_tracks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    track_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("tracks.id", ondelete="CASCADE"), unique=True
    )
    location: Mapped[str] = mapped_column(Text, unique=True)
    rekordbox_id: Mapped[str | None] = mapped_column(Text)
    name: Mapped[str | None] = mapped_column(Text)
    artist: Mapped[str | None] = mapped_column(Text)
    genre: Mapped[str | None] = mapped_column(Text)
    label: Mapped[str | None] = mapped_column(Text)
    comments: Mapped[str | None] = mapped_column(Text)
    rating: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    bpm: Mapped[Decimal | None] = mapped_column(Numeric(7, 3))
    tonality: Mapped[str | None] = mapped_column(Text)
    play_count: Mapped[int | None] = mapped_column(Integer)
    date_added: Mapped[date | None] = mapped_column(Date)
    tempo: Mapped[list[dict] | None] = mapped_column(JSONB)
    position_marks: Mapped[list[dict] | None] = mapped_column(JSONB)
    imported_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
