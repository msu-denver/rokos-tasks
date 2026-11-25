"""
File: conftest.py
Description: Shared pytest fixtures: the Flask app and test client, a
    live server for Selenium, a headless Chrome browser that saves a
    screenshot to .pr/e2e-failures/ when an e2e test fails, Postgres-backed
    engine and rolled-back session fixtures, seeded campaigns, and a local
    runner (the real runner HTTP server in host mode) for grading.
Author(s): Tyler Black, Richard Hall
"""

import json
import os
import threading
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from flask import Flask
from flask.testing import FlaskClient
from selenium import webdriver
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session
from werkzeug.serving import make_server

from src.app import create_app
from src.business.campaigns.check_runner import (
    TrustedSeedPlayer,
    host_play_supported,
)
from src.business.campaigns.seed_loader import SeedLoader
from src.data.database import db
from src.data.repositories.campaign_repository import CampaignRepository
from src.runner.limits import SandboxLimits
from src.runner.server import RunnerHTTPServer
from src.runner.service import RunnerService
from src.runner.slots import Slot, SlotPool

FAILURE_SCREENSHOT_DIR = Path(".pr/e2e-failures")
TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://rokos:rokos@localhost:5433/rokos_test",
)


@pytest.hookimpl(wrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo):
    """Attach each phase's report to the test so fixtures can see it."""
    report = yield
    setattr(item, f"report_{report.when}", report)
    return report


@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:
    """Create a database engine and run all migrations once for the session.

    Yields:
        A SQLAlchemy Engine connected to TEST_DATABASE_URL.
    """
    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)
    command.upgrade(alembic_cfg, "head")

    test_engine = create_engine(TEST_DATABASE_URL)
    yield test_engine
    test_engine.dispose()


@pytest.fixture
def db_session(engine: Engine) -> Iterator[Session]:
    """Yield a database session inside a rolled-back transaction.

    Args:
        engine: The session-scoped database engine.

    Yields:
        A Session bound to the test transaction.
    """
    connection = engine.connect()
    transaction = connection.begin()

    db.init(TEST_DATABASE_URL)
    db.session_factory.configure(
        bind=connection,
        join_transaction_mode="create_savepoint",
    )
    session = db.session

    yield session

    db.remove()
    transaction.rollback()
    connection.close()
    db.session_factory.configure(bind=engine)


@pytest.fixture(scope="session")
def local_runner(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    """Serve the real runner HTTP API on a free local port, in host mode.

    The web app reaches the real runner only inside Docker Compose, so
    route and e2e tests grade through this one instead. Everything but
    the container isolation is the same code (T12's hostile suite covers
    the isolation). Only trusted test programs run here.

    Yields:
        The runner's base URL, for ``RUNNER_URL``.
    """
    slots = [
        Slot(None, tmp_path_factory.mktemp(f"slot{index}"))
        for index in range(4)
    ]
    # macOS rejects the address-space limit, so host mode leaves it unset.
    service = RunnerService(SlotPool(slots), SandboxLimits(memory_bytes=None))
    # Host mode has no player programs to keep out, and no /proc/net.
    server = RunnerHTTPServer(("127.0.0.1", 0), service, check_peers=False)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()
    thread.join()


@pytest.fixture
def app(db_session: Session, local_runner: str) -> Flask:
    """Return a Flask app configured for testing with the test database."""
    return create_app(
        {
            "TESTING": True,
            "DATABASE_URL": TEST_DATABASE_URL,
            "RUNNER_URL": local_runner,
        }
    )


@pytest.fixture
def client(app: Flask) -> FlaskClient:
    """Return a Flask test client for the app."""
    return app.test_client()


class MemoSeedPlayer(TrustedSeedPlayer):
    """A trusted seed player that plays each program only once per session.

    Loading a seed validates it, which plays every program on its check
    script. Route and UI tests load the same seeds many times, so they
    share one of these. The seed validation tests use the real player.
    """

    def __init__(self) -> None:
        """Start with nothing played."""
        self._grades: dict[tuple[str, str], dict] = {}
        self._screens: dict[tuple[str, tuple[str, ...]], list[str]] = {}

    def grade(self, code: str, check_script: str) -> dict:
        """Return the verdict, playing it the first time only."""
        key = (code, check_script)
        if key not in self._grades:
            self._grades[key] = super().grade(code, check_script)
        return self._grades[key]

    def screens(self, code: str, inputs: list[str]) -> list[str]:
        """Return the screens, playing them the first time only."""
        key = (code, tuple(inputs))
        if key not in self._screens:
            self._screens[key] = super().screens(code, inputs)
        return self._screens[key]


# Skips a test on Windows, which can't play programs on the host (no
# pass_fds, no waiting on pipes). Linux CI runs every one of these.
requires_host_play = pytest.mark.skipif(
    not host_play_supported(),
    reason="plays programs on this machine, which needs Linux or macOS; "
    "CI runs it",
)


@pytest.fixture(scope="session")
def seed_player() -> MemoSeedPlayer | None:
    """Return the session's shared seed player.

    None on Windows: seeds are then structure-checked only (see
    ``SeedLoader``), so route and UI tests still get campaigns.
    """
    return MemoSeedPlayer() if host_play_supported() else None


def _load_seed(
    db_session: Session, player: MemoSeedPlayer | None, relative: str
) -> int:
    """Load one shipped seed file and return its campaign id."""
    seed_file = (
        Path(__file__).resolve().parents[1] / "content/campaigns/seed"
    ) / relative
    data = json.loads(seed_file.read_text(encoding="utf-8"))
    repository = CampaignRepository(db_session)
    campaign = SeedLoader(repository).load_campaign_data(
        data, slug=relative.removesuffix(".json"), player=player
    )
    campaign_id = campaign.id
    repository.commit()
    return campaign_id


@pytest.fixture
def seeded_beginner(
    db_session: Session, seed_player: MemoSeedPlayer | None
) -> int:
    """Make the shipped Beginner campaign available to route and UI tests."""
    return _load_seed(db_session, seed_player, "beginner/traffic_light.json")


@pytest.fixture
def seeded_pong(
    db_session: Session, seed_player: MemoSeedPlayer | None
) -> int:
    """Make the shipped Pong campaign available."""
    return _load_seed(db_session, seed_player, "medium/pong.json")


@pytest.fixture
def live_server(app: Flask) -> Iterator[str]:
    """Serve the app on a free local port in a background thread.

    Yields:
        The server's base URL, for example ``http://127.0.0.1:54321``.
    """
    app.config["WTF_CSRF_ENABLED"] = True
    server = make_server("127.0.0.1", 0, app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()
    thread.join()


@pytest.fixture
def browser(request: pytest.FixtureRequest) -> Iterator[webdriver.Chrome]:
    """Start headless Chrome, and screenshot the page if the test fails.

    Yields:
        A Selenium Chrome driver.
    """
    options = webdriver.ChromeOptions()
    for argument in (
        "--headless=new",
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--window-size=1280,800",
    ):
        options.add_argument(argument)
    driver = webdriver.Chrome(options=options)
    yield driver
    call_report = getattr(request.node, "report_call", None)
    if call_report is not None and call_report.failed:
        FAILURE_SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
        driver.save_screenshot(
            str(FAILURE_SCREENSHOT_DIR / f"{request.node.name}.png")
        )
    driver.quit()
