"""
File: campaign_selector.py
Description: Chooses a validated campaign based on a player's run history.
Author(s): Tyler Black
"""

from src.business.difficulty import Difficulty
from src.data.models.campaign import Campaign
from src.data.repositories.campaign_repository import CampaignRepository
from src.data.repositories.run_repository import RunRepository


class NoCampaignAvailableError(Exception):
    """Raised when a difficulty has no validated campaigns."""


class CampaignSelector:
    """Assign an unplayed campaign or the one started least recently."""

    def __init__(
        self, campaigns: CampaignRepository, runs: RunRepository
    ) -> None:
        """Use the repositories for the campaign pool and run history."""
        self._campaigns = campaigns
        self._runs = runs

    def choose(self, user_id: int, difficulty: Difficulty) -> Campaign:
        """Choose an eligible campaign, breaking ties by lowest ID."""
        campaigns = self._campaigns.validated_for(difficulty)
        if not campaigns:
            raise NoCampaignAvailableError(difficulty.value)

        last_started = self._runs.last_started_by_user(user_id)
        unplayed = [
            campaign
            for campaign in campaigns
            if campaign.id not in last_started
        ]
        if unplayed:
            return min(unplayed, key=lambda campaign: campaign.id)

        return min(
            campaigns,
            key=lambda campaign: (last_started[campaign.id], campaign.id),
        )

    def available_difficulties(self) -> set[str]:
        """Return the difficulty names present in the validated pool."""
        return self._campaigns.validated_difficulties()
