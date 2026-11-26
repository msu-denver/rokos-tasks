"""
File: test_run_repository.py
Description: Tests run locking, replacement, and progress persistence.
Author(s): Tyler Black
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.business.campaign_selector import CampaignSelector
from src.business.difficulty import Difficulty
from src.business.game_service import GameService
from src.data.models import Checkpoint, Submission
from src.data.models.campaign import Campaign
from src.data.models.game_run import GameRun
from src.data.models.user import User
from src.data.repositories.campaign_repository import CampaignRepository
from src.data.repositories.run_repository import RunRepository


def test_concurrent_starts_leave_one_active_run(engine: Engine) -> None:
    """Confirmed starts serialize and leave exactly one active run."""
    test_id = uuid4().hex
    with Session(engine, expire_on_commit=False) as session:
        player = User(username=f"Race{test_id[:12]}", password_hash="unused")
        campaign = Campaign(
            title="Concurrent test pool",
            slug=f"impossible/race-{test_id}",
            difficulty="impossible",
            status="validated",
            content_hash="a" * 64,
        )
        session.add_all([player, campaign])
        session.commit()
        player_id, campaign_id = player.id, campaign.id

    ready = Barrier(2, timeout=5)

    def start() -> int:
        with Session(engine) as session:
            runs = RunRepository(session)
            selector = CampaignSelector(CampaignRepository(session), runs)
            service = GameService(selector, runs, lambda: datetime.now(UTC))
            ready.wait()
            return service.start_run(
                player_id, Difficulty.IMPOSSIBLE, replace_active=True
            ).id

    try:
        with ThreadPoolExecutor(max_workers=2) as workers:
            first, second = workers.submit(start), workers.submit(start)
            run_ids = {first.result(timeout=10), second.result(timeout=10)}

        with Session(engine) as session:
            runs = session.scalars(
                select(GameRun).where(GameRun.user_id == player_id)
            ).all()
            assert {run.id for run in runs} == run_ids
            assert sorted(run.status for run in runs) == [
                "abandoned",
                "in_progress",
            ]
    finally:
        with Session(engine) as session:
            session.delete(session.get_one(User, player_id))
            session.flush()
            session.delete(session.get_one(Campaign, campaign_id))
            session.commit()


@pytest.fixture
def run_with_stages(db_session: Session, seeded_beginner: int) -> GameRun:
    """Create a Beginner-tier run and flush it for repository tests."""
    player = User(username="ProgressPlayer", password_hash="unused")
    db_session.add(player)
    db_session.flush()
    now = datetime.now(UTC)
    return RunRepository(db_session).add(
        GameRun(
            user_id=player.id,
            campaign_id=seeded_beginner,
            difficulty="beginner",
            status="in_progress",
            lives=4,
            current_stage=1,
            score=0,
            started_at=now,
            stage_started_at=now,
        )
    )


def test_checkpoint_and_submission_round_trip(
    db_session: Session, run_with_stages: GameRun
) -> None:
    """Read the checkpoint below the run's stage and passes in order."""
    runs = RunRepository(db_session)
    run = run_with_stages
    run_id = run.id
    now = run.started_at
    assert runs.latest_checkpoint(run) is None
    assert runs.passed_submissions(run) == []
    assert runs.stage_count(run) == 2
    second = runs.save_checkpoint(
        Checkpoint(run_id=run.id, stage_number=2, code="two", saved_at=now)
    )
    first = runs.save_checkpoint(
        Checkpoint(run_id=run.id, stage_number=1, code="one", saved_at=now)
    )
    passes = [
        runs.add_submission(
            Submission(
                run_id=run.id,
                stage_number=stage,
                code=code,
                passed=True,
                seconds_remaining=7,
                submitted_at=now,
            )
        )
        for stage, code in [(2, "two"), (1, "one")]
    ]
    runs.add_submission(
        Submission(
            run_id=run.id,
            stage_number=1,
            code="failed",
            passed=False,
            failure_kind="rule",
            failed_rule="Print one",
            failed_turn=4,
            seconds_remaining=12,
            submitted_at=now,
        )
    )
    runs.commit()
    checkpoint_ids = (first.id, second.id)
    pass_ids = [sub.id for sub in reversed(passes)]
    db_session.expunge_all()

    run = db_session.get_one(GameRun, run_id)
    # A checkpoint for the run's own stage isn't one it has reached yet.
    run.current_stage = 2
    latest = runs.latest_checkpoint(run)
    assert (latest.id, latest.stage_number, latest.code, latest.saved_at) == (
        checkpoint_ids[0],
        1,
        "one",
        now,
    )
    run.current_stage = 3
    assert runs.latest_checkpoint(run).id == checkpoint_ids[1]
    history = runs.passed_submissions(run)
    assert [sub.id for sub in history] == pass_ids
    assert [(sub.stage_number, sub.code) for sub in history] == [
        (1, "one"),
        (2, "two"),
    ]
    assert all(sub.submitted_at == now for sub in history)


def test_lock_for_user_checks_ownership(
    db_session: Session, run_with_stages: GameRun
) -> None:
    """Return the run only when locked by its owning player."""
    stranger = User(username="ProgressStranger", password_hash="unused")
    db_session.add(stranger)
    db_session.flush()
    runs = RunRepository(db_session)
    run = run_with_stages
    assert runs.lock_for_user(run.id, stranger.id) is None
    assert runs.lock_for_user(run.id, run.user_id) is run


def test_unknown_failure_kind_rejected(
    db_session: Session, run_with_stages: GameRun
) -> None:
    """Reject a submission outside the database's failure-kind constraint."""
    runs = RunRepository(db_session)
    with pytest.raises(IntegrityError, match="ck_submissions_failure_kind"):
        with db_session.begin_nested():
            runs.add_submission(
                Submission(
                    run_id=run_with_stages.id,
                    stage_number=1,
                    code="failed",
                    passed=False,
                    failure_kind="unknown",
                    seconds_remaining=7,
                    submitted_at=run_with_stages.started_at,
                )
            )
