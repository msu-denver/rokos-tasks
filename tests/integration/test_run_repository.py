"""
File: test_run_repository.py
Description: Verifies run replacement across concurrent PostgreSQL sessions.
Author(s): Tyler Black
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Barrier
from uuid import uuid4

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from src.business.campaign_selector import CampaignSelector
from src.business.difficulty import Difficulty
from src.business.game_service import GameService
from src.data.models.campaign import Campaign
from src.data.models.game_run import GameRun
from src.data.models.user import User
from src.data.repositories.campaign_repository import CampaignRepository
from src.data.repositories.run_repository import RunRepository


def test_concurrent_starts_leave_one_active_run(engine: Engine) -> None:
    """Both requests succeed and the later one abandons the earlier run."""
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
            return service.start_run(player_id, Difficulty.IMPOSSIBLE).id

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
