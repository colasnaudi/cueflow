"""Sections placed to the beat: drops do not always fall on a bar line.

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-01
"""

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE sections ADD COLUMN start_beat INTEGER NOT NULL DEFAULT 0"
    )  # beat inside start_bar
    op.execute("ALTER TABLE sections ADD COLUMN end_beat INTEGER NOT NULL DEFAULT 0")
    op.execute("ALTER TABLE sections DROP CONSTRAINT sections_check")
    op.execute(
        "ALTER TABLE sections ADD CONSTRAINT sections_check "
        "CHECK (end_bar * 4 + end_beat > start_bar * 4 + start_beat AND start_beat BETWEEN 0 AND 3 "
        "AND end_beat BETWEEN 0 AND 3)"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE sections DROP CONSTRAINT sections_check")
    op.execute("ALTER TABLE sections ADD CONSTRAINT sections_check CHECK (end_bar > start_bar)")
    op.execute("ALTER TABLE sections DROP COLUMN end_beat")
    op.execute("ALTER TABLE sections DROP COLUMN start_beat")
