"""
File: seed_loader.py
Description: Validates and loads seed campaign files into the database.
Author(s): Tyler Black
"""

import hashlib
import json
from pathlib import Path
from typing import Any

from src.business.campaigns.validator import CampaignValidator
from src.data.models.campaign import Campaign, Stage, TestCase
from src.data.repositories.campaign_repository import CampaignRepository


class CampaignValidationError(Exception):
    """Raised when a campaign fails validation during loading."""

    def __init__(self, errors: list[str]) -> None:
        """Initialize with validation error messages."""
        super().__init__("; ".join(errors))
        self.errors = errors


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
    ) -> Campaign:
        """Validate and upsert a campaign from a data dictionary.

        Args:
            data: Parsed campaign dictionary.
            slug: Unique slug identifier for the campaign.
            source: Campaign origin source (default 'seed').

        Returns:
            The persisted Campaign instance.

        Raises:
            CampaignValidationError: If validation fails.
        """
        errors = CampaignValidator.validate(data, filename=slug)
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
            stage = Stage(
                number=stage_data["stage"],
                prompt=stage_data["prompt"],
                starter_code=stage_data.get("starter_code"),
                reference_solution=stage_data["reference_solution"],
            )
            position = 1
            for sample in stage_data.get("samples", []):
                test_case = TestCase(
                    kind="sample",
                    position=position,
                    input=sample["input"],
                    expected_output=sample["expected_output"],
                )
                stage.test_cases.append(test_case)
                position += 1
            for hidden in stage_data.get("hidden_tests", []):
                test_case = TestCase(
                    kind="hidden",
                    position=position,
                    input=hidden["input"],
                    expected_output=hidden["expected_output"],
                )
                stage.test_cases.append(test_case)
                position += 1
            campaign.stages.append(stage)

        return self._repo.upsert(campaign)

    def load_file(self, path: Path | str) -> Campaign:
        """Load a single campaign JSON file into the database.

        The slug is generated as '<tier>/<file stem>'
        (for example 'beginner/two_sum').

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
