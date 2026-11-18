"""
File: conftest.py
Description: Shared pytest fixtures: the Flask app and test client, a
    live server for Selenium, a headless Chrome browser that saves a
    screenshot to .pr/e2e-failures/ when an e2e test fails, and
    Postgres-backed engine and rolled-back session fixtures.
Author(s): Tyler Black
"""

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
from src.business.campaigns.seed_loader import SeedLoader
from src.data.database import db
from src.data.repositories.campaign_repository import CampaignRepository

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


@pytest.fixture
def app(db_session: Session) -> Flask:
    """Return a Flask app configured for testing with the test database."""
    return create_app(
        {
            "TESTING": True,
            "DATABASE_URL": TEST_DATABASE_URL,
        }
    )


@pytest.fixture
def client(app: Flask) -> FlaskClient:
    """Return a Flask test client for the app."""
    return app.test_client()


@pytest.fixture
def seeded_beginner(db_session: Session) -> int:
    """Make the shipped Beginner campaign available to route and UI tests."""
    seed_file = (
        Path(__file__).resolve().parents[1]
        / "content/campaigns/seed/beginner/cafe_tab_splitter.json"
    )
    repository = CampaignRepository(db_session)
    campaign = SeedLoader(repository).load_file(seed_file)
    campaign_id = campaign.id
    repository.commit()
    return campaign_id


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
