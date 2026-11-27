 """
File: 0007_stage_input_style.py
Description: Adds input-style metadata to campaign stages and backfills
    existing seed stages with their declared input styles (US5).
Author(s): Steph Rivera
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_stage_input_style"
down_revision: str | None = "0006_check_scripts_only"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add and populate the required stage input style."""
    op.add_column(
        "stages",
        sa.Column("input_style", sa.String(length=16), nullable=True),
    )

    op.execute(
        """
        UPDATE stages AS stage
        SET input_style = mapping.input_style
        FROM campaigns AS campaign
        JOIN (
            VALUES
                ('beginner/traffic_light', 1, 'none'),
                ('beginner/traffic_light', 2, 'lines'),
                ('easy/vending_machine', 1, 'lines'),
                ('easy/vending_machine', 2, 'lines'),
                ('easy/vending_machine', 3, 'lines'),
                ('medium/pong', 1, 'none'),
                ('medium/pong', 2, 'keys'),
                ('medium/pong', 3, 'keys')
        ) AS mapping(slug, number, input_style)
            ON campaign.slug = mapping.slug
        WHERE stage.campaign_id = campaign.id
            AND stage.number = mapping.number
            AND campaign.source = 'seed'
        """
    )

    op.alter_column(
        "stages",
        "input_style",
        existing_type=sa.String(length=16),
        nullable=False,
    )

    op.create_check_constraint(
        "ck_stages_input_style",
        "stages",
        "input_style IN ('none', 'lines', 'keys')",
    )


def downgrade() -> None:
    """Remove stage input-style metadata."""
    op.drop_constraint(
        "ck_stages_input_style",
        "stages",
        type_="check",
    )

    op.drop_column("stages", "input_style")
