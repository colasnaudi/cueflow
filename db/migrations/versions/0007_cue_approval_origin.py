"""Who approved a cue: AUTO (approved on generation, replaced by re-analysis) or USER (never replaced).

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-01
"""

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE cues ADD COLUMN approved_by TEXT")  # NULL (pending) | AUTO | USER
    op.execute("UPDATE cues SET approved_by = 'USER' WHERE approved")


def downgrade() -> None:
    op.execute("ALTER TABLE cues DROP COLUMN approved_by")
