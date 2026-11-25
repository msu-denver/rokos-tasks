"""
File: 0004_game_runs.py
Description: Alembic migration creating game runs and their active-run index.
Author(s): Tyler Black
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_game_runs"
down_revision: str | None = "0003_campaigns"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create game runs and limit each user to one active run."""
    op.create_table(
        "game_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "campaign_id",
            sa.Integer(),
            sa.ForeignKey("campaigns.id"),
            nullable=False,
        ),
        sa.Column("difficulty", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("lives", sa.Integer(), nullable=False),
        sa.Column("current_stage", sa.Integer(), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "stage_started_at", sa.DateTime(timezone=True), nullable=False
        ),
        sa.Column("ended_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "status IN ('in_progress', 'won', 'lost', 'abandoned')",
            name="ck_game_runs_status",
        ),
    )
    op.create_index(
        "ix_game_runs_user_id_status", "game_runs", ["user_id", "status"]
    )
    op.create_index(
        "uq_game_runs_active_user",
        "game_runs",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("status = 'in_progress'"),
    )


def downgrade() -> None:
    """Drop the game runs table and its indexes."""
    op.drop_table("game_runs")
