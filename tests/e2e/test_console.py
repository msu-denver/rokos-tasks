"""
File: test_console.py
Description: Selenium coverage for the console under the editor: it
    resizes against the editor by mouse and keyboard, collapses and
    expands, opens for a new verdict, and remembers its layout.
Author(s): Tyler Black
"""

import pytest
from selenium import webdriver
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions
from selenium.webdriver.support.ui import WebDriverWait
from sqlalchemy.orm import Session

from src.business.auth_service import AuthService
from src.data.repositories.user_repository import UserRepository

DRAG_PIXELS = 24
# The handle's arrow-key step is --space-4.
KEY_STEP = 16
VERDICT_SECONDS = 10


def _selector(test_id: str) -> tuple[str, str]:
    return By.CSS_SELECTOR, f'[data-testid="{test_id}"]'


def _find(browser: webdriver.Chrome, test_id: str) -> WebElement:
    return browser.find_element(*_selector(test_id))


def _start_run(
    browser: webdriver.Chrome, live_server: str, db_session: Session
) -> WebDriverWait:
    """Register, log in, and start a Medium run on the play page."""
    AuthService(UserRepository(db_session)).register(
        "Consoler", "password123", "password123"
    )
    browser.get(f"{live_server}/login")
    ready = WebDriverWait(browser, 15)
    ready.until(
        expected_conditions.visibility_of_element_located(
            _selector("login-username")
        )
    ).send_keys("Consoler")
    _find(browser, "login-password").send_keys("password123")
    _find(browser, "login-submit").click()
    ready.until(
        expected_conditions.element_to_be_clickable(
            _selector("home-start-link")
        )
    ).click()
    ready.until(
        expected_conditions.element_to_be_clickable(
            _selector("start-tier-medium-button")
        )
    ).click()
    ready.until(expected_conditions.url_matches(r"/play/\d+$"))
    ready.until(
        expected_conditions.element_to_be_clickable(
            _selector("game-console-toggle")
        )
    )
    return ready


def _expanded(browser: webdriver.Chrome) -> bool:
    toggle = _find(browser, "game-console-toggle")
    return toggle.get_attribute("aria-expanded") == "true"


def _console_height(browser: webdriver.Chrome) -> int:
    return _find(browser, "game-console-body").size["height"]


def _editor_height(browser: webdriver.Chrome) -> int:
    return _find(browser, "game-editor").size["height"]


def _value(handle: WebElement, name: str) -> int:
    return int(handle.get_attribute(f"aria-{name}"))


@pytest.mark.e2e
def test_console_starts_collapsed_and_toggles(
    browser: webdriver.Chrome,
    live_server: str,
    db_session: Session,
    seeded_pong: int,
) -> None:
    """The bar collapses and expands the console, by mouse and keyboard."""
    _start_run(browser, live_server, db_session)
    toggle = _find(browser, "game-console-toggle")
    body = _find(browser, "game-console-body")
    handle = _find(browser, "game-console-handle")
    assert toggle.get_attribute("aria-controls") == body.get_attribute("id")
    assert not _expanded(browser)
    assert not body.is_displayed()
    assert not handle.is_displayed()

    toggle.click()
    assert _expanded(browser)
    assert body.is_displayed()
    assert handle.is_displayed()

    toggle.send_keys(Keys.ENTER)
    assert not _expanded(browser)
    assert not body.is_displayed()


@pytest.mark.e2e
def test_dragging_the_handle_trades_editor_height(
    browser: webdriver.Chrome,
    live_server: str,
    db_session: Session,
    seeded_pong: int,
) -> None:
    """Dragging the top edge up grows the console and shrinks the editor."""
    _start_run(browser, live_server, db_session)
    _find(browser, "game-console-toggle").click()
    handle = _find(browser, "game-console-handle")
    console_before = _console_height(browser)
    editor_before = _editor_height(browser)

    ActionChains(browser).click_and_hold(handle).move_by_offset(
        0, -DRAG_PIXELS
    ).release().perform()

    assert _console_height(browser) == console_before + DRAG_PIXELS
    assert _editor_height(browser) == editor_before - DRAG_PIXELS
    assert _value(handle, "valuenow") == _console_height(browser)


@pytest.mark.e2e
def test_handle_resizes_with_keys_within_limits(
    browser: webdriver.Chrome,
    live_server: str,
    db_session: Session,
    seeded_pong: int,
) -> None:
    """Arrow keys step the size; Home and End stop at the limits."""
    _start_run(browser, live_server, db_session)
    _find(browser, "game-console-toggle").click()
    handle = _find(browser, "game-console-handle")
    assert handle.get_attribute("role") == "separator"
    start = _value(handle, "valuenow")

    handle.send_keys(Keys.ARROW_UP)
    assert _value(handle, "valuenow") == start + KEY_STEP
    handle.send_keys(Keys.ARROW_DOWN, Keys.ARROW_DOWN)
    assert _value(handle, "valuenow") == start - KEY_STEP
    assert _console_height(browser) == start - KEY_STEP

    handle.send_keys(Keys.HOME)
    assert _value(handle, "valuenow") == _value(handle, "valuemin")
    assert _console_height(browser) == _value(handle, "valuemin")

    handle.send_keys(Keys.END)
    assert _value(handle, "valuenow") == _value(handle, "valuemax")
    # At the limit the editor keeps its minimum height.
    editor_min = browser.execute_script(
        "return parseFloat(getComputedStyle(arguments[0]).minBlockSize)",
        _find(browser, "game-editor"),
    )
    assert _editor_height(browser) == editor_min
    handle.send_keys(Keys.ARROW_UP)
    assert _value(handle, "valuenow") == _value(handle, "valuemax")


@pytest.mark.e2e
def test_new_verdict_opens_a_collapsed_console(
    browser: webdriver.Chrome,
    live_server: str,
    db_session: Session,
    seeded_pong: int,
) -> None:
    """Submitting while the console is collapsed opens it to the verdict."""
    ready = _start_run(browser, live_server, db_session)
    assert not _expanded(browser)
    ready.until(
        lambda driver: driver.execute_script(
            "return !!window.monaco && monaco.editor.getEditors().length > 0"
        )
    )
    browser.execute_script(
        "monaco.editor.getEditors()[0].setValue(arguments[0])", "print(1)"
    )
    _find(browser, "game-submit").click()
    WebDriverWait(browser, VERDICT_SECONDS).until(
        expected_conditions.visibility_of_element_located(
            _selector("game-verdict")
        )
    )
    assert _expanded(browser)
    assert _find(browser, "game-verdict-heading").text == "FAIL"


@pytest.mark.e2e
def test_console_layout_survives_a_reload(
    browser: webdriver.Chrome,
    live_server: str,
    db_session: Session,
    seeded_pong: int,
) -> None:
    """The console's height and open state come back after a reload."""
    ready = _start_run(browser, live_server, db_session)
    _find(browser, "game-console-toggle").click()
    handle = _find(browser, "game-console-handle")
    handle.send_keys(Keys.ARROW_UP, Keys.ARROW_UP, Keys.ARROW_UP)
    resized = _value(handle, "valuenow")

    browser.refresh()
    ready.until(
        expected_conditions.visibility_of_element_located(
            _selector("game-console-body")
        )
    )
    assert _expanded(browser)
    assert _console_height(browser) == resized

    _find(browser, "game-console-toggle").click()
    browser.refresh()
    ready.until(
        expected_conditions.element_to_be_clickable(
            _selector("game-console-toggle")
        )
    )
    assert not _expanded(browser)
    _find(browser, "game-console-toggle").click()
    assert _console_height(browser) == resized
