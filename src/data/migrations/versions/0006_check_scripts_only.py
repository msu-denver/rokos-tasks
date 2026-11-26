"""
File: 0006_check_scripts_only.py
Description: Alembic migration that makes check scripts the only grading
    data (#36): drops test_cases and stages.starter_code, renames
    stages.reference_solution to reference_program, and makes
    stages.check_script required. Campaigns with a stage that has no
    check script (the old stdin/stdout seeds) can't be graded, so they
    and their runs are deleted; `make seed` loads the new seeds.
Author(s): Tyler Black
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_check_scripts_only"
down_revision: str | None = "0005_stage_check_script"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UNGRADABLE = "SELECT campaign_id FROM stages WHERE check_script IS NULL"


def upgrade() -> None:
    """Remove the stdin/stdout grading data and require check scripts."""
    op.execute(f"DELETE FROM game_runs WHERE campaign_id IN ({_UNGRADABLE})")
    op.execute(f"DELETE FROM campaigns WHERE id IN ({_UNGRADABLE})")
    op.drop_index(op.f("ix_test_cases_stage_id"), table_name="test_cases")
    op.drop_table("test_cases")
    op.drop_column("stages", "starter_code")
    op.alter_column(
        "stages", "reference_solution", new_column_name="reference_program"
    )
    op.alter_column(
        "stages", "check_script", existing_type=sa.Text(), nullable=False
    )


def downgrade() -> None:
    """Restore the old columns and an empty test_cases table."""
    op.alter_column(
        "stages", "check_script", existing_type=sa.Text(), nullable=True
    )
    op.alter_column(
        "stages", "reference_program", new_column_name="reference_solution"
    )
    op.add_column(
        "stages", sa.Column("starter_code", sa.Text(), nullable=True)
    )
    op.create_table(
        "test_cases",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("stage_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("input", sa.Text(), nullable=False),
        sa.Column("expected_output", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["stage_id"], ["stages.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_test_cases_stage_id"),
        "test_cases",
        ["stage_id"],
        unique=False,
    )
