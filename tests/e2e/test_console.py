"""
File: test_console.py
Description: Selenium coverage for the console under the editor: it
    resizes against the editor by mouse and keyboard in both layouts,
    collapses and expands, opens and announces a new verdict, keeps wide
    output inside itself, and remembers its layout.
Author(s): Tyler Black
"""

import pytest
from selenium import webdriver
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions
from selenium.webdriver.support.ui import WebDriverWait
from sqlalchemy.orm import Session

from tests.e2e.support import selector, start_run, write_code

DRAG_PIXELS = 24
# The handle's arrow-key step is --space-4 and its page step --grid-size.
KEY_STEP = 16
PAGE_STEP = 64
VERDICT_SECONDS = 10
STACKED_WINDOW = (420, 900)
TALL_WINDOW = (1280, 900)
SHORT_WINDOW = (1280, 800)


def _find(browser: webdriver.Chrome, test_id: str) -> WebElement:
    return browser.find_element(*selector(test_id))


def _open_play_page(
    browser: webdriver.Chrome, live_server: str, db_session: Session
) -> WebDriverWait:
    ready = start_run(browser, live_server, db_session, "medium", "Consoler")
    ready.until(
        expected_conditions.element_to_be_clickable(
            selector("game-console-toggle")
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


def _panel_width(browser: webdriver.Chrome) -> int:
    return browser.execute_script(
        "return document.querySelector('.game-editor-panel').offsetWidth"
    )


def _value(handle: WebElement, name: str) -> int:
    return int(handle.get_attribute(f"aria-{name}"))


def _expand_at_minimum(browser: webdriver.Chrome) -> WebElement:
    """Open the console and shrink it to its minimum height."""
    _find(browser, "game-console-toggle").click()
    handle = _find(browser, "game-console-handle")
    handle.send_keys(Keys.HOME)
    return handle


def _drag(browser: webdriver.Chrome, handle: WebElement, pixels: int):
    browser.execute_script(
        "arguments[0].scrollIntoView({block: 'center'})", handle
    )
    ActionChains(browser).click_and_hold(handle).move_by_offset(
        0, pixels
    ).release().perform()


@pytest.mark.e2e
def test_console_starts_collapsed_and_toggles(
    browser: webdriver.Chrome,
    live_server: str,
    db_session: Session,
    seeded_pong: int,
) -> None:
    """The bar collapses and expands the console, by mouse and keyboard."""
    _open_play_page(browser, live_server, db_session)
    toggle = _find(browser, "game-console-toggle")
    body = _find(browser, "game-console-body")
    handle = _find(browser, "game-console-handle")
    assert toggle.get_attribute("aria-controls") == body.get_attribute("id")
    assert body.get_attribute("aria-labelledby") == toggle.get_attribute("id")
    assert body.get_attribute("tabindex") == "0"
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
    _open_play_page(browser, live_server, db_session)
    handle = _expand_at_minimum(browser)
    console_before = _console_height(browser)
    editor_before = _editor_height(browser)

    _drag(browser, handle, -DRAG_PIXELS)

    assert _console_height(browser) == console_before + DRAG_PIXELS
    assert _editor_height(browser) == editor_before - DRAG_PIXELS
    assert _value(handle, "valuenow") == _console_height(browser)


@pytest.mark.e2e
def test_stacked_layout_trades_editor_height_too(
    browser: webdriver.Chrome,
    live_server: str,
    db_session: Session,
    seeded_pong: int,
) -> None:
    """On a narrow screen the editor still gives up what the console takes."""
    browser.set_window_size(*STACKED_WINDOW)
    _open_play_page(browser, live_server, db_session)
    handle = _expand_at_minimum(browser)
    console_before = _console_height(browser)
    editor_before = _editor_height(browser)

    _drag(browser, handle, -DRAG_PIXELS)
    assert _console_height(browser) == console_before + DRAG_PIXELS
    assert _editor_height(browser) == editor_before - DRAG_PIXELS

    handle.send_keys(Keys.ARROW_UP)
    grown = DRAG_PIXELS + KEY_STEP
    assert _console_height(browser) == console_before + grown
    assert _editor_height(browser) == editor_before - grown


@pytest.mark.e2e
def test_handle_resizes_with_keys_within_limits(
    browser: webdriver.Chrome,
    live_server: str,
    db_session: Session,
    seeded_pong: int,
) -> None:
    """Arrow and Page keys step the size; Home and End stop at the limits."""
    _open_play_page(browser, live_server, db_session)
    handle = _expand_at_minimum(browser)
    assert handle.get_attribute("role") == "separator"
    assert handle.get_attribute("aria-orientation") == "horizontal"
    start = _value(handle, "valuemin")
    assert _value(handle, "valuenow") == start
    assert _console_height(browser) == start
    handle.send_keys(Keys.ARROW_DOWN)
    assert _value(handle, "valuenow") == start

    handle.send_keys(Keys.ARROW_UP, Keys.ARROW_UP)
    assert _value(handle, "valuenow") == start + 2 * KEY_STEP
    handle.send_keys(Keys.ARROW_DOWN)
    assert _value(handle, "valuenow") == start + KEY_STEP
    assert _console_height(browser) == start + KEY_STEP

    handle.send_keys(Keys.PAGE_UP)
    assert _value(handle, "valuenow") == start + KEY_STEP + PAGE_STEP
    handle.send_keys(Keys.PAGE_DOWN)
    assert _value(handle, "valuenow") == start + KEY_STEP

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
def test_window_resize_clamps_then_restores_the_size(
    browser: webdriver.Chrome,
    live_server: str,
    db_session: Session,
    seeded_pong: int,
) -> None:
    """A shorter window clamps the console; a taller one restores it."""
    browser.set_window_size(*TALL_WINDOW)
    ready = _open_play_page(browser, live_server, db_session)
    _find(browser, "game-console-toggle").click()
    handle = _find(browser, "game-console-handle")
    handle.send_keys(Keys.END)
    preferred = _value(handle, "valuenow")

    browser.set_window_size(*SHORT_WINDOW)
    ready.until(lambda _: _value(handle, "valuemax") < preferred)
    assert _value(handle, "valuenow") == _value(handle, "valuemax")
    assert _console_height(browser) == _value(handle, "valuenow")

    browser.set_window_size(*STACKED_WINDOW)
    ready.until(lambda _: _value(handle, "valuemax") > preferred)
    assert _value(handle, "valuenow") == preferred

    browser.set_window_size(*TALL_WINDOW)
    ready.until(lambda _: _value(handle, "valuemax") == preferred)
    assert _console_height(browser) == preferred


@pytest.mark.e2e
def test_new_verdict_opens_and_announces(
    browser: webdriver.Chrome,
    live_server: str,
    db_session: Session,
    seeded_pong: int,
) -> None:
    """A verdict opens a collapsed console and is read to screen readers."""
    ready = _open_play_page(browser, live_server, db_session)
    assert not _expanded(browser)
    write_code(browser, ready, "print(1)")
    _find(browser, "game-submit").click()
    WebDriverWait(browser, VERDICT_SECONDS).until(
        expected_conditions.visibility_of_element_located(
            selector("game-verdict")
        )
    )
    assert _expanded(browser)
    assert _find(browser, "game-console-body").is_displayed()

    status = _find(browser, "game-console-status")
    assert status.get_attribute("role") == "status"
    ready.until(lambda _: status.get_attribute("textContent"))
    shown = [
        _find(browser, test_id).text
        for test_id in ("game-verdict-heading", "game-verdict-reason")
    ]
    expected = ". ".join(text for text in shown if text)
    assert status.get_attribute("textContent") == expected


@pytest.mark.e2e
def test_wide_output_scrolls_inside_the_console(
    browser: webdriver.Chrome,
    live_server: str,
    db_session: Session,
    seeded_pong: int,
) -> None:
    """A very long output line never widens the editor window."""
    _open_play_page(browser, live_server, db_session)
    _find(browser, "game-console-toggle").click()
    panel_width = _panel_width(browser)
    body = _find(browser, "game-console-body")
    browser.execute_script(
        """
        const verdict = document.querySelector('[data-testid=game-verdict]');
        const frame = verdict.querySelector(
            '[data-testid=game-verdict-frame]');
        frame.textContent = 'O'.repeat(2000);
        frame.hidden = false;
        verdict.hidden = false;
        """
    )
    assert body.size["width"] < panel_width
    assert _panel_width(browser) == panel_width
    assert browser.execute_script(
        "return arguments[0].scrollWidth > arguments[0].clientWidth", body
    )


@pytest.mark.e2e
def test_console_layout_survives_a_reload(
    browser: webdriver.Chrome,
    live_server: str,
    db_session: Session,
    seeded_pong: int,
) -> None:
    """The console's height and open state come back after a reload."""
    ready = _open_play_page(browser, live_server, db_session)
    handle = _expand_at_minimum(browser)
    handle.send_keys(Keys.ARROW_UP)
    resized = _value(handle, "valuenow")
    assert resized == _value(handle, "valuemin") + KEY_STEP

    browser.refresh()
    ready.until(
        expected_conditions.visibility_of_element_located(
            selector("game-console-body")
        )
    )
    assert _expanded(browser)
    assert _console_height(browser) == resized

    _find(browser, "game-console-toggle").click()
    browser.refresh()
    ready.until(
        expected_conditions.element_to_be_clickable(
            selector("game-console-toggle")
        )
    )
    assert not _expanded(browser)
    _find(browser, "game-console-toggle").click()
    assert _console_height(browser) == resized


@pytest.mark.e2e
def test_unreadable_saved_layout_falls_back(
    browser: webdriver.Chrome,
    live_server: str,
    db_session: Session,
    seeded_pong: int,
) -> None:
    """Garbage in storage leaves a collapsed console that still works."""
    ready = _open_play_page(browser, live_server, db_session)
    browser.execute_script(
        "localStorage.setItem('rokos:console', '{not json')"
    )
    browser.refresh()
    ready.until(
        expected_conditions.element_to_be_clickable(
            selector("game-console-toggle")
        )
    )
    assert not _expanded(browser)
    _find(browser, "game-console-toggle").click()
    assert _expanded(browser)
    assert _find(browser, "game-console-body").is_displayed()
