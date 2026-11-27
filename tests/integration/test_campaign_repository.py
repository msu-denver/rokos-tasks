"""
File: test_campaign_repository.py
Description: Integration tests for CampaignRepository persistence operations.
Author(s): Tyler Black, Steph Rivera
"""

import hashlib

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.business.difficulty import Difficulty
from src.data.models.campaign import Campaign, Stage
from src.data.repositories.campaign_repository import CampaignRepository


def _make_campaign(
    slug: str,
    title: str,
    difficulty: str = "beginner",
    content_hash: str | None = None,
) -> Campaign:
    """Helper to build a campaign with 2 stages and check scripts."""
    if content_hash is None:
        content_hash = hashlib.sha256(
            f"{slug}:{title}:{difficulty}".encode()
        ).hexdigest()
    campaign = Campaign(
        title=title,
        difficulty=difficulty,
        status="validated",
        source="seed",
        slug=slug,
        content_hash=content_hash,
    )
    for num in (1, 2):
        campaign.stages.append(
            Stage(
                number=num,
                prompt=f"Stage {num} prompt.",
                input_style="lines",
                reference_program="print(1)",
                check_script=f"def check(game):\n    game.send('{num}')\n",
            )
        )
    return campaign


class TestCampaignRepository:
    """Integration test suite for CampaignRepository against PostgreSQL."""

    def test_add_and_get_by_slug(self, db_session: Session) -> None:
        """Verify adding a campaign and retrieving it by slug."""
        repo = CampaignRepository(db_session)
        campaign = _make_campaign("beginner/test_add", "Test Add")
        repo.add(campaign)

        db_session.expire_all()

        retrieved = repo.get_by_slug("beginner/test_add")
        assert retrieved is not None
        assert retrieved.id == campaign.id
        assert retrieved.title == "Test Add"
        assert len(retrieved.stages) == 2
        assert retrieved.stages[0].number == 1
        assert retrieved.stages[1].number == 2
        assert retrieved.stages[0].input_style == "lines"
        assert retrieved.stages[1].input_style == "lines"
        assert retrieved.stages[1].check_script.endswith("send('2')\n")

    def test_upsert_inserts_new_campaign(self, db_session: Session) -> None:
        """Verify upsert inserts when no campaign with slug exists."""
        repo = CampaignRepository(db_session)
        campaign = _make_campaign("beginner/new_slug", "New Slug Campaign")
        result = repo.upsert(campaign)

        assert result.id is not None

        db_session.expire_all()

        saved = repo.get_by_slug("beginner/new_slug")
        assert saved is not None
        assert saved.title == "New Slug Campaign"
        assert saved.stages[0].input_style == "lines"
        assert saved.stages[1].input_style == "lines"

    def test_upsert_updates_existing_in_place(
        self, db_session: Session
    ) -> None:
        """Verify upsert modifies fields and updates stages in place."""
        repo = CampaignRepository(db_session)
        initial = _make_campaign("beginner/update_test", "Original Title")
        repo.add(initial)
        campaign_id = initial.id
        stage1_id = initial.stages[0].id
        stage2_id = initial.stages[1].id

        updated = _make_campaign("beginner/update_test", "Modified Title")
        updated.stages[0].prompt = "Brand new prompt 1."
        updated.stages[0].input_style = "keys"
        result = repo.upsert(updated)

        assert result.id == campaign_id
        assert result.title == "Modified Title"

        db_session.expire_all()

        loaded = repo.get_by_slug("beginner/update_test")
        assert loaded is not None
        assert loaded.title == "Modified Title"
        assert loaded.stages[0].prompt == "Brand new prompt 1."
        assert loaded.stages[0].input_style == "keys"
        assert loaded.stages[1].input_style == "lines"
        assert loaded.stages[0].id == stage1_id
        assert loaded.stages[1].id == stage2_id

    def test_upsert_matching_content_hash_returns_untouched(
        self, db_session: Session
    ) -> None:
        """Verify matching content_hash causes no writes and returns entity."""
        repo = CampaignRepository(db_session)
        initial = _make_campaign(
            "beginner/unchanged_test",
            "Initial Title",
            content_hash="fixed_hash_1234",
        )
        repo.add(initial)
        campaign_id = initial.id
        initial_created_at = initial.created_at
        stage_ids = [s.id for s in initial.stages]

        candidate = _make_campaign(
            "beginner/unchanged_test",
            "Different Title Should Not Be Applied",
            content_hash="fixed_hash_1234",
        )
        candidate.stages[0].input_style = "keys"
        result = repo.upsert(candidate)

        assert result.id == campaign_id
        assert result.title == "Initial Title"
        assert result.created_at == initial_created_at
        assert [s.id for s in result.stages] == stage_ids
        assert result.stages[0].input_style == "lines"

    def test_upsert_preserves_quarantined_status(
        self, db_session: Session
    ) -> None:
        """Verify upsert never overwrites existing status on update."""
        repo = CampaignRepository(db_session)
        initial = _make_campaign("beginner/status_test", "Status Test")
        initial.status = "quarantined"
        repo.add(initial)

        updated = _make_campaign(
            "beginner/status_test",
            "Status Test Modified",
            content_hash="different_hash_5678",
        )
        updated.status = "validated"
        result = repo.upsert(updated)

        assert result.status == "quarantined"
        loaded = repo.get_by_slug("beginner/status_test")
        assert loaded is not None
        assert loaded.status == "quarantined"

    def test_upsert_removing_stage_deletes_only_that_one(
        self, db_session: Session
    ) -> None:
        """Verify removing a stage deletes only that stage."""
        repo = CampaignRepository(db_session)
        initial = _make_campaign("beginner/stage_del", "Stage Delete Initial")
        repo.add(initial)
        assert len(initial.stages) == 2
        stage1_id = initial.stages[0].id
        stage2_id = initial.stages[1].id

        updated = _make_campaign(
            "beginner/stage_del",
            "Stage Delete Updated",
            content_hash="del_stage_hash_999",
        )
        updated.stages = [updated.stages[0]]

        result = repo.upsert(updated)
        assert len(result.stages) == 1
        assert result.stages[0].id == stage1_id

        loaded = repo.get_by_slug("beginner/stage_del")
        assert loaded is not None
        assert len(loaded.stages) == 1
        assert loaded.stages[0].id == stage1_id

        deleted_stage = db_session.get(Stage, stage2_id)
        assert deleted_stage is None

    def test_upsert_adding_new_stage_to_existing(
        self, db_session: Session
    ) -> None:
        """Verify adding a new stage number appends it and keeps existing."""
        repo = CampaignRepository(db_session)
        initial = _make_campaign("beginner/stage_add", "Stage Add Initial")
        repo.add(initial)
        stage1_id = initial.stages[0].id
        stage2_id = initial.stages[1].id

        updated = _make_campaign(
            "beginner/stage_add",
            "Stage Add Updated",
            content_hash="add_stage_hash_111",
        )
        stage3 = Stage(
            number=3,
            prompt="Stage 3 prompt.",
            input_style="keys",
            reference_program="print(3)",
            check_script="def check(game):\n    game.send('3')\n",
        )
        updated.stages.append(stage3)

        result = repo.upsert(updated)
        assert len(result.stages) == 3
        assert result.stages[0].id == stage1_id
        assert result.stages[1].id == stage2_id
        assert result.stages[2].number == 3
        assert result.stages[2].id is not None
        assert result.stages[2].check_script.endswith("send('3')\n")

        db_session.expire_all()

        loaded = repo.get_by_slug("beginner/stage_add")
        assert loaded is not None
        assert loaded.stages[0].input_style == "lines"
        assert loaded.stages[1].input_style == "lines"
        assert loaded.stages[2].input_style == "keys"

    def test_validated_for_filters_by_difficulty_and_status(
        self, db_session: Session
    ) -> None:
        """Verify validated_for returns only validated tier campaigns."""
        repo = CampaignRepository(db_session)

        c1 = _make_campaign("beginner/c1", "Beginner Validated", "beginner")
        c2 = _make_campaign("beginner/c2", "Beginner Quarantined", "beginner")
        c2.status = "quarantined"
        c3 = _make_campaign("easy/c3", "Easy Validated", "easy")

        repo.add(c1)
        repo.add(c2)
        repo.add(c3)

        beginner_list = repo.validated_for(Difficulty.BEGINNER)
        assert len(beginner_list) == 1
        assert beginner_list[0].slug == "beginner/c1"

        easy_list = repo.validated_for("easy")
        assert len(easy_list) == 1
        assert easy_list[0].slug == "easy/c3"

        medium_list = repo.validated_for(Difficulty.MEDIUM)
        assert len(medium_list) == 0

    def test_cascade_delete(self, db_session: Session) -> None:
        """Verify deleting a campaign cascades to its stages."""
        repo = CampaignRepository(db_session)
        campaign = _make_campaign(
            "beginner/cascade_del", "Cascade Delete Test"
        )
        repo.add(campaign)

        stage_count_before = db_session.scalar(select(func.count(Stage.id)))
        assert stage_count_before >= 2

        db_session.delete(campaign)
        db_session.flush()

        assert repo.get_by_slug("beginner/cascade_del") is None