"""Library: tracks and tags.

Revision ID: 0001
Revises:
Create Date: 2026-09-30
"""

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute(
        """
        CREATE TABLE tracks (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

            path TEXT NOT NULL UNIQUE,
            filename TEXT NOT NULL,

            title TEXT,
            artist TEXT,
            album TEXT,
            label TEXT,
            genre TEXT,
            year INTEGER,

            duration_ms INTEGER,

            bpm NUMERIC(6,2),
            musical_key TEXT,
            camelot_key TEXT,

            bitrate INTEGER,
            sample_rate INTEGER,

            rating INTEGER NOT NULL DEFAULT 0 CHECK (rating BETWEEN 0 AND 5),

            file_hash TEXT NOT NULL,
            file_size BIGINT NOT NULL,
            file_mtime_ns BIGINT NOT NULL,

            status TEXT NOT NULL DEFAULT 'NOT_ANALYZED',

            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute("CREATE INDEX ix_tracks_file_hash ON tracks (file_hash)")
    op.execute("CREATE INDEX ix_tracks_camelot_key ON tracks (camelot_key)")
    op.execute("CREATE INDEX ix_tracks_bpm ON tracks (bpm)")
    op.execute(
        """
        CREATE INDEX ix_tracks_search ON tracks USING gin (
            (coalesce(artist, '') || ' ' || coalesce(title, '') || ' ' || coalesce(album, '') || ' '
             || coalesce(label, '') || ' ' || filename) gin_trgm_ops
        )
        """
    )

    op.execute(
        """
        CREATE TABLE tags (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name TEXT UNIQUE NOT NULL,
            category TEXT
        )
        """
    )
    op.execute(
        """
        CREATE TABLE track_tags (
            track_id UUID REFERENCES tracks(id) ON DELETE CASCADE,
            tag_id UUID REFERENCES tags(id) ON DELETE CASCADE,
            confidence NUMERIC(4,3),
            source TEXT,
            PRIMARY KEY (track_id, tag_id)
        )
        """
    )
    op.execute("CREATE INDEX ix_track_tags_tag_id ON track_tags (tag_id)")


def downgrade() -> None:
    op.execute("DROP TABLE track_tags")
    op.execute("DROP TABLE tags")
    op.execute("DROP TABLE tracks")
