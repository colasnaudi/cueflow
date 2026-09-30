"""Audio analysis, genre suggestions and their review.

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-30
"""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE audio_analysis (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            track_id UUID NOT NULL REFERENCES tracks(id) ON DELETE CASCADE,

            energy NUMERIC(4,2),
            danceability NUMERIC(4,2),
            loudness NUMERIC(6,2),

            instrumental_probability NUMERIC(4,3),
            vocal_probability NUMERIC(4,3),

            intro_seconds NUMERIC(10,3),
            outro_seconds NUMERIC(10,3),

            -- Top Discogs styles from the audio model: [{"style": "Tech House", "score": 0.31}, ...]
            styles JSONB,

            analyzed_at TIMESTAMP NOT NULL DEFAULT NOW(),
            analyzer_version TEXT NOT NULL,

            UNIQUE (track_id, analyzer_version)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE genre_suggestions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            track_id UUID NOT NULL REFERENCES tracks(id) ON DELETE CASCADE,
            genre TEXT NOT NULL,
            confidence NUMERIC(4,3),
            source TEXT NOT NULL,          -- FOLDER | AUDIO
            rank INTEGER NOT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            UNIQUE (track_id, genre)
        )
        """
    )
    op.execute("CREATE INDEX ix_genre_suggestions_track ON genre_suggestions (track_id)")
    op.execute(
        """
        CREATE TABLE genre_reviews (
            track_id UUID PRIMARY KEY REFERENCES tracks(id) ON DELETE CASCADE,
            status TEXT NOT NULL DEFAULT 'PENDING',   -- PENDING | APPROVED | REJECTED
            chosen_genre TEXT,
            previous_genre TEXT,                      -- genre before approval, never silently lost
            reviewed_at TIMESTAMP
        )
        """
    )
    op.execute("CREATE INDEX ix_genre_reviews_status ON genre_reviews (status)")


def downgrade() -> None:
    op.execute("DROP TABLE genre_reviews")
    op.execute("DROP TABLE genre_suggestions")
    op.execute("DROP TABLE audio_analysis")
