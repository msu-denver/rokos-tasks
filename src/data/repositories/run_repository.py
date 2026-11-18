"""
File: run_repository.py
Description: Persists runs and queries each player's progress and history.
Author(s): Tyler Black
"""

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import load_only

from src.data.models.campaign import Stage, TestCase
from src.data.models.game_run import GameRun
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

    def current_stage_for(self, run: GameRun) -> Stage:
        """Load the current stage's prompt and starter code for play."""
        query = (
            select(Stage)
            .where(
                Stage.campaign_id == run.campaign_id,
                Stage.number == run.current_stage,
            )
            .options(load_only(Stage.id, Stage.prompt, Stage.starter_code))
        )
        return self._session.scalars(query).one()

    def samples_for_stage(self, stage_id: int) -> Sequence[TestCase]:
        """Retrieve only a stage's public examples in campaign order."""
        query = (
            select(TestCase)
            .where(TestCase.stage_id == stage_id, TestCase.kind == "sample")
            .order_by(TestCase.position)
        )
        return self._session.scalars(query).all()

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
