"""
File: seed.py
Description: Seeds validated campaign files into the database.
Author(s): Tyler Black
"""

import json
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from sqlalchemy.exc import SQLAlchemyError  # noqa: E402

from src.business.campaigns.seed_loader import (  # noqa: E402
    CampaignValidationError,
    SeedLoader,
)
from src.data.database import db  # noqa: E402
from src.data.repositories.campaign_repository import (  # noqa: E402
    CampaignRepository,
)

DEFAULT_DATABASE_URL = (
    "postgresql+psycopg://rokos:rokos@localhost:5433/rokos_tasks"
)


def seed_campaigns(seed_dir: Path, database_url: str) -> int:
    """Validate and upsert all seed campaigns into the database.

    Args:
        seed_dir: Directory containing seed campaign JSON files.
        database_url: Database connection string.

    Returns:
        0 on success, 1 on failure.
    """
    db.init(database_url)
    session = db.session
    repo = CampaignRepository(session)
    try:
        loader = SeedLoader(repo)
        loaded = loader.load_directory(seed_dir)
        repo.commit()
        print(f"Successfully seeded {len(loaded)} campaign(s).")
        return 0
    except (
        CampaignValidationError,
        json.JSONDecodeError,
        OSError,
        SQLAlchemyError,
    ) as exc:
        repo.rollback()
        print(f"Error during seeding: {exc}", file=sys.stderr)
        return 1
    finally:
        db.remove()


def main(argv: list[str]) -> int:
    """Entry point for the seed CLI utility."""
    default_dir = Path("content/campaigns/seed")
    seed_path = Path(argv[1]) if len(argv) > 1 else default_dir
    db_url = os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)
    return seed_campaigns(seed_path, db_url)


if __name__ == "__main__":  # pragma: no cover - thin CLI entrypoint
    sys.exit(main(sys.argv))
