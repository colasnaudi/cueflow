"""Rekordbox collection import (read-only snapshot) and the origin of ratings.

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-01
"""

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE tracks ADD COLUMN rating_source TEXT")  # TAG | REKORDBOX | USER
    op.execute("UPDATE tracks SET rating_source = 'TAG' WHERE rating > 0")
    op.execute(
        """
        CREATE TABLE rekordbox_tracks (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            track_id UUID UNIQUE REFERENCES tracks(id) ON DELETE CASCADE,  -- NULL: not a Cueflow file
            location TEXT NOT NULL UNIQUE,     -- decoded file path
            rekordbox_id TEXT,
            name TEXT,
            artist TEXT,
            genre TEXT,
            label TEXT,
            comments TEXT,
            rating INTEGER NOT NULL DEFAULT 0, -- 0-5 stars
            bpm NUMERIC(7,3),
            tonality TEXT,
            play_count INTEGER,
            date_added DATE,
            tempo JSONB,                       -- [{"inizio": s, "bpm": x, "battito": 1}, ...] (its beatgrid)
            position_marks JSONB,              -- [{"name":..., "type": 0, "start": s, "num": 0}, ...]
            imported_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE rekordbox_tracks")
    op.execute("ALTER TABLE tracks DROP COLUMN rating_source")
