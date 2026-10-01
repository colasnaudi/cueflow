"""Track sections (musical positions) and per-bar vocal activity.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-01
"""

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Sections are stored as bars (CLAUDE.md §16: musical positions); seconds come from the current beatgrid,
    # so correcting bar 1 moves them with it.
    op.execute(
        """
        CREATE TABLE sections (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            track_id UUID NOT NULL REFERENCES tracks(id) ON DELETE CASCADE,
            type TEXT NOT NULL,              -- INTRO | GROOVE | BREAK | BUILD | DROP | OUTRO
            start_bar INTEGER NOT NULL,      -- 0-based, inclusive
            end_bar INTEGER NOT NULL,        -- exclusive
            confidence NUMERIC(4,3),
            source TEXT NOT NULL DEFAULT 'AUDIO',
            analyzer_version TEXT,
            CHECK (end_bar > start_bar)
        )
        """
    )
    op.execute("CREATE INDEX ix_sections_track ON sections (track_id)")
    op.execute("ALTER TABLE audio_analysis ADD COLUMN vocal_curve JSONB")  # voice probability per bar


def downgrade() -> None:
    op.execute("ALTER TABLE audio_analysis DROP COLUMN vocal_curve")
    op.execute("DROP TABLE sections")
