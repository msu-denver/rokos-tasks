"""
File: test_progression.py
Description: Selenium coverage for US7: a pass opens the next stage with
    the checkpoint code (or the player's saved draft), a fail costs a life
    and resets the editor to the checkpoint, and a finished run shows the
    victory or game-over screen with its score breakdown.
Author(s): Tyler Black
"""

import json
from pathlib import Path

import pytest
from selenium import webdriver
from selenium.common.exceptions import StaleElementReferenceException
from selenium.webdriver.support import expected_conditions
from selenium.webdriver.support.ui import WebDriverWait
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.data.models.game_run import GameRun
from tests.conftest import requires_host_play
from tests.e2e.support import selector, start_run, write_code

ROOT = Path(__file__).resolve().parents[2]
SEEDS = ROOT / "content/campaigns/seed"
PONG = json.loads((SEEDS / "medium/pong.json").read_text("utf-8"))
TRAFFIC = json.loads(
    (SEEDS / "beginner/traffic_light.json").read_text("utf-8")
)
PONG_STAGE_1 = PONG["stages"][0]["reference_program"]
CRASH = "1 / 0\n"
VERDICT_SECONDS = 10


def _submit(browser: webdriver.Chrome) -> None:
    """Click Submit and wait until the button is idle or the page reloads."""
    button = browser.find_element(*selector("game-submit"))
    button.click()

    def idle(_driver: webdriver.Chrome) -> bool:
        try:
            return button.get_attribute("textContent") == "Submit"
        except StaleElementReferenceException:
            return True  # The run ended and the page reloaded.

    WebDriverWait(browser, VERDICT_SECONDS).until(idle)


def _editor_code(browser: webdriver.Chrome) -> str:
    """Wait for Monaco, then return what the editor holds."""
    WebDriverWait(browser, 15).until(
        lambda driver: driver.execute_script(
            "return !!window.monaco && monaco.editor.getEditors().length > 0"
        )
    )
    return browser.execute_script(
        "return monaco.editor.getEditors()[0].getValue()"
    )


def _stage_label(browser: webdriver.Chrome) -> str:
    readout = browser.find_element(*selector("game-stage-readout"))
    return readout.get_attribute("aria-label")


def _run_id(browser: webdriver.Chrome) -> int:
    return int(browser.current_url.rsplit("/", 1)[1])


def _wait_for_result(browser: webdriver.Chrome) -> None:
    WebDriverWait(browser, VERDICT_SECONDS).until(
        expected_conditions.visibility_of_element_located(
            selector("game-result")
        )
    )


@requires_host_play
@pytest.mark.e2e
def test_pass_opens_the_next_stage_with_the_checkpoint(
    browser: webdriver.Chrome,
    live_server: str,
    db_session: Session,
    seeded_pong: int,
) -> None:
    """US7 AC1: a pass shows stage 2 with the Stage 1 code, and scores."""
    ready = start_run(browser, live_server, db_session, "medium")
    write_code(browser, ready, PONG_STAGE_1)
    _submit(browser)

    assert _stage_label(browser) == "Medium, stage 2 of 3"
    assert browser.title.startswith("Stage 2")
    prompt = browser.find_element(*selector("game-prompt")).text
    assert prompt.startswith(PONG["stages"][1]["prompt"][:40])
    assert _editor_code(browser) == PONG_STAGE_1
    heading = browser.find_element(*selector("game-verdict-heading"))
    assert heading.text == "PASS"
    run = db_session.scalars(
        select(GameRun).where(GameRun.id == _run_id(browser))
    ).one()
    assert run.score > 0

    # The server has the same state, so a reload shows the same stage.
    browser.refresh()
    assert _editor_code(browser) == PONG_STAGE_1
    assert _stage_label(browser) == "Medium, stage 2 of 3"


@requires_host_play
@pytest.mark.e2e
def test_saved_draft_wins_over_the_checkpoint(
    browser: webdriver.Chrome,
    live_server: str,
    db_session: Session,
    seeded_pong: int,
) -> None:
    """US7 AC1: a saved draft for the next stage wins over the checkpoint."""
    ready = start_run(browser, live_server, db_session, "medium")
    draft = "# my stage 2 draft\n"
    browser.execute_script(
        "localStorage.setItem(arguments[0], arguments[1])",
        f"rokos:run:{_run_id(browser)}:stage:2",
        draft,
    )
    write_code(browser, ready, PONG_STAGE_1)
    _submit(browser)

    assert _stage_label(browser) == "Medium, stage 2 of 3"
    assert _editor_code(browser) == draft
    stage_1_draft = browser.execute_script(
        "return localStorage.getItem(arguments[0])",
        f"rokos:run:{_run_id(browser)}:stage:1",
    )
    assert stage_1_draft is None


@requires_host_play
@pytest.mark.e2e
def test_fail_costs_a_life_and_resets_to_the_checkpoint(
    browser: webdriver.Chrome,
    live_server: str,
    db_session: Session,
    seeded_pong: int,
) -> None:
    """US7 AC2 and AC6: a fail drops a life and restores the checkpoint."""
    ready = start_run(browser, live_server, db_session, "medium")
    write_code(browser, ready, PONG_STAGE_1)
    _submit(browser)
    write_code(browser, ready, CRASH)
    _submit(browser)

    lives = browser.find_element(*selector("game-lives"))
    assert lives.get_attribute("aria-label") == "2 of 3 lives"
    full = lives.find_elements("css selector", ".game-life--full")
    assert len(full) == 2
    assert _stage_label(browser) == "Medium, stage 2 of 3"
    assert _editor_code(browser) == PONG_STAGE_1


@requires_host_play
@pytest.mark.e2e
def test_fail_on_stage_1_empties_the_editor(
    browser: webdriver.Chrome,
    live_server: str,
    db_session: Session,
    seeded_pong: int,
) -> None:
    """US7 AC6: with no checkpoint yet, a fail leaves the editor empty."""
    ready = start_run(browser, live_server, db_session, "medium")
    write_code(browser, ready, CRASH)
    _submit(browser)
    assert _editor_code(browser) == ""
    browser.refresh()
    assert _editor_code(browser) == ""


@requires_host_play
@pytest.mark.e2e
def test_clearing_the_last_stage_shows_victory(
    browser: webdriver.Chrome,
    live_server: str,
    db_session: Session,
    seeded_beginner: int,
) -> None:
    """US7 AC3: the last pass shows Victory with one row per stage."""
    ready = start_run(browser, live_server, db_session, "beginner")
    for stage in TRAFFIC["stages"]:
        write_code(browser, ready, stage["reference_program"])
        _submit(browser)
    _wait_for_result(browser)

    heading = browser.find_element(*selector("game-result-heading"))
    assert heading.text == "Victory"
    breakdown = browser.find_element(*selector("game-result-breakdown"))
    rows = breakdown.find_elements(*selector("game-result-row"))
    assert len(rows) == len(TRAFFIC["stages"])
    points = sum(int(row.text.split()[-1]) for row in rows)
    total = browser.find_element(*selector("game-result-total"))
    assert int(total.text) == points > 0


@requires_host_play
@pytest.mark.e2e
def test_losing_every_life_shows_game_over(
    browser: webdriver.Chrome,
    live_server: str,
    db_session: Session,
    seeded_beginner: int,
) -> None:
    """US7 AC3: at 0 lives the run ends on Game over with a 0 total."""
    ready = start_run(browser, live_server, db_session, "beginner")
    write_code(browser, ready, TRAFFIC["stages"][0]["reference_program"])
    _submit(browser)
    for _ in range(4):
        write_code(browser, ready, CRASH)
        _submit(browser)
    _wait_for_result(browser)

    heading = browser.find_element(*selector("game-result-heading"))
    assert heading.text == "Game over"
    breakdown = browser.find_element(*selector("game-result-breakdown"))
    assert len(breakdown.find_elements(*selector("game-result-row"))) == 1
    total = browser.find_element(*selector("game-result-total"))
    assert total.text == "0"
