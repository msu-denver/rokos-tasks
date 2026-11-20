"""
File: game_run.py
Description: SQLAlchemy model for a player's campaign run.
Author(s): Tyler Black
"""

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, text
from sqlalchemy.orm import Mapped, mapped_column

from src.data.database import Base


class GameRun(Base):
    """Persist stage progress, score, and timing for a player's run."""

    __tablename__ = "game_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('in_progress', 'won', 'lost', 'abandoned')",
            name="ck_game_runs_status",
        ),
        Index("ix_game_runs_user_id_status", "user_id", "status"),
        Index(
            "uq_game_runs_active_user",
            "user_id",
            unique=True,
            postgresql_where=text("status = 'in_progress'"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE")
    )
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id"))
    difficulty: Mapped[str]
    status: Mapped[str]
    lives: Mapped[int]
    current_stage: Mapped[int]
    score: Mapped[int]
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    stage_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
