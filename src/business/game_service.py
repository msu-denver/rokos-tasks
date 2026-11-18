"""
File: game_service.py
Description: Starts runs from the validated pool and exposes player progress.
Author(s): Tyler Black
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from src.business.campaign_selector import CampaignSelector
from src.business.difficulty import Difficulty
from src.data.models.game_run import GameRun
from src.data.repositories.run_repository import RunRepository


@dataclass(frozen=True)
class TierOverview:
    """Display rules and availability for a tier on the start screen."""

    difficulty: Difficulty
    available: bool


class GameService:
    """Coordinate the start screen, run assignment, and run ownership."""

    def __init__(
        self,
        selector: CampaignSelector,
        runs: RunRepository,
        clock: Callable[[], datetime],
    ) -> None:
        """Configure the campaign selector, run repository, and clock."""
        self._selector = selector
        self._runs = runs
        self._clock = clock

    def start_run(self, user_id: int, difficulty: Difficulty) -> GameRun:
        """Replace any active run with a new run in the chosen tier."""
        self._runs.lock_player(user_id)
        campaign = self._selector.choose(user_id, difficulty)
        now = self._clock()

        active = self.active_run(user_id)
        if active is not None:
            active.status = "abandoned"
            active.score = 0
            active.ended_at = now

        run = GameRun(
            user_id=user_id,
            campaign_id=campaign.id,
            difficulty=difficulty.value,
            status="in_progress",
            lives=difficulty.starting_lives,
            current_stage=1,
            score=0,
            started_at=now,
            stage_started_at=now,
        )
        self._runs.add(run)
        self._runs.commit()
        return run

    def tier_overview(self) -> list[TierOverview]:
        """Return rules for all tiers and flag which ones can start."""
        available = self._selector.available_difficulties()
        return [
            TierOverview(difficulty, difficulty in available)
            for difficulty in Difficulty
        ]

    def active_run(self, user_id: int) -> GameRun | None:
        """Return the player's in-progress run for the resume link."""
        return self._runs.active_for(user_id)

    def get_run(self, run_id: int, user_id: int) -> GameRun | None:
        """Return run progress only to the player who owns it."""
        return self._runs.get_for_user(run_id, user_id)
