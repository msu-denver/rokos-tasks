"""
File: campaign_repository.py
Description: Repository for Campaign entity persistence and queries.
Author(s): Tyler Black, Steph Rivera
"""

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from src.data.models.campaign import Campaign, Stage
from src.data.repositories.base_repository import BaseRepository


class CampaignRepository(BaseRepository[Campaign]):
    """Repository handling database operations for campaigns."""

    model_cls = Campaign

    def __init__(self, session: Session) -> None:
        """Initialize with session and Campaign model class."""
        super().__init__(session, model_cls=Campaign)

    def get_by_slug(self, slug: str) -> Campaign | None:
        """Retrieve a campaign by its unique slug.

        Args:
            slug: Unique slug identifier (e.g. 'beginner/two_sum').

        Returns:
            The Campaign instance if found, or None.
        """
        stmt = (
            select(Campaign)
            .where(Campaign.slug == slug)
            .options(selectinload(Campaign.stages))
        )
        return self._session.execute(stmt).scalar_one_or_none()

    def upsert(self, campaign: Campaign) -> Campaign:
        """Insert a new campaign or update an existing one by slug.

        If a campaign with the given slug already exists and its
        content_hash matches, return it untouched without database writes.
        If the hash differs, update title, difficulty, and content_hash,
        preserve the existing status, and update stages in place by stage
        number (updating existing rows, adding new numbers, and removing
        deleted numbers).

        Args:
            campaign: Campaign instance to persist.

        Returns:
            The persisted or updated Campaign instance.
        """
        existing = self.get_by_slug(campaign.slug)
        if existing is None:
            campaign.status = "validated"
            return self.add(campaign)

        if existing.content_hash == campaign.content_hash:
            return existing

        existing.title = campaign.title
        existing.difficulty = campaign.difficulty
        existing.content_hash = campaign.content_hash
        existing.source = campaign.source

        incoming_by_num = {stage.number: stage for stage in campaign.stages}
        existing_by_num = {stage.number: stage for stage in existing.stages}

        # Remove stages whose numbers no longer exist in incoming campaign
        for stage in list(existing.stages):
            if stage.number not in incoming_by_num:
                existing.stages.remove(stage)

        # Update existing stages in place or append newly added stages
        for number, incoming_stage in incoming_by_num.items():
            if number in existing_by_num:
                current_stage = existing_by_num[number]
                current_stage.prompt = incoming_stage.prompt
                current_stage.input_style = incoming_stage.input_style
                current_stage.reference_program = (
                    incoming_stage.reference_program
                )
                current_stage.check_script = incoming_stage.check_script
            else:
                existing.stages.append(
                    Stage(
                        number=incoming_stage.number,
                        prompt=incoming_stage.prompt,
                        input_style=incoming_stage.input_style,
                        reference_program=incoming_stage.reference_program,
                        check_script=incoming_stage.check_script,
                    )
                )

        existing.stages.sort(key=lambda s: s.number)
        self._session.flush()
        return existing

    def validated_for(self, difficulty: str) -> Sequence[Campaign]:
        """Retrieve all validated campaigns for a given difficulty tier.

        Args:
            difficulty: Lowercase difficulty name.

        Returns:
            List of validated campaigns for that tier.
        """
        stmt = (
            select(Campaign)
            .where(
                Campaign.difficulty == difficulty,
                Campaign.status == "validated",
            )
            .options(selectinload(Campaign.stages))
            .order_by(Campaign.id)
        )
        return self._session.execute(stmt).scalars().all()

    def validated_difficulties(self) -> set[str]:
        """List tiers that have at least one validated campaign."""
        query = (
            select(Campaign.difficulty)
            .where(Campaign.status == "validated")
            .distinct()
        )
        return set(self._session.scalars(query))
