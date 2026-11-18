"""
File: 0002_users.py
Description: Create users table and case-insensitive unique index on username.
Author(s): Tyler Black
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002_users"
down_revision: str | None = "0001_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Run migration upgrades."""
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("username", sa.String(length=50), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_users_lower_username",
        "users",
        [sa.text("lower(username)")],
        unique=True,
    )


def downgrade() -> None:
    """Run migration downgrades."""
    op.drop_index("uq_users_lower_username", table_name="users")
    op.drop_table("users")
