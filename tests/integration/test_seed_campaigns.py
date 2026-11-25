"""
File: test_seed_campaigns.py
Description: Verify that the shipped seed campaigns load into PostgreSQL.
Author(s): Tyler Black, Richard Hall
"""

from pathlib import Path

from sqlalchemy.orm import Session

from src.business.campaigns.seed_loader import SeedLoader
from src.business.difficulty import Difficulty
from src.data.repositories.campaign_repository import CampaignRepository

SEED_DIR = Path(__file__).resolve().parents[2] / "content/campaigns/seed"


def test_shipped_seed_campaigns_load(db_session: Session) -> None:
    """Load every shipped campaign with all stages in the validated pool."""
    repository = CampaignRepository(db_session)

    campaigns = SeedLoader(repository).load_directory(SEED_DIR)

    assert {campaign.slug for campaign in campaigns} == {
        "beginner/cafe_tab_splitter",
        "easy/rpn_calculator",
        "medium/pong",
    }
    tiers = (
        (Difficulty.BEGINNER, 2),
        (Difficulty.EASY, 3),
        (Difficulty.MEDIUM, 3),
    )
    for tier, stage_count in tiers:
        (campaign,) = repository.validated_for(tier)
        assert [stage.number for stage in campaign.stages] == list(
            range(1, stage_count + 1)
        )
        assert all(stage.starter_code is None for stage in campaign.stages)


def test_pong_stages_are_graded_by_check_scripts(db_session: Session) -> None:
    """Every Pong stage is stored with its check script (US6)."""
    repository = CampaignRepository(db_session)
    SeedLoader(repository).load_directory(SEED_DIR)
    (pong,) = repository.validated_for(Difficulty.MEDIUM)
    assert all(
        "def check(game)" in stage.check_script for stage in pong.stages
    )
