"""
File: seed_loader.py
Description: Validates and loads seed campaign files into the database.
    Only trusted seed content may use the local validation player.
Author(s): Tyler Black, Steph Rivera
"""

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

from src.business.campaigns.check_runner import (
    CheckPlayer,
    TrustedSeedPlayer,
    host_play_supported,
)
from src.business.campaigns.validator import CampaignValidator
from src.data.models.campaign import Campaign, Stage
from src.data.repositories.campaign_repository import CampaignRepository

logger = logging.getLogger(__name__)


class CampaignValidationError(Exception):
    """Raised when a campaign fails validation during loading."""

    def __init__(self, errors: list[str]) -> None:
        """Initialize with validation error messages."""
        super().__init__("; ".join(errors))
        self.errors = errors


class UntrustedCampaignError(ValueError):
    """An untrusted campaign was loaded without a runner-backed player."""


class SeedLoader:
    """Service that validates seed files and persists them via repository."""

    def __init__(self, campaign_repo: CampaignRepository) -> None:
        """Initialize with campaign repository dependency."""
        self._repo = campaign_repo

    def load_campaign_data(
        self,
        data: dict[str, Any],
        slug: str,
        source: str = "seed",
        player: CheckPlayer | None = None,
    ) -> Campaign:
        """Validate and upsert a campaign from a data dictionary.

        Args:
            data: Parsed campaign dictionary.
            slug: Unique slug identifier for the campaign.
            source: Campaign origin source (default 'seed').
            player: Plays the campaign's programs during validation.
                Required for anything but a hand-written seed, because
                the default player runs programs on this host unsandboxed.

        Returns:
            The persisted Campaign instance.

        Raises:
            UntrustedCampaignError: If a non-seed campaign has no player.
            CampaignValidationError: If validation fails.
        """
        if player is None:
            if source != "seed":
                raise UntrustedCampaignError(
                    f"a {source} campaign must be validated in the runner"
                )
            if host_play_supported():
                player = TrustedSeedPlayer()
        if player is None:
            # Windows can't play programs locally, and seeds are committed
            # files that Linux CI plays in full on every PR.
            logger.warning(
                "%s: this machine can't play programs, so only the checks "
                "that don't play one ran; CI runs the rest",
                slug,
            )
            errors = CampaignValidator.validate_structure(data, filename=slug)
        else:
            errors = CampaignValidator.validate(
                data, filename=slug, player=player
            )
        if errors:
            raise CampaignValidationError(errors)

        canonical_json = json.dumps(data, sort_keys=True)
        content_hash = hashlib.sha256(canonical_json.encode()).hexdigest()

        campaign = Campaign(
            title=data["title"],
            difficulty=data["difficulty"],
            status="validated",
            source=source,
            slug=slug,
            content_hash=content_hash,
        )

        for stage_data in data["stages"]:
            campaign.stages.append(
                Stage(
                    number=stage_data["stage"],
                    prompt=stage_data["prompt"],
                    input_style=stage_data["input"],
                    reference_program=stage_data["reference_program"],
                    check_script=stage_data["check_script"],
                )
            )

        return self._repo.upsert(campaign)

    def load_file(self, path: Path | str) -> Campaign:
        """Load a single campaign JSON file into the database.

        The slug is generated as '<tier>/<file stem>'
        (for example 'medium/pong').

        Args:
            path: Path to the campaign JSON file.

        Returns:
            The persisted Campaign instance.
        """
        file_path = Path(path)
        data = json.loads(file_path.read_text(encoding="utf-8"))
        tier = file_path.parent.name
        if isinstance(data, dict):
            difficulty = data.get("difficulty")
            if isinstance(difficulty, str):
                tier = difficulty
        slug = f"{tier}/{file_path.stem}"
        return self.load_campaign_data(data, slug=slug, source="seed")

    def load_directory(self, directory: Path | str) -> list[Campaign]:
        """Find and load all campaign JSON files under directory recursively.

        Args:
            directory: Root directory to search for campaign JSON files.

        Returns:
            List of successfully loaded Campaign instances.
        """
        root = Path(directory)
        loaded: list[Campaign] = []
        if not root.exists():
            return loaded
        for path in sorted(root.rglob("*.json")):
            if path.name == "schema.json":
                continue
            loaded.append(self.load_file(path))
        return loaded
