"""
File: test_submit.py
Description: Selenium coverage for Submit (US6): a passing program, a
    broken rule named in the verdict, the busy Submit button while the
    Overlord plays, and a stage that can't be graded yet.
Author(s): Richard Hall, Tyler Black
"""

import json
from pathlib import Path

import pytest
from selenium import webdriver
from selenium.webdriver.support import expected_conditions
from selenium.webdriver.support.ui import WebDriverWait
from sqlalchemy.orm import Session

from tests.conftest import requires_host_play
from tests.e2e.support import selector, start_run, write_code

ROOT = Path(__file__).resolve().parents[2]
PONG = json.loads(
    (ROOT / "content/campaigns/seed/medium/pong.json").read_text("utf-8")
)
STAGE_1 = PONG["stages"][0]["reference_program"]
TWO_BALLS = PONG["stages"][0]["broken_program"]
TRAFFIC_STAGE_1 = json.loads(
    (ROOT / "content/campaigns/seed/beginner/traffic_light.json").read_text(
        "utf-8"
    )
)["stages"][0]["reference_program"]
# Prints the board after 0.6 s, inside the 1 s limit, so grading is slow
# enough to see the busy button.
SLOW_STAGE_1 = "import time\n\ntime.sleep(0.6)\n" + STAGE_1
BUSY_LABEL = "The Overlord is playing your program…"
VERDICT_SECONDS = 10


def _submit_and_wait(browser: webdriver.Chrome) -> None:
    browser.find_element(*selector("game-submit")).click()
    WebDriverWait(browser, VERDICT_SECONDS).until(
        expected_conditions.visibility_of_element_located(
            selector("game-verdict")
        )
    )


@requires_host_play
@pytest.mark.e2e
def test_reference_program_passes(
    browser: webdriver.Chrome,
    live_server: str,
    db_session: Session,
    seeded_pong: int,
) -> None:
    """US6 AC1: Submit the Pong stage 1 reference and see a pass."""
    ready = start_run(browser, live_server, db_session, "medium")
    write_code(browser, ready, STAGE_1)
    _submit_and_wait(browser)
    heading = browser.find_element(*selector("game-verdict-heading"))
    assert heading.text == "PASS"


@requires_host_play
@pytest.mark.e2e
def test_broken_rule_is_named(
    browser: webdriver.Chrome,
    live_server: str,
    db_session: Session,
    seeded_pong: int,
) -> None:
    """US6 AC2: a board with two O characters fails, naming the rule."""
    ready = start_run(browser, live_server, db_session, "medium")
    write_code(browser, ready, TWO_BALLS)
    _submit_and_wait(browser)
    assert browser.find_element(*selector("game-verdict-heading")).text == (
        "FAIL"
    )
    reason = browser.find_element(*selector("game-verdict-reason"))
    assert reason.text == "The board must show exactly one ball (O)."
    frame = browser.find_element(*selector("game-verdict-frame"))
    assert frame.is_displayed()
    assert frame.get_attribute("textContent").count("O") == 2


@requires_host_play
@pytest.mark.e2e
def test_submit_is_busy_until_the_verdict(
    browser: webdriver.Chrome,
    live_server: str,
    db_session: Session,
    seeded_pong: int,
) -> None:
    """US6 AC5: Submit is disabled and says so while grading runs."""
    ready = start_run(browser, live_server, db_session, "medium")
    write_code(browser, ready, SLOW_STAGE_1)
    button = browser.find_element(*selector("game-submit"))
    button.click()
    assert not button.is_enabled()
    assert button.get_attribute("textContent") == BUSY_LABEL
    verdict = browser.find_element(*selector("game-verdict"))
    assert not verdict.is_displayed()
    WebDriverWait(browser, VERDICT_SECONDS).until(
        expected_conditions.visibility_of(verdict)
    )
    assert button.is_enabled()
    assert button.get_attribute("textContent") == "Submit"


@requires_host_play
@pytest.mark.e2e
def test_beginner_stage_gets_a_verdict(
    browser: webdriver.Chrome,
    live_server: str,
    db_session: Session,
    seeded_beginner: int,
) -> None:
    """#19 AC1: Beginner is graded by its check script like Medium."""
    ready = start_run(browser, live_server, db_session, "beginner")
    write_code(browser, ready, TRAFFIC_STAGE_1)
    _submit_and_wait(browser)
    heading = browser.find_element(*selector("game-verdict-heading"))
    assert heading.text == "PASS"
