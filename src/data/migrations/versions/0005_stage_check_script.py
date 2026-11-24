"""
File: 0005_stage_check_script.py
Description: Alembic migration adding the optional check_script column to
    stages (US6: the script that plays the player's program).
Author(s): Richard Hall
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_stage_check_script"
down_revision: str | None = "0004_game_runs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add stages.check_script (null for stages graded the old way)."""
    op.add_column(
        "stages", sa.Column("check_script", sa.Text(), nullable=True)
    )


def downgrade() -> None:
    """Remove stages.check_script."""
    op.drop_column("stages", "check_script")
