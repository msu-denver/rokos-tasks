"""
File: score_calculator.py
Description: Calculates remaining stage time and difficulty-adjusted points.
Author(s): Tyler Black
"""

import math
from datetime import datetime

from src.business.difficulty import Difficulty


class ScoreCalculator:
    """Calculate the time and points for a stage submission."""

    @staticmethod
    def seconds_remaining(
        limit_seconds: int, started_at: datetime, now: datetime
    ) -> int:
        """Return the remaining whole seconds, clamped to zero."""
        return max(
            0, math.floor(limit_seconds - (now - started_at).total_seconds())
        )

    @staticmethod
    def stage_points(seconds_remaining: int, difficulty: Difficulty) -> int:
        """Return the whole points earned for passing a stage.

        Raises:
            ValueError: If the remaining time is negative.
        """
        if seconds_remaining < 0:
            raise ValueError("seconds_remaining must be nonnegative")
        return math.floor(
            (100 + seconds_remaining * 2) * difficulty.multiplier
        )
