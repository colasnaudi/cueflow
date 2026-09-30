import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Numeric, Text, UniqueConstraint, func
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
