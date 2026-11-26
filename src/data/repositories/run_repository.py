"""
File: run_repository.py
Description: Persists runs and queries each player's progress and history.
Author(s): Tyler Black, Richard Hall
"""

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import load_only

from src.data.models.campaign import Stage
from src.data.models.checkpoint import Checkpoint
from src.data.models.game_run import GameRun
from src.data.models.submission import Submission
from src.data.models.user import User
from src.data.repositories.base_repository import BaseRepository


class RunRepository(BaseRepository[GameRun]):
    """Store game runs and scope run access to their owners."""

    model_cls = GameRun

    def lock_player(self, user_id: int) -> None:
        """Serialize starts for this player until the transaction ends."""
        query = select(User.id).where(User.id == user_id).with_for_update()
        self._session.execute(query).scalar_one()

    def get_for_user(self, run_id: int, user_id: int) -> GameRun | None:
        """Retrieve a run only if it belongs to the given player."""
        query = select(GameRun).where(
            GameRun.id == run_id, GameRun.user_id == user_id
        )
        return self._session.scalars(query).one_or_none()

    def lock_for_user(self, run_id: int, user_id: int) -> GameRun | None:
        """Lock the owned run and refresh any previously loaded state."""
        query = (
            select(GameRun)
            .where(GameRun.id == run_id, GameRun.user_id == user_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return self._session.scalars(query).one_or_none()

    def current_stage_for(self, run: GameRun) -> Stage:
        """Load the current stage's prompt for play."""
        query = (
            select(Stage)
            .where(
                Stage.campaign_id == run.campaign_id,
                Stage.number == run.current_stage,
            )
            .options(load_only(Stage.id, Stage.prompt))
        )
        return self._session.scalars(query).one()

    def check_script_for(self, run: GameRun) -> str | None:
        """Return the current stage's check script if available."""
        query = select(Stage.check_script).where(
            Stage.campaign_id == run.campaign_id,
            Stage.number == run.current_stage,
        )
        return self._session.scalars(query).one_or_none()

    def stage_count(self, run: GameRun) -> int:
        """Count the stages in the run's campaign."""
        query = (
            select(func.count())
            .select_from(Stage)
            .where(Stage.campaign_id == run.campaign_id)
        )
        return self._session.execute(query).scalar_one()

    def save_checkpoint(self, checkpoint: Checkpoint) -> Checkpoint:
        """Add a passing program to the current transaction."""
        self._session.add(checkpoint)
        return checkpoint

    def add_submission(self, submission: Submission) -> Submission:
        """Add a graded attempt to the current transaction."""
        self._session.add(submission)
        return submission

    def latest_checkpoint(self, run: GameRun) -> Checkpoint | None:
        """Return the checkpoint from the last stage before the run's own.

        Only stages below ``run.current_stage`` count, so a page that read
        the run just before a pass never pairs its stage with that pass.
        """
        query = (
            select(Checkpoint)
            .where(
                Checkpoint.run_id == run.id,
                Checkpoint.stage_number < run.current_stage,
            )
            .order_by(Checkpoint.stage_number.desc())
            .limit(1)
        )
        return self._session.scalars(query).one_or_none()

    def passed_submissions(self, run: GameRun) -> list[Submission]:
        """List the run's passing submissions in stage order."""
        query = (
            select(Submission)
            .where(Submission.run_id == run.id, Submission.passed.is_(True))
            .order_by(Submission.stage_number)
        )
        return list(self._session.scalars(query))

    def active_for(self, user_id: int) -> GameRun | None:
        """Retrieve the player's current in-progress run, if any."""
        query = select(GameRun).where(
            GameRun.user_id == user_id, GameRun.status == "in_progress"
        )
        return self._session.scalars(query).one_or_none()

    def last_started_by_user(self, user_id: int) -> dict[int, datetime]:
        """Map each campaign played by this user to its latest start time."""
        query = (
            select(GameRun.campaign_id, func.max(GameRun.started_at))
            .where(GameRun.user_id == user_id)
            .group_by(GameRun.campaign_id)
        )
        return dict(self._session.execute(query).all())
