"""
File: checkpoint.py
Description: SQLAlchemy model for code saved after a stage pass.
Author(s): Tyler Black
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.data.database import Base


class Checkpoint(Base):
    """Store the passing program for one stage of a run."""

    __tablename__ = "checkpoints"
    __table_args__ = (
        UniqueConstraint(
            "run_id", "stage_number", name="uq_checkpoints_run_id_stage_number"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("game_runs.id", ondelete="CASCADE"), index=True
    )
    stage_number: Mapped[int]
    code: Mapped[str] = mapped_column(Text)
    saved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
