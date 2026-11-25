"""
File: test_run_sample.py
Description: Selenium coverage for Run Sample (US5), including sample
    execution, output comparison, tracebacks, timeout recovery, browser-only
    execution, normalization, Python loading, and interpreter isolation.
Author(s): Steph Rivera
"""

from threading import Event
from time import monotonic

import pytest
from flask import Flask, request
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions
from selenium.webdriver.support.ui import WebDriverWait
from sqlalchemy.orm import Session

from src.business.auth_service import AuthService
from src.data.models.campaign import Campaign, Stage, TestCase
from src.data.repositories.user_repository import UserRepository

CORRECT_CODE = (
    "n = int(input())\n"
    "prices = list(map(int, input().split()))\n"
    "print(sum(prices))"
)

TIMEOUT_MESSAGE = (
    "Your code ran for more than 5 seconds and was stopped. "
    "Check for an infinite loop."
)

PYTHON_READY_SECONDS = 60
RESULT_SECONDS = 15


def _selector(test_id: str) -> tuple[str, str]:
    return By.CSS_SELECTOR, f'[data-testid="{test_id}"]'


def _start_run(
    browser: webdriver.Chrome,
    live_server: str,
    db_session: Session,
) -> WebDriverWait:
    AuthService(UserRepository(db_session)).register(
        "SampleRunner", "password123", "password123"
    )
    browser.get(f"{live_server}/login")
    ready = WebDriverWait(browser, 15)
    ready.until(
        expected_conditions.visibility_of_element_located(
            _selector("login-username")
        )
    ).send_keys("SampleRunner")
    browser.find_element(*_selector("login-password")).send_keys("password123")
    browser.find_element(*_selector("login-submit")).click()
    ready.until(
        expected_conditions.element_to_be_clickable(
            _selector("home-start-link")
        )
    ).click()
    ready.until(
        expected_conditions.element_to_be_clickable(
            _selector("start-tier-beginner-button")
        )
    ).click()
    ready.until(expected_conditions.url_matches(r"/play/\d+$"))
    return ready


def _write_code(
    browser: webdriver.Chrome, ready: WebDriverWait, code: str
) -> None:
    """Put the player's Python code in the Monaco editor."""
    ready.until(
        lambda driver: driver.execute_script(
            "return !!window.monaco && monaco.editor.getEditors().length > 0"
        )
    )
    browser.execute_script(
        "monaco.editor.getEditors()[0].setValue(arguments[0])", code
    )


def _wait_for_python(browser: webdriver.Chrome) -> WebElement:
    """Wait until Python is ready to execute samples."""
    return WebDriverWait(browser, PYTHON_READY_SECONDS).until(
        expected_conditions.element_to_be_clickable(
            _selector("game-run-sample")
        )
    )


def _run_sample_and_wait(browser: webdriver.Chrome) -> None:
    """Run samples and wait for newly rendered results."""
    previous = browser.find_elements(*_selector("game-sample-1-result"))

    _wait_for_python(browser).click()

    results = WebDriverWait(browser, RESULT_SECONDS)

    if previous:
        results.until(expected_conditions.staleness_of(previous[0]))

    results.until(
        expected_conditions.visibility_of_element_located(
            _selector("game-sample-1-result")
        )
    )
    results.until(
        expected_conditions.visibility_of_element_located(
            _selector("game-sample-summary")
        )
    )


def _lives(browser: webdriver.Chrome) -> str:
    """Return the current lives displayed in the game HUD."""
    label = browser.find_element(*_selector("game-lives")).get_dom_attribute(
        "aria-label"
    )
    assert label is not None
    return label


def _text(browser: webdriver.Chrome, test_id: str) -> str:
    """Return the visible text of a game element."""
    return browser.find_element(*_selector(test_id)).text


def _wait_for_timeout(browser: webdriver.Chrome) -> None:
    """Verify that execution stops within the expected timeout window."""
    button = _wait_for_python(browser)
    started = monotonic()
    button.click()

    message = WebDriverWait(browser, 8, poll_frequency=0.1).until(
        expected_conditions.visibility_of_element_located(
            _selector("game-run-timeout")
        )
    )

    elapsed = monotonic() - started

    assert message.text == TIMEOUT_MESSAGE
    assert 4.5 <= elapsed <= 7.5, (
        f"Unexpected timeout duration: {elapsed:.2f} seconds"
    )


def _first_stage(db_session: Session, campaign_id: int) -> Stage:
    """Retrieve the first stage of the seeded campaign."""
    campaign = db_session.get(Campaign, campaign_id)
    assert campaign is not None
    return campaign.stages[0]


@pytest.fixture
def two_samples(db_session: Session, seeded_beginner: int) -> None:
    """Add a second visible sample to the test campaign."""
    stage = _first_stage(db_session, seeded_beginner)
    position = max(case.position for case in stage.test_cases) + 1

    stage.test_cases.append(
        TestCase(
            kind="sample",
            position=position,
            input="2\n100 200",
            expected_output="300",
        )
    )
    db_session.commit()


@pytest.mark.e2e
@pytest.mark.blackbox
def test_correct_program_passes(
    browser: webdriver.Chrome,
    live_server: str,
    db_session: Session,
    seeded_beginner: int,
) -> None:
    """US5 AC1: Correct Python code passes without deducting lives."""
    ready = _start_run(browser, live_server, db_session)
    lives_before = _lives(browser)

    _write_code(browser, ready, CORRECT_CODE)
    _run_sample_and_wait(browser)

    assert _text(browser, "game-sample-1-status") == "PASS"
    assert _text(browser, "game-sample-1-expected") == "425"
    assert _text(browser, "game-sample-1-actual") == "425"
    assert _text(browser, "game-sample-summary") == ("1 of 1 samples passed")
    assert _lives(browser) == lives_before


@pytest.mark.e2e
def test_incorrect_program_fails(
    browser: webdriver.Chrome,
    live_server: str,
    db_session: Session,
    seeded_beginner: int,
) -> None:
    """US5 AC1: Incorrect output fails and displays the comparison."""
    ready = _start_run(browser, live_server, db_session)
    lives_before = _lives(browser)

    _write_code(browser, ready, "print(400)")
    _run_sample_and_wait(browser)

    assert _text(browser, "game-sample-1-status") == "FAIL"
    assert _text(browser, "game-sample-1-expected") == "425"
    assert _text(browser, "game-sample-1-actual") == "400"
    assert _text(browser, "game-sample-summary") == ("0 of 1 samples passed")
    assert _lives(browser) == lives_before


@pytest.mark.e2e
def test_python_exception_displays_traceback(
    browser: webdriver.Chrome,
    live_server: str,
    db_session: Session,
    seeded_beginner: int,
) -> None:
    """US5 AC1: Python exceptions display a player-facing traceback."""
    ready = _start_run(browser, live_server, db_session)
    lives_before = _lives(browser)

    _write_code(browser, ready, 'raise ValueError("Test error")')
    _run_sample_and_wait(browser)

    error = _text(browser, "game-sample-1-error")

    assert _text(browser, "game-sample-1-status") == "FAIL"
    assert "Traceback (most recent call last):" in error
    assert 'File "main.py"' in error
    assert "ValueError: Test error" in error
    assert 'File "<exec>"' not in error
    assert 'File "<string>"' not in error
    assert _text(browser, "game-sample-summary") == ("0 of 1 samples passed")
    assert _lives(browser) == lives_before


@pytest.mark.e2e
def test_infinite_loop_times_out_and_recovers(
    browser: webdriver.Chrome,
    live_server: str,
    db_session: Session,
    seeded_beginner: int,
) -> None:
    """US5 AC2: An infinite loop stops and Python can run again."""
    ready = _start_run(browser, live_server, db_session)
    lives_before = _lives(browser)
    original_url = browser.current_url

    _write_code(browser, ready, "while True:\n    pass")
    _wait_for_timeout(browser)

    assert _lives(browser) == lives_before

    button = _wait_for_python(browser)
    assert button.get_property("textContent") == "Run Sample"

    _write_code(browser, ready, CORRECT_CODE)
    _run_sample_and_wait(browser)

    assert _text(browser, "game-sample-1-status") == "PASS"
    assert _text(browser, "game-sample-summary") == ("1 of 1 samples passed")
    assert not browser.find_elements(*_selector("game-run-timeout"))
    assert browser.current_url == original_url
    assert _lives(browser) == lives_before


@pytest.mark.e2e
def test_timeout_applies_to_all_samples(
    browser: webdriver.Chrome,
    live_server: str,
    db_session: Session,
    two_samples: None,
) -> None:
    """US5 AC2: The five-second timeout covers the entire sample run."""
    ready = _start_run(browser, live_server, db_session)
    lives_before = _lives(browser)

    slow_code = (
        "import time\n"
        "started = time.monotonic()\n"
        "while time.monotonic() - started < 3:\n"
        "    pass\n"
    ) + CORRECT_CODE

    _write_code(browser, ready, slow_code)
    _wait_for_timeout(browser)

    assert _lives(browser) == lives_before


@pytest.mark.e2e
def test_run_sample_sends_no_server_requests(
    browser: webdriver.Chrome,
    live_server: str,
    db_session: Session,
    seeded_beginner: int,
    app: Flask,
) -> None:
    """US5 AC3: Sample execution sends no requests to our server."""
    requests_received: list[str] = []

    @app.before_request
    def record_request() -> None:
        requests_received.append(request.path)

    ready = _start_run(browser, live_server, db_session)
    _write_code(browser, ready, CORRECT_CODE)
    _wait_for_python(browser)

    # Confirm that the request recorder is working.
    assert "/login" in requests_received
    assert any(
        path.endswith("/pyodide_worker.js") for path in requests_received
    )

    # Exclude requests made during initial page loading.
    requests_received.clear()

    _run_sample_and_wait(browser)

    # Also observe requests during worker recreation.
    _wait_for_python(browser)

    assert _text(browser, "game-sample-1-status") == "PASS"
    assert not requests_received, (
        f"Unexpected server requests: {requests_received}"
    )


@pytest.mark.e2e
@pytest.mark.parametrize(
    ("code", "expected_output", "status"),
    [
        (
            'print("425   \\r\\n\\r\\n")',
            "425",
            "PASS",
        ),
        (
            'print(" 425")',
            "425",
            "FAIL",
        ),
        (
            'print("425\\n100")',
            "425\n\n100",
            "FAIL",
        ),
    ],
    ids=[
        "trailing-whitespace",
        "leading-whitespace",
        "internal-blank-lines",
    ],
)
def test_sample_output_normalization(
    browser: webdriver.Chrome,
    live_server: str,
    db_session: Session,
    seeded_beginner: int,
    code: str,
    expected_output: str,
    status: str,
) -> None:
    """US5 AC4: Normalize trailing but preserve meaningful whitespace."""
    stage = _first_stage(db_session, seeded_beginner)
    sample = next(case for case in stage.test_cases if case.kind == "sample")
    sample.expected_output = expected_output
    db_session.commit()

    ready = _start_run(browser, live_server, db_session)

    _write_code(browser, ready, code)
    _run_sample_and_wait(browser)

    assert _text(browser, "game-sample-1-status") == status


@pytest.mark.e2e
def test_run_sample_disabled_while_python_loads(
    browser: webdriver.Chrome,
    live_server: str,
    db_session: Session,
    seeded_beginner: int,
    app: Flask,
) -> None:
    """US5 AC5: Run Sample stays disabled until Python is ready."""
    worker_requested = Event()
    release_worker = Event()

    @app.before_request
    def delay_worker_source() -> None:
        if request.path.endswith("/pyodide_worker.js"):
            worker_requested.set()
            release_worker.wait(timeout=PYTHON_READY_SECONDS)

    try:
        _start_run(browser, live_server, db_session)

        assert worker_requested.wait(timeout=15)

        button = browser.find_element(*_selector("game-run-sample"))

        assert not button.is_enabled()
        assert button.get_property("textContent") == "Loading Python…"
    finally:
        release_worker.set()

    button = _wait_for_python(browser)

    assert button.is_enabled()
    assert button.get_property("textContent") == "Run Sample"


@pytest.mark.e2e
def test_long_output_is_truncated(
    browser: webdriver.Chrome,
    live_server: str,
    db_session: Session,
    seeded_beginner: int,
) -> None:
    """US5 AC6: Actual output is limited to 10,000 characters."""
    ready = _start_run(browser, live_server, db_session)

    _write_code(browser, ready, 'print("A" * 11000)')
    _run_sample_and_wait(browser)

    actual = browser.find_element(
        *_selector("game-sample-1-actual")
    ).get_property("textContent")

    assert _text(browser, "game-sample-1-status") == "FAIL"
    assert actual == "A" * 10000 + "\n… output truncated."


@pytest.mark.e2e
def test_samples_use_fresh_interpreters(
    browser: webdriver.Chrome,
    live_server: str,
    db_session: Session,
    two_samples: None,
) -> None:
    """US5: Interpreter state is isolated across samples and runs."""
    ready = _start_run(browser, live_server, db_session)
    lives_before = _lives(browser)

    code = (
        "import sys\n"
        "sys.sample_counter = getattr(sys, 'sample_counter', 0) + 1\n"
        "n = int(input())\n"
        "prices = list(map(int, input().split()))\n"
        "print(sum(prices) + sys.sample_counter - 1)"
    )

    _write_code(browser, ready, code)

    for _ in range(2):
        _run_sample_and_wait(browser)

        assert _text(browser, "game-sample-1-status") == "PASS"
        assert _text(browser, "game-sample-2-status") == "PASS"
        assert _text(browser, "game-sample-1-actual") == "425"
        assert _text(browser, "game-sample-2-actual") == "300"
        assert _text(browser, "game-sample-summary") == (
            "2 of 2 samples passed"
        )
        assert _lives(browser) == lives_before
