"""
File: campaign.py
Description: SQLAlchemy models for campaigns, stages, and test cases.
Author(s): Tyler Black
"""

from datetime import UTC, datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.data.database import Base


class Campaign(Base):
    """Campaign representing a multi-stage programming challenge."""

    __tablename__ = "campaigns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    difficulty: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="validated"
    )
    source: Mapped[str] = mapped_column(
        String(64), nullable=False, default="seed"
    )
    slug: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )

    stages: Mapped[list["Stage"]] = relationship(
        "Stage",
        back_populates="campaign",
        cascade="all, delete-orphan",
        order_by="Stage.number",
    )


class Stage(Base):
    """Individual stage within a campaign."""

    __tablename__ = "stages"
    __table_args__ = (
        UniqueConstraint(
            "campaign_id", "number", name="uq_stages_campaign_id_number"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    campaign_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("campaigns.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    starter_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    reference_solution: Mapped[str] = mapped_column(Text, nullable=False)

    campaign: Mapped["Campaign"] = relationship(
        "Campaign", back_populates="stages"
    )
    test_cases: Mapped[list["TestCase"]] = relationship(
        "TestCase",
        back_populates="stage",
        cascade="all, delete-orphan",
        order_by="TestCase.position",
    )


class TestCase(Base):
    """Test case (sample or hidden) associated with a stage."""

    __test__ = False
    __tablename__ = "test_cases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    stage_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("stages.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    input: Mapped[str] = mapped_column(Text, nullable=False)
    expected_output: Mapped[str] = mapped_column(Text, nullable=False)

    stage: Mapped["Stage"] = relationship("Stage", back_populates="test_cases")
