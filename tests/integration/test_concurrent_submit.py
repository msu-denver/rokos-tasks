"""
File: test_concurrent_submit.py
Description: Verifies duplicate submissions serialize across DB sessions.
Author(s): Tyler Black
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Barrier
from unittest.mock import Mock
from uuid import uuid4

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from src.business.campaign_selector import CampaignSelector
from src.business.game_service import GameService, StaleSubmitError
from src.business.grading_service import GradingService, Verdict
from src.data.models import Campaign, GameRun, Stage, Submission, User
from src.data.repositories.run_repository import RunRepository


def _committed_run(engine: Engine) -> tuple[int, int, int]:
    test_id = uuid4().hex
    now = datetime.now(UTC)
    with Session(engine, expire_on_commit=False) as session:
        player = User(username=f"Submit{test_id[:12]}", password_hash="unused")
        campaign = Campaign(
            title="Concurrent submission campaign",
            slug=f"beginner/submit-{test_id}",
            difficulty="beginner",
            content_hash="a" * 64,
            stages=[
                Stage(
                    number=1,
                    prompt="Print one.",
                    reference_program="print(1)",
                    check_script="def check(game): pass",
                )
            ],
        )
        session.add_all([player, campaign])
        session.flush()
        run = GameRun(
            user_id=player.id,
            campaign_id=campaign.id,
            difficulty="beginner",
            status="in_progress",
            lives=4,
            current_stage=1,
            score=0,
            started_at=now,
            stage_started_at=now,
        )
        session.add(run)
        session.commit()
        return player.id, campaign.id, run.id


def _submit_failure(
    engine: Engine, player_id: int, run_id: int, both_grading: Barrier
) -> str:
    def grade(user_id: int, run_id: int, code: str) -> Verdict:
        both_grading.wait()
        return Verdict(False, "FAIL", "rule", "Print one.", 1, (), None, "")

    grading = Mock(spec=GradingService)
    grading.grade.side_effect = grade
    with Session(engine) as session:
        game = GameService(
            Mock(spec=CampaignSelector),
            RunRepository(session),
            lambda: datetime.now(UTC),
            grading=grading,
        )
        try:
            game.submit_stage(player_id, run_id, "print(2)", 1)
        except StaleSubmitError:
            return "stale"
        return "applied"


def test_concurrent_failures_count_once(engine: Engine) -> None:
    """Two verdicts from one snapshot cost one life and save one attempt."""
    player_id, campaign_id, run_id = _committed_run(engine)
    both_grading = Barrier(2, timeout=5)
    try:
        with ThreadPoolExecutor(max_workers=2) as workers:
            futures = [
                workers.submit(
                    _submit_failure, engine, player_id, run_id, both_grading
                )
                for _ in range(2)
            ]
            outcomes = [future.result(timeout=10) for future in futures]

        assert sorted(outcomes) == ["applied", "stale"]
        with Session(engine) as session:
            run = session.get_one(GameRun, run_id)
            assert (run.lives, run.current_stage) == (3, 1)
            attempt = session.scalars(
                select(Submission).where(Submission.run_id == run_id)
            ).one()
            assert attempt.passed is False
    finally:
        with Session(engine) as session:
            session.delete(session.get_one(User, player_id))
            session.flush()
            session.delete(session.get_one(Campaign, campaign_id))
            session.commit()
