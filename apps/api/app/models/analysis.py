import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class AudioAnalysis(Base):
    __tablename__ = "audio_analysis"
    __table_args__ = (
        UniqueConstraint("track_id", "analyzer_version", name="audio_analysis_track_id_analyzer_version_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    track_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tracks.id", ondelete="CASCADE"))
    energy: Mapped[Decimal | None] = mapped_column(Numeric(4, 2))
    danceability: Mapped[Decimal | None] = mapped_column(Numeric(4, 2))
    loudness: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    instrumental_probability: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    vocal_probability: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    intro_seconds: Mapped[Decimal | None] = mapped_column(Numeric(10, 3))
    outro_seconds: Mapped[Decimal | None] = mapped_column(Numeric(10, 3))
    styles: Mapped[list[dict] | None] = mapped_column(JSONB)
    musical_key: Mapped[str | None] = mapped_column(Text)
    camelot_key: Mapped[str | None] = mapped_column(Text)
    key_strength: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    energy_curve: Mapped[list[float] | None] = mapped_column(JSONB)
    vocal_curve: Mapped[list[float] | None] = mapped_column(JSONB)
    analyzed_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    analyzer_version: Mapped[str] = mapped_column(Text)


class GenreSuggestion(Base):
    __tablename__ = "genre_suggestions"
    __table_args__ = (
        UniqueConstraint("track_id", "genre", name="genre_suggestions_track_id_genre_key"),
        Index("ix_genre_suggestions_track", "track_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    track_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tracks.id", ondelete="CASCADE"))
    genre: Mapped[str] = mapped_column(Text)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    source: Mapped[str] = mapped_column(Text)
    rank: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class GenreReview(Base):
    __tablename__ = "genre_reviews"
    __table_args__ = (Index("ix_genre_reviews_status", "status"),)

    track_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tracks.id", ondelete="CASCADE"), primary_key=True)
    status: Mapped[str] = mapped_column(Text, default="PENDING", server_default="PENDING")
    chosen_genre: Mapped[str | None] = mapped_column(Text)
    previous_genre: Mapped[str | None] = mapped_column(Text)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime)


class Beatgrid(Base):
    __tablename__ = "beatgrids"
    __table_args__ = (
        CheckConstraint("downbeat_offset BETWEEN 0 AND beats_per_bar - 1", name="beatgrids_check"),
    )

    track_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tracks.id", ondelete="CASCADE"), primary_key=True)
    bpm: Mapped[Decimal] = mapped_column(Numeric(7, 3))
    first_beat: Mapped[Decimal] = mapped_column(Numeric(10, 4))
    downbeat_offset: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    beats_per_bar: Mapped[int] = mapped_column(Integer, default=4, server_default="4")
    grid_confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    downbeat_confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    source: Mapped[str] = mapped_column(Text, default="ANALYSIS", server_default="ANALYSIS")
    analyzer_version: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class Section(Base):
    __tablename__ = "sections"
    __table_args__ = (
        CheckConstraint(
            "end_bar * 4 + end_beat > start_bar * 4 + start_beat AND start_beat BETWEEN 0 AND 3 "
            "AND end_beat BETWEEN 0 AND 3",
            name="sections_check",
        ),
        Index("ix_sections_track", "track_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    track_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tracks.id", ondelete="CASCADE"))
    type: Mapped[str] = mapped_column(Text)
    start_bar: Mapped[int] = mapped_column(Integer)
    end_bar: Mapped[int] = mapped_column(Integer)
    start_beat: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    end_beat: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    source: Mapped[str] = mapped_column(Text, default="AUDIO", server_default="AUDIO")
    analyzer_version: Mapped[str | None] = mapped_column(Text)
