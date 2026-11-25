"""
File: test_run_sample.py
Description: Selenium coverage for Run Sample (US5).
Author(s): Steph Rivera
"""

import pytest
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions
from selenium.webdriver.support.ui import WebDriverWait
from sqlalchemy.orm import Session

from src.business.auth_service import AuthService
from src.data.repositories.user_repository import UserRepository

CORRECT_CODE = (
    "n = int(input())\n"
    "prices = list(map(int, input().split()))\n"
    "print(sum(prices))"
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
    browser.find_element(*_selector("login-password")).send_keys(
        "password123"
    )
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


def _run_sample_and_wait(browser: webdriver.Chrome) -> None:
    """Wait for Python, run the samples, and wait for the results."""
    WebDriverWait(browser, PYTHON_READY_SECONDS).until(
        expected_conditions.element_to_be_clickable(
            _selector("game-run-sample")
        )
    ).click()
    WebDriverWait(browser, RESULT_SECONDS).until(
        expected_conditions.visibility_of_element_located(
            _selector("game-sample-summary")
        )
    )


@pytest.mark.e2e
def test_correct_program_passes(
    browser: webdriver.Chrome,
    live_server: str,
    db_session: Session,
    seeded_beginner: int,
) -> None:
    """US5 AC1: Correct Python code passes the visible sample."""
    ready = _start_run(browser, live_server, db_session)
    _write_code(browser, ready, CORRECT_CODE)
    _run_sample_and_wait(browser)

    status = browser.find_element(*_selector("game-sample-1-status"))
    assert status.text == "PASS"

    summary = browser.find_element(*_selector("game-sample-summary"))
    assert summary.text == "1 of 1 samples passed"


@pytest.mark.e2e
def test_incorrect_program_fails(
    browser: webdriver.Chrome,
    live_server: str,
    db_session: Session,
    seeded_beginner: int,
) -> None:
    """US5 AC1: Incorrect output fails and displays the comparison."""
    ready = _start_run(browser, live_server, db_session)
    _write_code(browser, ready, "print(400)")
    _run_sample_and_wait(browser)

    status = browser.find_element(*_selector("game-sample-1-status"))
    assert status.text == "FAIL"

    expected = browser.find_element(*_selector("game-sample-1-expected"))
    actual = browser.find_element(*_selector("game-sample-1-actual"))

    assert expected.text == "425"
    assert actual.text == "400"

    summary = browser.find_element(*_selector("game-sample-summary"))
    assert summary.text == "0 of 1 samples passed"
