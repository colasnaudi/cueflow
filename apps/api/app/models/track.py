import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, Numeric, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Track(Base):
    __tablename__ = "tracks"
    # ix_tracks_search (trigram expression index) lives in migration 0001; env.py makes Alembic ignore it.
    __table_args__ = (Index("ix_tracks_bpm", "bpm"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )

    path: Mapped[str] = mapped_column(Text, unique=True)
    filename: Mapped[str] = mapped_column(Text)

    title: Mapped[str | None] = mapped_column(Text)
    artist: Mapped[str | None] = mapped_column(Text)
    album: Mapped[str | None] = mapped_column(Text)
    label: Mapped[str | None] = mapped_column(Text)
    genre: Mapped[str | None] = mapped_column(Text)
    year: Mapped[int | None] = mapped_column(Integer)

    duration_ms: Mapped[int | None] = mapped_column(Integer)

    bpm: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    musical_key: Mapped[str | None] = mapped_column(Text)
    camelot_key: Mapped[str | None] = mapped_column(Text, index=True)
    # Where bpm / musical_key come from: TAG (file), ANALYSIS (DSP, only when the tag was empty or the user
    # accepted it) or USER (typed in Cueflow).
    bpm_source: Mapped[str | None] = mapped_column(Text)
    key_source: Mapped[str | None] = mapped_column(Text)

    bitrate: Mapped[int | None] = mapped_column(Integer)
    sample_rate: Mapped[int | None] = mapped_column(Integer)

    rating: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    rating_source: Mapped[str | None] = mapped_column(Text)  # TAG | REKORDBOX | USER
    # An edit exported from the audio editor: the track it was made from.
    edited_from: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("tracks.id", ondelete="SET NULL"))

    file_hash: Mapped[str] = mapped_column(Text, index=True)
    # Size + mtime let a rescan skip unchanged files without re-hashing them.
    file_size: Mapped[int] = mapped_column(BigInteger)
    file_mtime_ns: Mapped[int] = mapped_column(BigInteger)

    status: Mapped[str] = mapped_column(Text, default="NOT_ANALYZED", server_default="NOT_ANALYZED")

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    tags: Mapped[list["TrackTag"]] = relationship(  # noqa: F821
        back_populates="track", cascade="all, delete-orphan", lazy="selectin"
    )
