"""
File: game_service.py
Description: Starts runs, applies stage verdicts, and exposes progress.
Author(s): Tyler Black
"""

from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import datetime

from src.business.campaign_selector import CampaignSelector
from src.business.difficulty import Difficulty
from src.business.grading_service import (
    GradingService,
    RunFinishedError,
    Verdict,
)
from src.business.grading_service import RunNotFoundError as RunNotFoundError
from src.business.score_calculator import ScoreCalculator
from src.data.models.checkpoint import Checkpoint
from src.data.models.game_run import GameRun
from src.data.models.submission import Submission
from src.data.repositories.run_repository import RunRepository


@dataclass(frozen=True)
class TierOverview:
    """Display rules and availability for a tier on the start screen."""

    difficulty: Difficulty
    available: bool


class StaleSubmitError(Exception):
    """The run changed while grading."""


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
    checkpoint_code: str | None = None


@dataclass(frozen=True)
class RunState:
    """The run's state immediately after applying a verdict."""

    status: str
    lives: int
    stage: int
    score: int
    stage_points: int


@dataclass(frozen=True)
class SubmitResult:
    """A verdict, updated progress, and code to restore in the editor."""

    verdict: Verdict
    run: RunState
    next_stage: StageView | None
    checkpoint_code: str | None

    def to_dict(self) -> dict:
        """Return the response payload for a counted submission."""
        stage = self.next_stage
        return {
            "verdict": self.verdict.to_dict(),
            "run": asdict(self.run),
            "stage": {"number": stage.number, "prompt": stage.prompt}
            if stage is not None
            else None,
            "checkpoint": self.checkpoint_code,
        }


@dataclass(frozen=True)
class ResultRow:
    """The points earned for a passed stage."""

    stage: int
    points: int


@dataclass(frozen=True)
class ResultView:
    """Score breakdown for a won or lost run."""

    difficulty: Difficulty
    status: str
    rows: tuple[ResultRow, ...]
    total: int


class GameService:
    """Coordinate run assignment, stage submissions, and game results."""

    def __init__(
        self,
        selector: CampaignSelector,
        runs: RunRepository,
        clock: Callable[[], datetime],
        *,
        grading: GradingService | None = None,
    ) -> None:
        """Configure run dependencies and optional stage grading."""
        self._selector = selector
        self._runs = runs
        self._clock = clock
        self._grading = grading

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
        active = self._locked_active_run(user_id)
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
        run = self._owned_run(user_id, run_id)
        if run.status != "in_progress":
            return None
        return self._stage_view(run, self._checkpoint_code(run))

    def submit_stage(
        self, user_id: int, run_id: int, code: str, stage: int
    ) -> SubmitResult:
        """Grade and apply one attempt if the run still matches its snapshot.

        Args:
            user_id: The player submitting.
            run_id: One of the player's runs.
            code: The program in the editor.
            stage: The stage the player's page shows.

        Returns:
            The verdict and the run's state after applying it.

        Raises:
            RuntimeError: If no grading service was configured.
            RunNotFoundError: If the player does not own the run.
            RunFinishedError: If the run has already finished.
            StaleSubmitError: If the page shows another stage, or the run
                changed during grading.
        """
        if self._grading is None:
            raise RuntimeError("no grading service configured")
        arrived = self._clock()
        run = self._owned_run(user_id, run_id)
        if run.status != "in_progress":
            raise RunFinishedError(run_id)
        if run.current_stage != stage:
            # An old tab must not spend a life on a stage it never showed.
            raise StaleSubmitError("the page shows another stage")
        started = run.stage_started_at
        difficulty = Difficulty(run.difficulty)
        seconds_remaining = ScoreCalculator.seconds_remaining(
            difficulty.minutes_per_stage * 60, started, arrived
        )
        verdict = self._grading.grade(user_id, run_id, code)
        run = self._lock_snapshot(user_id, run_id, stage, started)
        submission = Submission(
            run_id=run_id,
            stage_number=stage,
            code=code,
            passed=verdict.passed,
            failure_kind=verdict.kind,
            failed_rule=verdict.reason if verdict.kind == "rule" else None,
            failed_turn=None if verdict.passed else verdict.turn,
            seconds_remaining=seconds_remaining,
            submitted_at=arrived,
        )
        result = self._apply_verdict(run, submission, verdict, difficulty)
        self._runs.commit()
        return result

    def get_result_view(self, user_id: int, run_id: int) -> ResultView | None:
        """Return the owned run's score breakdown if it was won or lost."""
        run = self._owned_run(user_id, run_id)
        if run.status not in ("won", "lost"):
            return None
        difficulty = Difficulty(run.difficulty)
        rows = tuple(
            ResultRow(
                sub.stage_number,
                ScoreCalculator.stage_points(
                    sub.seconds_remaining, difficulty
                ),
            )
            for sub in self._runs.passed_submissions(run)
        )
        return ResultView(difficulty, run.status, rows, run.score)

    def _owned_run(self, user_id: int, run_id: int) -> GameRun:
        run = self._runs.get_for_user(run_id, user_id)
        if run is None:
            raise RunNotFoundError(run_id)
        return run

    def _locked_active_run(self, user_id: int) -> GameRun | None:
        active = self._runs.active_for(user_id)
        if active is None:
            return None
        # A final submit may win or lose this run while we wait for its
        # lock, and then it is no longer ours to abandon.
        locked = self._runs.lock_for_user(active.id, user_id)
        if locked is None or locked.status != "in_progress":
            return None
        return locked

    def _lock_snapshot(
        self, user_id: int, run_id: int, stage: int, started: datetime
    ) -> GameRun:
        run = self._runs.lock_for_user(run_id, user_id)
        if (
            run is None
            or run.status != "in_progress"
            or (run.current_stage, run.stage_started_at) != (stage, started)
        ):
            self._runs.rollback()
            raise StaleSubmitError("the run changed while grading")
        return run

    def _stage_view(
        self, run: GameRun, checkpoint_code: str | None
    ) -> StageView:
        stage = self._runs.current_stage_for(run)
        return StageView(
            difficulty=Difficulty(run.difficulty),
            number=run.current_stage,
            lives=run.lives,
            prompt=stage.prompt,
            checkpoint_code=checkpoint_code,
        )

    def _checkpoint_code(self, run: GameRun) -> str | None:
        checkpoint = self._runs.latest_checkpoint(run)
        return checkpoint.code if checkpoint is not None else None

    def _apply_verdict(
        self,
        run: GameRun,
        submission: Submission,
        verdict: Verdict,
        difficulty: Difficulty,
    ) -> SubmitResult:
        applied = self._clock()
        self._runs.add_submission(submission)
        next_stage = None
        if verdict.passed:
            points = ScoreCalculator.stage_points(
                submission.seconds_remaining, difficulty
            )
            self._apply_pass(run, submission, points, applied)
            if run.status == "in_progress":
                next_stage = self._stage_view(run, submission.code)
        else:
            points = 0
            self._apply_fail(run, applied)
        # Capture the state while the run is still locked.
        state = RunState(
            run.status, run.lives, run.current_stage, run.score, points
        )
        # A finished run has no editor left to restore.
        checkpoint_code = (
            self._checkpoint_code(run) if run.status == "in_progress" else None
        )
        return SubmitResult(verdict, state, next_stage, checkpoint_code)

    def _apply_pass(
        self,
        run: GameRun,
        submission: Submission,
        points: int,
        applied: datetime,
    ) -> None:
        self._runs.save_checkpoint(
            Checkpoint(
                run_id=run.id,
                stage_number=submission.stage_number,
                code=submission.code,
                saved_at=applied,
            )
        )
        run.score += points
        if run.current_stage >= self._runs.stage_count(run):
            run.status = "won"
            run.ended_at = applied
        else:
            run.current_stage += 1
            run.stage_started_at = applied

    def _apply_fail(self, run: GameRun, applied: datetime) -> None:
        run.lives -= 1
        if run.lives == 0:
            run.status = "lost"
            run.score = 0
            run.ended_at = applied
        else:
            run.stage_started_at = applied
