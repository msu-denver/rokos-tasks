"""
File: test_seed_campaigns.py
Description: Verify that the shipped seed campaigns load into PostgreSQL,
    and that every seed stage is graded only by its check script and
    passes the game-design §4.4 checks: its reference passes on 3 runs,
    and its broken program, an empty program, the previous stage's
    reference, and (from Stage 2) one fixed frame all fail.
Author(s): Tyler Black, Richard Hall
"""

import json
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from src.business.campaigns.check_runner import run_check, run_frames
from src.business.campaigns.seed_loader import SeedLoader
from src.business.campaigns.validator import CampaignValidator, frame_program
from src.business.difficulty import Difficulty
from src.data.repositories.campaign_repository import CampaignRepository

SEED_DIR = Path(__file__).resolve().parents[2] / "content/campaigns/seed"
SEED_FILES = sorted(SEED_DIR.rglob("*.json"))
STAGES = [
    (path.stem, index, stages)
    for path in SEED_FILES
    for stages in [json.loads(path.read_text("utf-8"))["stages"]]
    for index in range(len(stages))
]


def verdict(code: str, stage: dict) -> str:
    return run_check(code, stage["check_script"])["verdict"]


def test_shipped_seed_campaigns_load(db_session: Session) -> None:
    """Load every shipped campaign with all stages in the validated pool."""
    repository = CampaignRepository(db_session)

    campaigns = SeedLoader(repository).load_directory(SEED_DIR)

    assert {campaign.slug for campaign in campaigns} == {
        "beginner/traffic_light",
        "easy/vending_machine",
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
        assert all(
            "def check(game)" in stage.check_script
            for stage in campaign.stages
        )


@pytest.mark.parametrize("path", SEED_FILES, ids=lambda path: path.stem)
def test_seed_file_is_valid(path: Path) -> None:
    """The full validator, with the real player, accepts every seed."""
    assert CampaignValidator.validate_file(path) == []


@pytest.mark.parametrize(
    ("name", "index", "stages"),
    STAGES,
    ids=[f"{name}-stage{index + 1}" for name, index, _ in STAGES],
)
def test_seed_stage_checks(name: str, index: int, stages: list) -> None:
    """Each seed stage's check script tells good programs from bad."""
    stage = stages[index]
    reference = stage["reference_program"]
    assert [verdict(reference, stage) for _ in range(3)] == ["pass"] * 3
    assert verdict(stage["broken_program"], stage) == "fail"
    assert verdict("", stage) == "fail"
    if index:
        previous = stages[index - 1]["reference_program"]
        assert verdict(previous, stage) == "fail"
        first_frame = run_frames(reference, [""])[0]
        assert verdict(frame_program(first_frame), stage) == "fail"
