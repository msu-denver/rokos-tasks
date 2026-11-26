"""
File: test_score_calculator.py
Description: Black-box tests for stage timing and points.
Author(s): Tyler Black
"""

from datetime import UTC, datetime, timedelta

import pytest

from src.business.difficulty import Difficulty
from src.business.score_calculator import ScoreCalculator


@pytest.mark.blackbox
@pytest.mark.parametrize(
    ("seconds", "difficulty", "expected"),
    [
        (0, Difficulty.BEGINNER, 100),
        (240, Difficulty.BEGINNER, 580),
        (7, Difficulty.EASY, 142),
        (10, Difficulty.MEDIUM, 180),
        (10, Difficulty.HARD, 240),
        (10, Difficulty.EXPERT, 300),
        (10, Difficulty.IMPOSSIBLE, 360),
    ],
)
def test_stage_points(
    seconds: int, difficulty: Difficulty, expected: int
) -> None:
    """Verify tier scoring at zero, full time, and fractional points.

    Stage points apply the tier multiplier to the base plus time bonus.
    The returned score matches the expected whole points for each tier.
    """
    assert ScoreCalculator.stage_points(seconds, difficulty) == expected


@pytest.mark.blackbox
def test_negative_remaining_time_is_rejected() -> None:
    """Verify stage points validate the time and reject negative seconds."""
    with pytest.raises(ValueError):
        ScoreCalculator.stage_points(-1, Difficulty.BEGINNER)


@pytest.mark.blackbox
@pytest.mark.parametrize(
    ("elapsed", "expected"), [(0, 240), (80.5, 159), (240, 0), (241, 0)]
)
def test_seconds_remaining(elapsed: float, expected: int) -> None:
    """Verify the countdown at start, mid-stage, expiry, and after expiry.

    The remaining time rounds down and stays at zero after the limit.
    """
    started = datetime(2026, 11, 18, tzinfo=UTC)
    now = started + timedelta(seconds=elapsed)
    assert ScoreCalculator.seconds_remaining(240, started, now) == expected
