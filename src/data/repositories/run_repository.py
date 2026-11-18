"""
File: run_repository.py
Description: Persists runs and queries each player's progress and history.
Author(s): Tyler Black
"""

from datetime import datetime

from sqlalchemy import func, select

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
