"""
File: test_difficulty.py
Description: Unit tests for Difficulty enum and round rules table.
Author(s): Tyler Black
"""

from dataclasses import FrozenInstanceError

import pytest

from src.business.difficulty import Difficulty, DifficultyRules


class TestDifficultyTiers:
    """Test suite verifying difficulty tier rules."""

    def test_all_six_tiers_exist(self) -> None:
        """Verify that all six expected difficulty tiers are present."""
        tiers = [d.value for d in Difficulty]
        expected = [
            "beginner",
            "easy",
            "medium",
            "hard",
            "expert",
            "impossible",
        ]
        assert tiers == expected

    def test_display_labels(self) -> None:
        """Verify human-readable labels for UI display."""
        expected_labels = {
            Difficulty.BEGINNER: "Beginner",
            Difficulty.EASY: "Easy",
            Difficulty.MEDIUM: "Medium",
            Difficulty.HARD: "Hard",
            Difficulty.EXPERT: "Expert",
            Difficulty.IMPOSSIBLE: "Impossible",
        }
        for diff, expected_label in expected_labels.items():
            assert diff.label == expected_label

    @pytest.mark.parametrize(
        (
            "difficulty",
            "expected_stages",
            "expected_minutes",
            "expected_lives",
            "expected_multiplier",
        ),
        [
            (Difficulty.BEGINNER, 2, 4, 4, 1.0),
            (Difficulty.EASY, 3, 5, 3, 1.25),
            (Difficulty.MEDIUM, 3, 6, 3, 1.5),
            (Difficulty.HARD, 4, 7, 3, 2.0),
            (Difficulty.EXPERT, 5, 8, 2, 2.5),
            (Difficulty.IMPOSSIBLE, 5, 8, 1, 3.0),
        ],
    )
    def test_tier_rules_match_game_design(
        self,
        difficulty: Difficulty,
        expected_stages: int,
        expected_minutes: int,
        expected_lives: int,
        expected_multiplier: float,
    ) -> None:
        """Verify tier rules match game-design §3.1 specifications exactly."""
        rules = difficulty.rules
        assert isinstance(rules, DifficultyRules)
        assert rules.stages == expected_stages
        assert rules.minutes_per_stage == expected_minutes
        assert rules.starting_lives == expected_lives
        assert rules.multiplier == expected_multiplier

        assert difficulty.stages == expected_stages
        assert difficulty.minutes_per_stage == expected_minutes
        assert difficulty.starting_lives == expected_lives
        assert difficulty.multiplier == expected_multiplier

    def test_rules_are_immutable(self) -> None:
        """Verify that DifficultyRules instances cannot be mutated."""
        rules = Difficulty.BEGINNER.rules
        with pytest.raises(FrozenInstanceError):
            rules.stages = 99  # type: ignore[misc]

    def test_lookup_by_string_value(self) -> None:
        """Verify parsing Difficulty from its string value."""
        assert Difficulty("beginner") is Difficulty.BEGINNER
        assert Difficulty("easy") is Difficulty.EASY
        assert Difficulty("medium") is Difficulty.MEDIUM
        assert Difficulty("hard") is Difficulty.HARD
        assert Difficulty("expert") is Difficulty.EXPERT
        assert Difficulty("impossible") is Difficulty.IMPOSSIBLE
        with pytest.raises(ValueError):
            Difficulty("unknown")
