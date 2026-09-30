"""Beatgrids, DSP analysis columns and the origin of BPM/key values.

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-30
"""

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE beatgrids (
            track_id UUID PRIMARY KEY REFERENCES tracks(id) ON DELETE CASCADE,
            bpm NUMERIC(7,3) NOT NULL,
            first_beat NUMERIC(10,4) NOT NULL,          -- seconds; beat k = first_beat + k * 60 / bpm
            downbeat_offset INTEGER NOT NULL DEFAULT 0, -- index (0-3) of the first beat that starts a bar
            beats_per_bar INTEGER NOT NULL DEFAULT 4,
            grid_confidence NUMERIC(4,3),
            downbeat_confidence NUMERIC(4,3),
            source TEXT NOT NULL DEFAULT 'ANALYSIS',    -- ANALYSIS | USER (a user grid is never overwritten)
            analyzer_version TEXT,
            updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
            CHECK (downbeat_offset BETWEEN 0 AND beats_per_bar - 1)
        )
        """
    )
    op.execute("ALTER TABLE audio_analysis ADD COLUMN musical_key TEXT")
    op.execute("ALTER TABLE audio_analysis ADD COLUMN camelot_key TEXT")
    op.execute("ALTER TABLE audio_analysis ADD COLUMN key_strength NUMERIC(4,3)")
    op.execute("ALTER TABLE audio_analysis ADD COLUMN energy_curve JSONB")  # one 0-1 value per bar
    op.execute("ALTER TABLE tracks ADD COLUMN bpm_source TEXT")  # TAG | ANALYSIS | USER
    op.execute("ALTER TABLE tracks ADD COLUMN key_source TEXT")
    op.execute("UPDATE tracks SET bpm_source = 'TAG' WHERE bpm IS NOT NULL")
    op.execute("UPDATE tracks SET key_source = 'TAG' WHERE camelot_key IS NOT NULL")


def downgrade() -> None:
    op.execute("ALTER TABLE tracks DROP COLUMN key_source")
    op.execute("ALTER TABLE tracks DROP COLUMN bpm_source")
    op.execute("ALTER TABLE audio_analysis DROP COLUMN energy_curve")
    op.execute("ALTER TABLE audio_analysis DROP COLUMN key_strength")
    op.execute("ALTER TABLE audio_analysis DROP COLUMN camelot_key")
    op.execute("ALTER TABLE audio_analysis DROP COLUMN musical_key")
    op.execute("DROP TABLE beatgrids")
