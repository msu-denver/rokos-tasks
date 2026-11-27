"""
File: game_service.py
Description: Starts runs from the validated pool and exposes player progress.
Author(s): Tyler Black, Steph Rivera
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


class RunNotFoundError(LookupError):
    """The requested run is absent or belongs to another player."""


class ActiveRunExistsError(Exception):
    """Replacing the current run requires confirmation."""

    def __init__(self, run_id: int) -> None:
        """Identify the run that would be abandoned."""
        super().__init__(run_id)
        self.run_id = run_id


@dataclass(frozen=True)
class StageView:
    """Player-visible content and progress for an active stage."""

    difficulty: Difficulty
    number: int
    lives: int
    prompt: str
    input_style: str


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

    def start_run(
        self,
        user_id: int,
        difficulty: Difficulty,
        replace_active: bool = False,
        *,
        expected_active_id: int | None = None,
    ) -> GameRun:
        """Start the chosen tier and replace an active run with consent."""
        self._runs.lock_player(user_id)
        campaign = self._selector.choose(user_id, difficulty)
        active = self.active_run(user_id)
        if active is not None and (
            not replace_active or expected_active_id not in (None, active.id)
        ):
            raise ActiveRunExistsError(active.id)

        now = self._clock()
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
        """Return the player's in-progress run, if any."""
        return self._runs.active_for(user_id)

    def get_stage_view(self, user_id: int, run_id: int) -> StageView | None:
        """Return the owned run's public stage, or None for a finished run."""
        run = self._runs.get_for_user(run_id, user_id)
        if run is None:
            raise RunNotFoundError(run_id)
        if run.status != "in_progress":
            return None

        stage = self._runs.current_stage_for(run)
        return StageView(
            difficulty=Difficulty(run.difficulty),
            number=run.current_stage,
            lives=run.lives,
            prompt=stage.prompt,
            input_style=stage.input_style,
        )
