"""
File: 0003_campaigns.py
Description: Alembic migration creating campaigns, stages, and test_cases.
Author(s): Tyler Black
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003_campaigns"
down_revision: str | None = "0002_users"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create campaigns, stages, and test_cases tables."""
    op.create_table(
        "campaigns",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("difficulty", sa.String(length=32), nullable=False),
        sa.Column(
            "status",
            sa.String(length=32),
            nullable=False,
            server_default="validated",
        ),
        sa.Column(
            "source",
            sa.String(length=64),
            nullable=False,
            server_default="seed",
        ),
        sa.Column("slug", sa.String(length=255), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_campaigns_slug"), "campaigns", ["slug"], unique=True
    )

    op.create_table(
        "stages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("campaign_id", sa.Integer(), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("starter_code", sa.Text(), nullable=True),
        sa.Column("reference_solution", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["campaign_id"],
            ["campaigns.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "campaign_id", "number", name="uq_stages_campaign_id_number"
        ),
    )
    op.create_index(
        op.f("ix_stages_campaign_id"), "stages", ["campaign_id"], unique=False
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
            ["stage_id"],
            ["stages.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_test_cases_stage_id"),
        "test_cases",
        ["stage_id"],
        unique=False,
    )


def downgrade() -> None:
    """Drop test_cases, stages, and campaigns tables."""
    op.drop_index(op.f("ix_test_cases_stage_id"), table_name="test_cases")
    op.drop_table("test_cases")
    op.drop_index(op.f("ix_stages_campaign_id"), table_name="stages")
    op.drop_table("stages")
    op.drop_index(op.f("ix_campaigns_slug"), table_name="campaigns")
    op.drop_table("campaigns")
