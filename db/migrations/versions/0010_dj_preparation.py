"""DJ preparation (editor V2, lot 1): variable beatgrids, loops, DJ sections, annotations, edited tracks.

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-05
"""

from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Variable tempo: [{"time": s, "bpm": x, "beat": 1-4}] like Rekordbox TEMPO entries. NULL = constant grid
    # (bpm, first_beat, downbeat_offset), which stays filled from the first anchor for every reader.
    op.execute("ALTER TABLE beatgrids ADD COLUMN anchors JSONB")
    # A cue with a length is a loop (Rekordbox POSITION_MARK Type 4), in beats (1/2 beat allowed).
    op.execute("ALTER TABLE cues ADD COLUMN loop_beats NUMERIC(6,3) CHECK (loop_beats > 0)")
    # Sections edited by the DJ (source USER) take precedence over the detected ones (AUDIO), which are kept.
    op.execute("ALTER TABLE sections ADD COLUMN label TEXT")
    op.execute("ALTER TABLE sections ADD COLUMN color TEXT")
    op.execute(
        """
        CREATE TABLE annotations (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            track_id UUID NOT NULL REFERENCES tracks(id) ON DELETE CASCADE,
            bar INTEGER NOT NULL,
            beat INTEGER NOT NULL DEFAULT 0 CHECK (beat BETWEEN 0 AND 3),
            kind TEXT NOT NULL DEFAULT 'NOTE',  -- NOTE | DROP | VOCAL | WARNING | FIRE
            text TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute("CREATE INDEX ix_annotations_track ON annotations (track_id)")
    # An exported edit added to the catalogue remembers the track it was made from.
    op.execute("ALTER TABLE tracks ADD COLUMN edited_from UUID REFERENCES tracks(id) ON DELETE SET NULL")


def downgrade() -> None:
    op.execute("ALTER TABLE tracks DROP COLUMN edited_from")
    op.execute("DROP TABLE annotations")
    op.execute("ALTER TABLE sections DROP COLUMN color")
    op.execute("ALTER TABLE sections DROP COLUMN label")
    op.execute("ALTER TABLE cues DROP COLUMN loop_beats")
    op.execute("ALTER TABLE beatgrids DROP COLUMN anchors")
