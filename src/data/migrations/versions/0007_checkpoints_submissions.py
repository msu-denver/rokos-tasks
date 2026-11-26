"""
File: 0007_checkpoints_submissions.py
Description: Alembic migration creating stage checkpoints and submissions.
Author(s): Tyler Black
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_checkpoints_submissions"
down_revision: str | None = "0006_check_scripts_only"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _create_checkpoints() -> None:
    op.create_table(
        "checkpoints",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "run_id",
            sa.Integer(),
            sa.ForeignKey("game_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("stage_number", sa.Integer(), nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("saved_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "run_id", "stage_number", name="uq_checkpoints_run_id_stage_number"
        ),
    )
    op.create_index("ix_checkpoints_run_id", "checkpoints", ["run_id"])


def _create_submissions() -> None:
    op.create_table(
        "submissions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "run_id",
            sa.Integer(),
            sa.ForeignKey("game_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("stage_number", sa.Integer(), nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("failure_kind", sa.String(32)),
        sa.Column("failed_rule", sa.Text()),
        sa.Column("failed_turn", sa.Integer()),
        sa.Column("seconds_remaining", sa.Integer(), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "failure_kind IN ('rule','crashed','exited','turn_timeout',"
            "'run_timeout','output_limit')",
            name="ck_submissions_failure_kind",
        ),
    )
    op.create_index("ix_submissions_run_id", "submissions", ["run_id"])


def upgrade() -> None:
    """Create stage checkpoints and submissions with run-scoped indexes."""
    _create_checkpoints()
    _create_submissions()


def downgrade() -> None:
    """Drop stage submissions and checkpoints and their indexes."""
    op.drop_table("submissions")
    op.drop_table("checkpoints")
