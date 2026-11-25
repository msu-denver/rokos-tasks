"""
File: test_seed_loader.py
Description: Integration tests for SeedLoader service.
Author(s): Tyler Black, Richard Hall
"""

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.business.campaigns.check_runner import TrustedSeedPlayer
from src.business.campaigns.seed_loader import (
    CampaignValidationError,
    SeedLoader,
    UntrustedCampaignError,
)
from src.business.campaigns.validator import CampaignValidator
from src.business.difficulty import Difficulty
from src.data.models.campaign import Campaign, Stage
from src.data.repositories.campaign_repository import CampaignRepository

FIXTURE_PATH = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "campaigns"
    / "valid_beginner.json"
)


class TestSeedLoader:
    """Integration test suite for SeedLoader persistence behavior."""

    def test_load_fixture_campaign(self, db_session: Session) -> None:
        """Verify loading a valid campaign fixture creates db entities."""
        repo = CampaignRepository(db_session)
        loader = SeedLoader(repo)

        campaign = loader.load_file(FIXTURE_PATH)
        assert campaign.id is not None
        assert campaign.slug == "beginner/valid_beginner"
        assert campaign.status == "validated"
        assert len(campaign.content_hash) == 64
        assert len(campaign.stages) == 2

    def test_second_run_leaves_row_counts_unchanged(
        self, db_session: Session
    ) -> None:
        """Verify second load leaves database row counts unchanged."""
        repo = CampaignRepository(db_session)
        loader = SeedLoader(repo)

        loader.load_file(FIXTURE_PATH)
        c_count_1 = db_session.scalar(select(func.count(Campaign.id)))
        s_count_1 = db_session.scalar(select(func.count(Stage.id)))

        loader.load_file(FIXTURE_PATH)
        c_count_2 = db_session.scalar(select(func.count(Campaign.id)))
        s_count_2 = db_session.scalar(select(func.count(Stage.id)))

        assert c_count_1 == c_count_2
        assert s_count_1 == s_count_2

    def test_edited_fixture_updates_in_place(
        self, db_session: Session, tmp_path: Path
    ) -> None:
        """Verify updating a campaign JSON file updates the existing record."""
        repo = CampaignRepository(db_session)
        loader = SeedLoader(repo)

        data = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        temp_file = tmp_path / "valid_beginner.json"
        temp_file.write_text(json.dumps(data), encoding="utf-8")

        initial = loader.load_file(temp_file)
        initial_id = initial.id
        assert initial.title == "Tick Ball"

        # Edit title and re-save
        data["title"] = "Updated Tick Ball Title"
        temp_file.write_text(json.dumps(data), encoding="utf-8")

        updated = loader.load_file(temp_file)
        assert updated.id == initial_id
        assert updated.title == "Updated Tick Ball Title"

    def test_reload_unchanged_file_performs_no_update(
        self, db_session: Session
    ) -> None:
        """Verify reloading unchanged file leaves id, created_at, stages."""
        repo = CampaignRepository(db_session)
        loader = SeedLoader(repo)

        initial = loader.load_file(FIXTURE_PATH)
        initial_id = initial.id
        initial_created_at = initial.created_at
        initial_stage_ids = [stage.id for stage in initial.stages]
        initial_hash = initial.content_hash

        reloaded = loader.load_file(FIXTURE_PATH)
        assert reloaded.id == initial_id
        assert reloaded.content_hash == initial_hash
        assert reloaded.created_at == initial_created_at
        assert [stage.id for stage in reloaded.stages] == initial_stage_ids

    def test_editing_prompt_keeps_same_stage_ids(
        self, db_session: Session, tmp_path: Path
    ) -> None:
        """Verify editing stage prompt modifies prompt and keeps stage ids."""
        repo = CampaignRepository(db_session)
        loader = SeedLoader(repo)

        data = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        temp_file = tmp_path / "valid_beginner.json"
        temp_file.write_text(json.dumps(data), encoding="utf-8")

        initial = loader.load_file(temp_file)
        initial_stage_ids = [stage.id for stage in initial.stages]

        new_prompt = "Print the board with one `O` in the middle."
        data["stages"][0]["prompt"] = new_prompt
        temp_file.write_text(json.dumps(data), encoding="utf-8")

        updated = loader.load_file(temp_file)
        assert updated.id == initial.id
        assert [stage.id for stage in updated.stages] == initial_stage_ids
        assert updated.stages[0].prompt == new_prompt

    def test_removing_stage_deletes_only_that_one(
        self, db_session: Session, tmp_path: Path
    ) -> None:
        """Verify removing a stage deletes only that stage from database."""
        repo = CampaignRepository(db_session)
        loader = SeedLoader(repo)

        data = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        temp_file = tmp_path / "valid_beginner.json"
        temp_file.write_text(json.dumps(data), encoding="utf-8")

        initial = loader.load_file(temp_file)
        assert len(initial.stages) == 2
        stage1_id = initial.stages[0].id
        stage2_id = initial.stages[1].id

        data["stages"] = [data["stages"][0]]
        temp_file.write_text(json.dumps(data), encoding="utf-8")

        with patch.object(CampaignValidator, "validate", return_value=[]):
            updated = loader.load_file(temp_file)
        assert len(updated.stages) == 1
        assert updated.stages[0].id == stage1_id

        deleted_stage = db_session.get(Stage, stage2_id)
        assert deleted_stage is None

    def test_quarantined_campaign_stays_quarantined_after_reload(
        self, db_session: Session, tmp_path: Path
    ) -> None:
        """Verify quarantined campaign status is preserved on reload."""
        repo = CampaignRepository(db_session)
        loader = SeedLoader(repo)

        data = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        temp_file = tmp_path / "valid_beginner.json"
        temp_file.write_text(json.dumps(data), encoding="utf-8")

        initial = loader.load_file(temp_file)
        initial.status = "quarantined"
        db_session.flush()

        data["title"] = "Quarantined Challenge Modified"
        temp_file.write_text(json.dumps(data), encoding="utf-8")

        updated = loader.load_file(temp_file)
        assert updated.id == initial.id
        assert updated.title == "Quarantined Challenge Modified"
        assert updated.status == "quarantined"

    def test_validated_for_returns_only_validated_tier(
        self, db_session: Session
    ) -> None:
        """Verify validated_for returns newly loaded campaign for its tier."""
        repo = CampaignRepository(db_session)
        loader = SeedLoader(repo)

        loader.load_file(FIXTURE_PATH)
        beginner_campaigns = repo.validated_for(Difficulty.BEGINNER)
        assert len(beginner_campaigns) == 1
        assert beginner_campaigns[0].slug == "beginner/valid_beginner"

        easy_campaigns = repo.validated_for(Difficulty.EASY)
        assert len(easy_campaigns) == 0

    def test_invalid_campaign_raises_validation_error(
        self, db_session: Session
    ) -> None:
        """Verify invalid campaign data is rejected without touching db."""
        repo = CampaignRepository(db_session)
        loader = SeedLoader(repo)

        data = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        data["difficulty"] = "invalid_tier"

        with pytest.raises(CampaignValidationError) as exc_info:
            loader.load_campaign_data(data, slug="beginner/broken")
        assert len(exc_info.value.errors) > 0

    def test_load_directory(self, db_session: Session, tmp_path: Path) -> None:
        """Verify load_directory loads all campaign files in a folder tree."""
        repo = CampaignRepository(db_session)
        loader = SeedLoader(repo)

        data = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        dir_a = tmp_path / "beginner"
        dir_a.mkdir()
        (dir_a / "c1.json").write_text(json.dumps(data), encoding="utf-8")
        (dir_a / "schema.json").write_text("{}", encoding="utf-8")

        loaded = loader.load_directory(tmp_path)
        assert len(loaded) == 1
        assert loaded[0].slug == "beginner/c1"

        # Empty directory returns empty list
        assert loader.load_directory(tmp_path / "empty_dir") == []

    def test_rejects_non_object_json(
        self, db_session: Session, tmp_path: Path
    ) -> None:
        """Reject a JSON array through the campaign validation path."""
        seed_file = tmp_path / "invalid.json"
        seed_file.write_text("[]", encoding="utf-8")
        loader = SeedLoader(CampaignRepository(db_session))

        with pytest.raises(CampaignValidationError, match="Schema error"):
            loader.load_file(seed_file)


class TestCheckScriptStorage:
    """The seed loader stores each stage's check script and reference."""

    def test_check_scripts_are_stored(self, db_session: Session) -> None:
        """Loading a campaign saves every stage's check script."""
        loader = SeedLoader(CampaignRepository(db_session))
        campaign = loader.load_file(FIXTURE_PATH)
        data = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        assert [
            (stage.check_script, stage.reference_program)
            for stage in campaign.stages
        ] == [
            (stage["check_script"], stage["reference_program"])
            for stage in data["stages"]
        ]

    def test_edited_check_script_updates_in_place(
        self, db_session: Session
    ) -> None:
        """Reloading an edited check script updates the same stage row."""
        repo = CampaignRepository(db_session)
        loader = SeedLoader(repo)
        data = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        first = loader.load_campaign_data(data, slug="beginner/tick")
        stage_id = first.stages[0].id
        data["stages"][0]["check_script"] += "    game.tick('go')\n"
        second = loader.load_campaign_data(data, slug="beginner/tick")
        assert second.stages[0].id == stage_id
        assert second.stages[0].check_script.endswith("game.tick('go')\n")


class TestUntrustedCampaigns:
    """Only hand-written seeds may be validated on the host (#36)."""

    def test_untrusted_campaign_needs_a_player(
        self, db_session: Session
    ) -> None:
        """An LLM campaign without a runner player is refused unplayed."""
        loader = SeedLoader(CampaignRepository(db_session))
        data = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        with (
            patch.object(CampaignValidator, "validate") as validate,
            pytest.raises(UntrustedCampaignError, match="in the runner"),
        ):
            loader.load_campaign_data(data, slug="beginner/x", source="llm")
        validate.assert_not_called()

    def test_untrusted_campaign_uses_the_given_player(
        self, db_session: Session
    ) -> None:
        """With a player, validation plays everything through it."""
        loader = SeedLoader(CampaignRepository(db_session))
        data = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        player = TrustedSeedPlayer()
        with patch.object(player, "grade", wraps=player.grade) as grade:
            campaign = loader.load_campaign_data(
                data, slug="beginner/x", source="llm", player=player
            )
        assert campaign.source == "llm"
        assert grade.called
