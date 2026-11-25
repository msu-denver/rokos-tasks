"""
File: 0001_baseline.py
Description: Baseline empty migration establishing schema versioning.
Author(s): Tyler Black
"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "0001_baseline"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Run migration upgrades."""
    pass


def downgrade() -> None:
    """Run migration downgrades."""
    pass
