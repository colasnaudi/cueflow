"""Hot cues and memory cues, as musical positions resolved with the beatgrid.

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-01
"""

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE cues (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            track_id UUID NOT NULL REFERENCES tracks(id) ON DELETE CASCADE,
            slot TEXT NOT NULL,                    -- A-H for hot cues, M01... for memory cues
            type TEXT NOT NULL DEFAULT 'HOT',      -- HOT | MEMORY
            label TEXT,
            bar INTEGER NOT NULL,                  -- 0-based bar of the beatgrid (CLAUDE.md §16)
            beat INTEGER NOT NULL DEFAULT 0,       -- 0-3 inside the bar
            color TEXT,                            -- #RRGGBB
            confidence NUMERIC(4,3),
            source TEXT NOT NULL,                  -- ANALYSIS | USER
            approved BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            UNIQUE (track_id, slot),
            CHECK (beat BETWEEN 0 AND 3),
            CHECK (type IN ('HOT', 'MEMORY'))
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE cues")
