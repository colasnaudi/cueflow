import uuid
from decimal import Decimal

from sqlalchemy import ForeignKey, Index, Numeric, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Tag(Base):
    __tablename__ = "tags"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    name: Mapped[str] = mapped_column(Text, unique=True)
    category: Mapped[str | None] = mapped_column(Text)


class TrackTag(Base):
    __tablename__ = "track_tags"
    __table_args__ = (Index("ix_track_tags_tag_id", "tag_id"),)

    track_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tracks.id", ondelete="CASCADE"), primary_key=True)
    tag_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    source: Mapped[str | None] = mapped_column(Text)

    track: Mapped["Track"] = relationship(back_populates="tags")  # noqa: F821
    tag: Mapped[Tag] = relationship(lazy="joined")
