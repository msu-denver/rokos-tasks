"""
File: submission.py
Description: SQLAlchemy model for an applied stage submission and verdict.
Author(s): Tyler Black
"""

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.data.database import Base


class Submission(Base):
    """Store a graded program and the timing and outcome of its attempt."""

    __tablename__ = "submissions"
    __table_args__ = (
        CheckConstraint(
            "failure_kind IN ('rule','crashed','exited','turn_timeout',"
            "'run_timeout','output_limit')",
            name="ck_submissions_failure_kind",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("game_runs.id", ondelete="CASCADE"), index=True
    )
    stage_number: Mapped[int]
    code: Mapped[str] = mapped_column(Text)
    passed: Mapped[bool]
    failure_kind: Mapped[str | None] = mapped_column(String(32))
    failed_rule: Mapped[str | None] = mapped_column(Text)
    failed_turn: Mapped[int | None]
    seconds_remaining: Mapped[int]
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
