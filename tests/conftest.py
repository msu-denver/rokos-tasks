"""
File: conftest.py
Description: Shared pytest fixtures: the Flask app and test client, a
    live server for Selenium, and a headless Chrome browser that saves a
    screenshot to .pr/e2e-failures/ when an e2e test fails.
Author(s): Tyler Black
"""

import threading
from collections.abc import Iterator
from pathlib import Path

import pytest
from flask import Flask
from flask.testing import FlaskClient
from selenium import webdriver
from werkzeug.serving import make_server

from src.app import create_app

FAILURE_SCREENSHOT_DIR = Path(".pr/e2e-failures")


@pytest.hookimpl(wrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo):
    """Attach each phase's report to the test so fixtures can see it."""
    report = yield
    setattr(item, f"report_{report.when}", report)
    return report


@pytest.fixture
def app() -> Flask:
    """Return a Flask app configured for testing."""
    return create_app({"TESTING": True})


@pytest.fixture
def client(app: Flask) -> FlaskClient:
    """Return a Flask test client for the app."""
    return app.test_client()


@pytest.fixture
def live_server(app: Flask) -> Iterator[str]:
    """Serve the app on a free local port in a background thread.

    Yields:
        The server's base URL, for example ``http://127.0.0.1:54321``.
    """
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
