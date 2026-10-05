"""Audio editor: the saved working edit of a track (an edit list, the original file is never rewritten).

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-05
"""

from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE track_edits (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            track_id UUID NOT NULL UNIQUE REFERENCES tracks(id) ON DELETE CASCADE,
            edit JSONB NOT NULL,  -- {"sample_rate", "gain_db", "segments": [{"start", "end", "ramps"}]}
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE track_edits")
