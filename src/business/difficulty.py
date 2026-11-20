"""
File: difficulty.py
Description: Difficulty tiers and their round rules for Roko's Tasks.
Author(s): Tyler Black
"""

from dataclasses import dataclass
from enum import StrEnum


@dataclass(frozen=True)
class DifficultyRules:
    """Rules and parameters governing a difficulty tier."""

    stages: int
    minutes_per_stage: int
    starting_lives: int
    multiplier: float


class Difficulty(StrEnum):
    """The six game difficulty tiers."""

    BEGINNER = "beginner"
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"
    EXPERT = "expert"
    IMPOSSIBLE = "impossible"

    @property
    def label(self) -> str:
        """Display label for this difficulty tier."""
        return _TIER_LABELS[self]

    @property
    def rules(self) -> DifficultyRules:
        """Rule parameters for this difficulty tier."""
        return _TIER_RULES[self]

    @property
    def stages(self) -> int:
        """Number of stages in this tier."""
        return self.rules.stages

    @property
    def minutes_per_stage(self) -> int:
        """Minutes allowed per stage in this tier."""
        return self.rules.minutes_per_stage

    @property
    def starting_lives(self) -> int:
        """Starting lives for runs in this tier."""
        return self.rules.starting_lives

    @property
    def multiplier(self) -> float:
        """Score multiplier for this tier."""
        return self.rules.multiplier


_TIER_LABELS: dict[Difficulty, str] = {
    Difficulty.BEGINNER: "Beginner",
    Difficulty.EASY: "Easy",
    Difficulty.MEDIUM: "Medium",
    Difficulty.HARD: "Hard",
    Difficulty.EXPERT: "Expert",
    Difficulty.IMPOSSIBLE: "Impossible",
}

_TIER_RULES: dict[Difficulty, DifficultyRules] = {
    Difficulty.BEGINNER: DifficultyRules(
        stages=2,
        minutes_per_stage=4,
        starting_lives=4,
        multiplier=1.0,
    ),
    Difficulty.EASY: DifficultyRules(
        stages=3,
        minutes_per_stage=5,
        starting_lives=3,
        multiplier=1.25,
    ),
    Difficulty.MEDIUM: DifficultyRules(
        stages=3,
        minutes_per_stage=6,
        starting_lives=3,
        multiplier=1.5,
    ),
    Difficulty.HARD: DifficultyRules(
        stages=4,
        minutes_per_stage=7,
        starting_lives=3,
        multiplier=2.0,
    ),
    Difficulty.EXPERT: DifficultyRules(
        stages=5,
        minutes_per_stage=8,
        starting_lives=2,
        multiplier=2.5,
    ),
    Difficulty.IMPOSSIBLE: DifficultyRules(
        stages=5,
        minutes_per_stage=8,
        starting_lives=1,
        multiplier=3.0,
    ),
}
