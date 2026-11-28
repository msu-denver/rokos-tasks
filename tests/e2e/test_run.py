"""
File: test_run.py
Description: Selenium coverage for Run (US5): local Python execution,
    interactive input, automatic turns, stopping, exception handling,
    timeout recovery, screen formatting, and Submit coordination.
Author(s): Steph Rivera
"""

import json
from pathlib import Path
from threading import Event
from time import monotonic

import pytest
from flask import Flask, request
from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions
from selenium.webdriver.support.ui import WebDriverWait
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.data.models.campaign import Stage
from src.data.models.game_run import GameRun
from tests.conftest import requires_host_play
from tests.e2e.support import selector, start_run, write_code

pytestmark = pytest.mark.e2e

PYTHON_SECONDS = 60
EXECUTION_SECONDS = 10
WAIT_INTERVAL = 0.05

ROOT = Path(__file__).resolve().parents[2]
TRAFFIC = json.loads(
    (ROOT / "content/campaigns/seed/beginner/traffic_light.json")
    .read_text("utf-8")
)
TRAFFIC_STAGE_1 = TRAFFIC["stages"][0]["reference_program"]
PONG = json.loads(
    (ROOT / "content/campaigns/seed/medium/pong.json")
    .read_text("utf-8")
)

KEY_PROGRAM = (
    "turn = 0\n"
    "received = ''\n"
    "while True:\n"
    "    print('Turn:', turn)\n"
    "    print('Keys:', received)\n"
    "    received += input()\n"
    "    turn += 1\n"
)


def _text(browser: webdriver.Chrome, test_id: str) -> str:
    """Return the exact text of a game element."""
    return browser.find_element(
        *selector(test_id)
    ).get_attribute("textContent")

def _turn_number(browser: webdriver.Chrome) -> int:
    """Return the current automatic turn, or -1 before output."""
    line = _text(browser, "game-run-screen").partition("\n")[0]
    _, _, number = line.partition("Turn: ")
    return int(number) if number.isdecimal() else -1


def _wait_for_python(browser: webdriver.Chrome) -> None:
    """Wait until the browser is ready to execute Python."""
    button = WebDriverWait(browser, PYTHON_SECONDS).until(
        expected_conditions.element_to_be_clickable(
            selector("game-run")
        )
    )
    assert button.get_attribute("textContent") == "Run"


def _wait_for_status(
    browser: webdriver.Chrome, status: str
) -> None:
    """Wait for the local program to reach the expected status."""
    WebDriverWait(
        browser, EXECUTION_SECONDS, poll_frequency=WAIT_INTERVAL
    ).until(
        lambda driver: _text(driver, "game-run-status") == status
    )


def _run(
    browser: webdriver.Chrome,
    ready: WebDriverWait,
    code: str,
) -> None:
    """Write a program and execute it locally."""
    write_code(browser, ready, code)
    _wait_for_python(browser)
    browser.find_element(*selector("game-run")).click()


def _current_run_id(browser: webdriver.Chrome) -> int:
    """Read the current run identifier from the play page URL."""
    return int(browser.current_url.rsplit("/", 1)[-1])


def _set_stage(
    browser: webdriver.Chrome,
    db_session: Session,
    number: int,
) -> None:
    """Prepare a later test stage without relying on US7 progression."""
    run = db_session.get(GameRun, _current_run_id(browser))
    assert run is not None
    run.current_stage = number
    db_session.commit()
    browser.refresh()


def _lives(browser: webdriver.Chrome) -> str:
    """Return the displayed life count."""
    return browser.find_element(
        *selector("game-lives")
    ).get_attribute("aria-label")


def _assert_idle(browser: webdriver.Chrome) -> None:
    """Verify that execution controls recover after a program ends."""
    _wait_for_python(browser)
    assert not browser.find_element(
        *selector("game-stop")
    ).is_enabled()
    assert browser.find_element(
        *selector("game-submit")
    ).is_enabled()


def test_run_program_without_losing_lives(
    browser: webdriver.Chrome,
    live_server: str,
    db_session: Session,
    seeded_beginner: int,
) -> None:
    """US5 AC1/AC4: Run a normal Python script without losing lives."""
    ready = start_run(browser, live_server, db_session, "beginner")
    lives = _lives(browser)

    _run(browser, ready, 'print("Hello, world!")')
    _wait_for_status(browser, "Program finished.")

    assert _text(browser, "game-run-screen") == "Hello, world!"
    assert browser.find_element(
        *selector("game-console-body")
    ).is_displayed()
    assert _lives(browser) == lives

    run = db_session.get(GameRun, _current_run_id(browser))
    assert run is not None
    db_session.refresh(run)
    assert run.current_stage == 1
    assert run.lives == 4

    _assert_idle(browser)


def test_line_input_waits_for_enter(
    browser: webdriver.Chrome,
    live_server: str,
    db_session: Session,
    seeded_beginner: int,
) -> None:
    """US5 AC2/AC6: Accept a line and suspend timeout during input."""
    ready = start_run(browser, live_server, db_session, "beginner")
    _set_stage(browser, db_session, 2)
    lives = _lives(browser)

    code = (
        'print("Enter a command:")\n'
        "command = input()\n"
        'print("You entered:", command)\n'
    )
    _run(browser, ready, code)
    _wait_for_status(browser, "Waiting for input…")

    assert _text(browser, "game-run-screen") == "Enter a command:"
    field = browser.find_element(*selector("game-run-input"))
    assert field.is_displayed()
    assert field.is_enabled()

    deadline = monotonic() + 1.2
    WebDriverWait(
        browser, EXECUTION_SECONDS, poll_frequency=WAIT_INTERVAL
    ).until(
        lambda driver: monotonic() >= deadline
    )

    assert _text(browser, "game-run-status") == "Waiting for input…"
    assert field.is_enabled()

    field.send_keys("coin 25", Keys.ENTER)
    _wait_for_status(browser, "Program finished.")

    assert _text(browser, "game-run-screen") == "You entered: coin 25"
    assert not field.is_displayed()
    assert _lives(browser) == lives
    _assert_idle(browser)


def test_keys_advance_automatically_and_stop(
    browser: webdriver.Chrome,
    live_server: str,
    db_session: Session,
    seeded_pong: int,
) -> None:
    """US5 AC3/AC4: Advance turns, receive keys, and stop execution."""
    ready = start_run(browser, live_server, db_session, "medium")
    _set_stage(browser, db_session, 2)
    lives = _lives(browser)

    _run(browser, ready, KEY_PROGRAM)

    screen = browser.find_element(*selector("game-run-screen"))
    wait = WebDriverWait(
        browser, EXECUTION_SECONDS, poll_frequency=WAIT_INTERVAL
    )
    wait.until(lambda driver: _turn_number(driver) >= 10)
    assert _text(browser, "game-run-screen").splitlines()[1] == "Keys: "

    browser.execute_script(
        "monaco.editor.getEditors()[0].focus()"
    )
    browser.switch_to.active_element.send_keys("z")
    target = _turn_number(browser) + 3
    wait.until(lambda driver: _turn_number(driver) >= target)

    assert _text(browser, "game-run-screen").splitlines()[1] == "Keys: "

    assert browser.find_element(
        *selector("game-run-hint")
    ).is_displayed()
    assert not browser.find_element(
        *selector("game-run-input-form")
    ).is_displayed()
    assert not browser.find_element(
        *selector("game-run")
    ).is_enabled()
    assert not browser.find_element(
        *selector("game-submit")
    ).is_enabled()

    screen.send_keys("q", "a")
    wait.until(
        lambda driver: "Keys: qa" in _text(
            driver, "game-run-screen"
        )
    )

    browser.find_element(*selector("game-stop")).click()
    _wait_for_status(browser, "Program stopped.")
    stopped_screen = _text(browser, "game-run-screen")

    _assert_idle(browser)
    assert _text(browser, "game-run-screen") == stopped_screen
    assert _lives(browser) == lives

    _run(browser, ready, 'print("Restarted!")')
    _wait_for_status(browser, "Program finished.")
    assert _text(browser, "game-run-screen") == "Restarted!"


def test_run_displays_clean_traceback(
    browser: webdriver.Chrome,
    live_server: str,
    db_session: Session,
    seeded_beginner: int,
) -> None:
    """US5 AC5: Display player errors without internal harness frames."""
    ready = start_run(browser, live_server, db_session, "beginner")
    lives = _lives(browser)

    code = (
        'print("Starting program...")\n'
        'raise ValueError("Test exception")'
    )
    _run(browser, ready, code)
    _wait_for_status(browser, "Program stopped with an error.")

    assert _text(browser, "game-run-screen") == "Starting program..."
    error = _text(browser, "game-error")
    assert 'File "main.py", line 2' in error
    assert "ValueError: Test exception" in error
    assert 'File "<exec>"' not in error
    assert 'File "<string>"' not in error
    assert "pyodide" not in error.lower()
    assert _lives(browser) == lives

    _assert_idle(browser)


@pytest.mark.parametrize(
    "code",
    [
        "while True:\n    pass",
        'print("First turn")\ninput()\nwhile True:\n    pass',
    ],
    ids=["before-input", "after-input"],
)
def test_run_timeout_and_recovery(
    browser: webdriver.Chrome,
    live_server: str,
    db_session: Session,
    seeded_pong: int,
    code: str,
) -> None:
    """US5 AC6: Recover after an infinite loop on any turn."""
    ready = start_run(browser, live_server, db_session, "medium")
    _set_stage(browser, db_session, 2)
    lives = _lives(browser)

    write_code(browser, ready, code)
    _wait_for_python(browser)

    started = monotonic()
    browser.find_element(*selector("game-run")).click()
    _wait_for_status(browser, "Execution timed out.")

    assert monotonic() - started < 2.5
    assert "more than 1 second" in _text(
        browser, "game-run-timeout"
    )
    assert browser.find_element(
        *selector("game-run-timeout")
    ).is_displayed()
    assert _lives(browser) == lives
    _assert_idle(browser)

    _run(browser, ready, 'print("Recovery successful!")')
    _wait_for_status(browser, "Program finished.")

    assert _text(browser, "game-run-screen") == "Recovery successful!"
    for test_id in ("game-error", "game-run-timeout"):
        assert not browser.find_element(
            *selector(test_id)
        ).is_displayed()
    assert _lives(browser) == lives


def test_run_does_not_contact_app_server(
    browser: webdriver.Chrome,
    live_server: str,
    db_session: Session,
    seeded_pong: int,
    app: Flask,
) -> None:
    """US5 AC7: Local execution makes no requests to the Flask app."""
    requests: list[str] = []

    @app.before_request
    def record_request() -> None:
        """Record application-server requests during the test."""
        requests.append(request.path)

    ready = start_run(browser, live_server, db_session, "medium")
    _set_stage(browser, db_session, 2)
    lives = _lives(browser)

    code = (
        "for turn in range(20):\n"
        "    print(turn)\n"
        "    input()\n"
        'print("Program complete!")'
    )
    write_code(browser, ready, code)
    _wait_for_python(browser)
    browser.get_log("performance")
    requests.clear()

    browser.find_element(*selector("game-run")).click()
    _wait_for_status(browser, "Program finished.")
    _assert_idle(browser)

    assert _text(browser, "game-run-screen") == "Program complete!"
    network_requests = []
    for entry in browser.get_log("performance"):
        message = json.loads(entry["message"])["message"]
        if message["method"] == "Network.requestWillBeSent":
            url = message["params"]["request"]["url"]
            if url.startswith(live_server + "/"):
                network_requests.append(url)

    assert network_requests == []
    assert requests == []
    assert _lives(browser) == lives


@requires_host_play
def test_run_and_submit_show_matching_screens(
    browser: webdriver.Chrome,
    live_server: str,
    db_session: Session,
    seeded_beginner: int,
) -> None:
    """US5 AC8: Local output matches the graded program's screen."""
    ready = start_run(browser, live_server, db_session, "beginner")

    _run(browser, ready, TRAFFIC_STAGE_1)
    _wait_for_status(browser, "Program finished.")
    run_screen = _text(browser, "game-run-screen")
    _assert_idle(browser)

    browser.find_element(*selector("game-submit")).click()
    WebDriverWait(browser, EXECUTION_SECONDS).until(
        expected_conditions.visibility_of_element_located(
            selector("game-verdict")
        )
    )

    assert _text(browser, "game-verdict-heading") == "PASS"
    assert _text(browser, "game-verdict-frame") == run_screen
    assert not browser.find_element(
        *selector("game-run-output")
    ).is_displayed()
    _assert_idle(browser)


def test_none_stage_rejects_input(
    browser: webdriver.Chrome,
    live_server: str,
    db_session: Session,
    seeded_beginner: int,
) -> None:
    """US5: A stage without input rejects a request for input."""
    ready = start_run(browser, live_server, db_session, "beginner")
    lives = _lives(browser)

    _run(browser, ready, 'print("Before input")\ninput()')
    _wait_for_status(browser, "Program stopped with an error.")

    assert _text(browser, "game-run-screen") == "Before input"
    assert _text(browser, "game-error") == (
        "This stage does not accept input."
    )
    assert _lives(browser) == lives
    _assert_idle(browser)


def test_run_preserves_screen_whitespace(
    browser: webdriver.Chrome,
    live_server: str,
    db_session: Session,
    seeded_beginner: int,
) -> None:
    """US5 AC8: Preserve spaces and remove only one final newline."""
    ready = start_run(browser, live_server, db_session, "beginner")

    _run(browser, ready, 'print("  Hello  ")\nprint()')
    _wait_for_status(browser, "Program finished.")

    assert _text(browser, "game-run-screen") == "  Hello  \n"


def test_run_truncates_large_output(
    browser: webdriver.Chrome,
    live_server: str,
    db_session: Session,
    seeded_beginner: int,
) -> None:
    """US5 AC10: Bound the displayed output of a large screen."""
    ready = start_run(browser, live_server, db_session, "beginner")
    lives = _lives(browser)

    _run(browser, ready, 'print("X" * 15000)')
    _wait_for_status(browser, "Program finished.")

    screen = _text(browser, "game-run-screen")
    assert screen == "X" * 10000 + "\n… output truncated."
    assert _lives(browser) == lives
    _assert_idle(browser)


@requires_host_play
def test_run_is_disabled_during_submit(
    browser: webdriver.Chrome,
    live_server: str,
    db_session: Session,
    seeded_beginner: int,
) -> None:
    """US5: Prevent local execution while Submit is grading."""
    ready = start_run(browser, live_server, db_session, "beginner")

    code = "import time\n\ntime.sleep(0.6)\n" + TRAFFIC_STAGE_1
    write_code(browser, ready, code)
    _wait_for_python(browser)

    run_button = browser.find_element(*selector("game-run"))
    stop_button = browser.find_element(*selector("game-stop"))
    submit_button = browser.find_element(*selector("game-submit"))

    submit_button.click()

    assert not submit_button.is_enabled()
    assert not run_button.is_enabled()
    assert not stop_button.is_enabled()

    WebDriverWait(browser, EXECUTION_SECONDS).until(
        expected_conditions.visibility_of_element_located(
            selector("game-verdict")
        )
    )

    assert _text(browser, "game-verdict-heading") == "PASS"
    _assert_idle(browser)

@requires_host_play
def test_interactive_run_and_submit_match(
    browser: webdriver.Chrome,
    live_server: str,
    db_session: Session,
    seeded_beginner: int,
) -> None:
    """US5 AC8: Run and Submit agree after identical input sequences."""
    ready = start_run(browser, live_server, db_session, "beginner")
    _set_stage(browser, db_session, 2)

    code = TRAFFIC["stages"][1]["reference_program"]
    lines = ["", "go", "stop"]

    _run(browser, ready, code)
    _wait_for_status(browser, "Waiting for input…")

    assert _text(browser, "game-run-screen") == "(R)\n( )\n( )"

    for turn in range(1, 21):
        field = browser.find_element(*selector("game-run-input"))
        field.send_keys(lines[turn % len(lines)], Keys.ENTER)
        _wait_for_status(browser, "Waiting for input…")

    run_screen = _text(browser, "game-run-screen")
    assert run_screen == "( )\n(Y)\n( )"

    browser.find_element(*selector("game-stop")).click()
    _wait_for_status(browser, "Program stopped.")
    _assert_idle(browser)

    browser.find_element(*selector("game-submit")).click()
    WebDriverWait(browser, EXECUTION_SECONDS).until(
        expected_conditions.visibility_of_element_located(
            selector("game-verdict")
        )
    )

    assert _text(browser, "game-verdict-heading") == "PASS"
    assert _text(browser, "game-verdict-frame") == run_screen
    _assert_idle(browser)


def test_python_loading_disables_run(
    browser: webdriver.Chrome,
    live_server: str,
    db_session: Session,
    seeded_beginner: int,
    app: Flask,
) -> None:
    """US5 AC9: Disable Run until Python finishes loading."""
    requested = Event()
    release = Event()

    @app.before_request
    def delay_worker() -> tuple[str, int] | None:
        """Hold the worker request until loading controls are checked."""
        if request.path == "/static/js/pyodide_worker.js":
            requested.set()
            if not release.wait(timeout=30):
                return "Worker request timed out.", 503
        return None

    try:
        ready = start_run(browser, live_server, db_session, "beginner")
        ready.until(lambda driver: requested.is_set())

        assert _text(browser, "game-run") == "Loading Python…"
        assert not browser.find_element(
            *selector("game-run")
        ).is_enabled()
        assert not browser.find_element(
            *selector("game-stop")
        ).is_enabled()
        assert browser.find_element(
            *selector("game-submit")
        ).is_enabled()
    finally:
        release.set()

    _assert_idle(browser)
    assert not browser.find_element(
        *selector("game-run-load-error")
    ).is_displayed()


@requires_host_play
def test_python_load_failure_preserves_submit(
    browser: webdriver.Chrome,
    live_server: str,
    db_session: Session,
    seeded_beginner: int,
    app: Flask,
) -> None:
    """US5: Report Python loading failure without disabling Submit."""

    @app.before_request
    def reject_worker() -> tuple[str, int] | None:
        """Simulate an unavailable browser Python worker."""
        if request.path == "/static/js/pyodide_worker.js":
            return "Python worker unavailable.", 503
        return None

    ready = start_run(browser, live_server, db_session, "beginner")

    ready.until(
        expected_conditions.visibility_of_element_located(
            selector("game-run-load-error")
        )
    )

    assert _text(browser, "game-run") == "Python unavailable"
    assert "Python could not load." in _text(
        browser, "game-run-load-error"
    )
    assert not browser.find_element(
        *selector("game-run")
    ).is_enabled()
    assert not browser.find_element(
        *selector("game-stop")
    ).is_enabled()
    assert browser.find_element(
        *selector("game-submit")
    ).is_enabled()

    write_code(browser, ready, TRAFFIC_STAGE_1)
    browser.find_element(*selector("game-submit")).click()

    ready.until(
        expected_conditions.visibility_of_element_located(
            selector("game-verdict")
        )
    )

    assert _text(browser, "game-verdict-heading") == "PASS"
    assert not browser.find_element(
        *selector("game-run")
    ).is_enabled()
    assert browser.find_element(
        *selector("game-submit")
    ).is_enabled()


def test_run_pong_board(
    browser: webdriver.Chrome,
    live_server: str,
    db_session: Session,
    seeded_pong: int,
) -> None:
    """US5 AC1: Display the complete 20 by 20 Pong board."""
    ready = start_run(browser, live_server, db_session, "medium")
    lives = _lives(browser)

    _run(browser, ready, PONG["stages"][0]["reference_program"])
    _wait_for_status(browser, "Program finished.")

    rows = _text(browser, "game-run-screen").splitlines()
    assert len(rows) == 20
    assert all(len(row) == 20 for row in rows)
    assert sum(row.count("O") for row in rows) == 1
    assert _lives(browser) == lives
    _assert_idle(browser)


def _paddle_top(browser: webdriver.Chrome, column: int) -> int:
    """Return the top row of a paddle on the latest Pong screen."""
    rows = _text(browser, "game-run-screen").splitlines()
    return next(
        (
            index for index, row in enumerate(rows)
            if len(row) == 20 and row[column] == "|"
        ),
        -1,
    )


def test_run_pong_paddles(
    browser: webdriver.Chrome,
    live_server: str,
    db_session: Session,
    seeded_pong: int,
) -> None:
    """US5 AC3: Play the shipped Pong program with keyboard input."""
    ready = start_run(browser, live_server, db_session, "medium")
    _set_stage(browser, db_session, 2)
    _run(browser, ready, PONG["stages"][1]["reference_program"])

    wait = WebDriverWait(
        browser, EXECUTION_SECONDS, poll_frequency=WAIT_INTERVAL
    )
    wait.until(lambda driver: _paddle_top(driver, 0) > 0)

    left = _paddle_top(browser, 0)
    right = _paddle_top(browser, 19)
    screen = browser.find_element(*selector("game-run-screen"))

    screen.send_keys("q")
    wait.until(lambda driver: _paddle_top(driver, 0) == left - 1)
    assert _paddle_top(browser, 19) == right

    screen.send_keys("a")
    wait.until(lambda driver: _paddle_top(driver, 0) == left)
    assert _paddle_top(browser, 19) == right

    browser.find_element(*selector("game-stop")).click()
    _wait_for_status(browser, "Program stopped.")
    _assert_idle(browser)


def _send_key_batch(browser: webdriver.Chrome) -> None:
    """Deliver an oversized batch within one browser event-loop task."""
    screen = browser.find_element(*selector("game-run-screen"))
    browser.execute_script(
        """
        const screen = arguments[0];
        screen.focus();
        for (const key of "q".repeat(64) + "a".repeat(6)) {
            screen.dispatchEvent(new KeyboardEvent("keydown", {
                key, bubbles: true, cancelable: true
            }));
        }
        """,
        screen,
    )


@requires_host_play
def test_keys_run_and_submit_match(
    browser: webdriver.Chrome,
    live_server: str,
    db_session: Session,
    seeded_pong: int,
) -> None:
    """US5 AC8: Replay exactly the capped keys received during Run."""
    ready = start_run(browser, live_server, db_session, "medium")
    _set_stage(browser, db_session, 2)

    code = (
        "import json\n"
        "received = []\n"
        "while True:\n"
        "    line = input()\n"
        "    received.append(line)\n"
        "    if line:\n"
        "        break\n"
        "received.append(input())\n"
        "print(json.dumps(received))\n"
    )
    _run(browser, ready, code)
    ready.until(
        expected_conditions.visibility_of_element_located(
            selector("game-run-screen")
        )
    )
    _send_key_batch(browser)
    _wait_for_status(browser, "Program finished.")

    run_screen = _text(browser, "game-run-screen")
    received = json.loads(run_screen)
    assert received[-2:] == ["q" * 64, ""]
    assert all(line == "" for line in received[:-2])
    _assert_idle(browser)

    # Change only this test's stage inside the test transaction.
    # Replay exactly the browser's input sequence through Submit.
    run = db_session.get(GameRun, _current_run_id(browser))
    assert run is not None
    stage = db_session.scalar(
        select(Stage).where(
            Stage.campaign_id == run.campaign_id,
            Stage.number == 2,
        )
    )
    assert stage is not None

    stage.check_script = (
        "def check(game):\n"
        f"    for line in {received!r}:\n"
        "        game.send(line)\n"
        "    game.check(game.finished, 'Program must finish.')\n"
    )
    db_session.commit()

    browser.find_element(*selector("game-submit")).click()
    ready.until(
        expected_conditions.visibility_of_element_located(
            selector("game-verdict")
        )
    )

    assert _text(browser, "game-verdict-heading") == "PASS"
    assert _text(browser, "game-verdict-frame") == run_screen
    _assert_idle(browser)
