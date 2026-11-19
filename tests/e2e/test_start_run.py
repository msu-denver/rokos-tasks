"""
File: test_start_run.py
Description: Selenium coverage for choosing a tier and opening Stage 1.
Author(s): Tyler Black
"""

import pytest
from selenium import webdriver
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions
from selenium.webdriver.support.ui import WebDriverWait
from sqlalchemy.orm import Session

from src.business.auth_service import AuthService
from src.data.repositories.campaign_repository import CampaignRepository
from src.data.repositories.user_repository import UserRepository


def _selector(test_id: str) -> tuple[str, str]:
    return By.CSS_SELECTOR, f'[data-testid="{test_id}"]'


def _start_beginner(
    browser: webdriver.Chrome,
    live_server: str,
    db_session: Session,
) -> WebDriverWait:
    AuthService(UserRepository(db_session)).register(
        "RunStarter", "password123", "password123"
    )
    browser.get(f"{live_server}/login")
    ready = WebDriverWait(browser, 15)

    ready.until(
        expected_conditions.visibility_of_element_located(
            _selector("login-username")
        )
    ).send_keys("RunStarter")
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


def _set_viewport(browser: webdriver.Chrome, width: int, height: int) -> None:
    browser.execute_cdp_cmd(
        "Emulation.setDeviceMetricsOverride",
        {
            "width": width,
            "height": height,
            "deviceScaleFactor": 1,
            "mobile": False,
        },
    )


@pytest.mark.e2e
def test_start_beginner_run(
    browser: webdriver.Chrome,
    live_server: str,
    db_session: Session,
    seeded_beginner: int,
) -> None:
    """Start Beginner and retain the responsive layout and resume rules."""
    ready = _start_beginner(browser, live_server, db_session)
    first_url = browser.current_url
    feed = browser.find_element(*_selector("game-feed"))
    editor = browser.find_element(*_selector("game-editor"))
    assert feed.rect["x"] < editor.rect["x"]

    _set_viewport(browser, 1280, 720)
    assert browser.execute_script(
        "const page = document.scrollingElement;"
        "return page.scrollHeight === page.clientHeight"
        " && page.scrollWidth === page.clientWidth;"
    )
    assert editor.rect["width"] > feed.rect["width"]
    prompt_top, editor_bottom, viewport_height = browser.execute_script(
        "return [arguments[0].getBoundingClientRect().top,"
        "arguments[1].getBoundingClientRect().bottom, window.innerHeight];",
        browser.find_element(*_selector("game-prompt")),
        editor,
    )
    assert 0 <= prompt_top < viewport_height
    assert editor_bottom <= viewport_height

    _set_viewport(browser, 390, 560)
    assert editor.rect["y"] >= feed.rect["y"] + feed.rect["height"]
    assert browser.execute_script(
        "const page = document.scrollingElement;"
        "return page.scrollWidth === page.clientWidth;"
    )

    browser.get(f"{live_server}/start")
    ready.until(
        expected_conditions.visibility_of_element_located(
            _selector("start-title")
        )
    )
    resume = ready.until(
        expected_conditions.element_to_be_clickable(
            _selector("start-resume-run")
        )
    )
    for width, height, needs_scroll in ((1280, 640, False), (390, 560, True)):
        _set_viewport(browser, width, height)
        horizontal, vertical = browser.execute_script(
            "const page = document.scrollingElement;"
            "return [page.scrollWidth - page.clientWidth,"
            "page.scrollHeight - page.clientHeight];"
        )
        assert horizontal == 0
        assert (vertical > 0) == needs_scroll, (width, height, vertical)

    last_tier = browser.find_element(*_selector("start-tier-impossible"))
    scroll, top, bottom, viewport_height = browser.execute_script(
        "window.scrollTo(0, document.scrollingElement.scrollHeight);"
        "const {top, bottom} = arguments[0].getBoundingClientRect();"
        "return [window.scrollY, top, bottom, window.innerHeight];",
        last_tier,
    )
    assert scroll > 0
    assert 0 <= top < bottom <= viewport_height

    resume.click()
    ready.until(expected_conditions.url_to_be(first_url))


@pytest.mark.e2e
def test_cancel_then_confirm_new_run(
    browser: webdriver.Chrome,
    live_server: str,
    db_session: Session,
    seeded_beginner: int,
) -> None:
    """Cancel returns to the tier picker and Confirm opens a replacement."""
    ready = _start_beginner(browser, live_server, db_session)
    first_url = browser.current_url
    start_url = f"{live_server}/start"
    can_start = expected_conditions.element_to_be_clickable(
        _selector("start-tier-beginner-button")
    )
    confirmation_visible = expected_conditions.visibility_of_element_located(
        _selector("start-confirm-abandon")
    )

    browser.get(start_url)
    ready.until(can_start).click()
    ready.until(confirmation_visible)
    ready.until(
        expected_conditions.element_to_be_clickable(
            _selector("start-confirm-abandon-cancel")
        )
    ).click()
    ready.until(expected_conditions.url_to_be(start_url))
    assert not browser.find_elements(*_selector("start-confirm-abandon"))
    resume = ready.until(
        expected_conditions.element_to_be_clickable(
            _selector("start-resume-run")
        )
    )
    assert resume.get_attribute("href") == first_url

    browser.get(start_url)
    ready.until(can_start).click()
    ready.until(confirmation_visible)
    ready.until(
        expected_conditions.element_to_be_clickable(
            _selector("start-confirm-abandon-submit")
        )
    ).click()
    ready.until(expected_conditions.url_matches(r"/play/\d+$"))
    assert browser.current_url != first_url


@pytest.mark.e2e
def test_game_editor_restores_pending_and_empty_drafts(
    browser: webdriver.Chrome,
    live_server: str,
    db_session: Session,
    seeded_beginner: int,
) -> None:
    """Show the prompt, start with empty Python, and restore saved drafts."""
    repository = CampaignRepository(db_session)
    campaign = repository.get(seeded_beginner)
    assert campaign is not None
    stage = campaign.stages[0]
    stage.prompt = stage.prompt.replace("item count N", "item count `N`")
    description = stage.prompt.split("\n\nExample 1 input:", 1)[0].rstrip()
    expected_prompt = description.replace("`", "")
    repository.commit()
    ready = _start_beginner(browser, live_server, db_session)
    prompt = browser.find_element(*_selector("game-prompt"))
    exact_value = ready.until(
        lambda driver: prompt.find_element(By.TAG_NAME, "code")
    )
    assert prompt.get_property("textContent") == expected_prompt
    assert exact_value.text == "N"
    stage_readout = browser.find_element(*_selector("game-stage-readout"))
    assert stage_readout.get_attribute("aria-label") == (
        "Beginner, stage 1 of 2"
    )
    assert browser.find_element(*_selector("game-tier")).text == "BEGINNER"
    assert (
        browser.find_element(*_selector("game-lives")).get_attribute(
            "aria-label"
        )
        == "4 of 4 lives"
    )
    assert browser.find_element(*_selector("game-timer")).text == "00:00"
    assert browser.find_element(*_selector("game-editor")).is_displayed()
    ready.until(
        lambda driver: (
            driver.execute_script(
                "return window.monaco?.editor.getModels()[0]?.getLanguageId();"
            )
            == "python"
        )
    )
    assert (
        browser.execute_script(
            "return monaco.editor.getModels()[0].getValue();"
        )
        == ""
    )
    options = browser.execute_script(
        "return monaco.editor.getModels()[0].getOptions();"
    )
    assert options["tabSize"] == 4 and options["insertSpaces"]

    previous = None
    run_id = browser.current_url.rsplit("/", 1)[1]
    draft_key = f"rokos:run:{run_id}:stage:1"
    for draft in ("print(sum(map(int, input().split())))\n", ""):
        assert (
            browser.execute_script(
                "monaco.editor.getModels()[0].setValue(arguments[0]);"
                "return localStorage.getItem(arguments[1]);",
                draft,
                draft_key,
            )
            == previous
        )
        browser.refresh()
        ready.until(
            lambda driver, expected=draft: driver.execute_script(
                "return window.monaco?.editor.getModels()[0]?.getValue()"
                " === arguments[0];",
                expected,
            )
        )
        assert (
            browser.execute_script(
                "return localStorage.getItem(arguments[0]);", draft_key
            )
            == draft
        )
        previous = draft


@pytest.mark.e2e
def test_python_editor_pairs_quotes_and_completes_with_tab(
    browser: webdriver.Chrome,
    live_server: str,
    db_session: Session,
    seeded_beginner: int,
) -> None:
    """Use actual keystrokes for quote pairing and Python completion."""
    ready = _start_beginner(browser, live_server, db_session)
    ready.until(
        lambda driver: driver.execute_script(
            "return window.monaco?.editor.getEditors().length > 0;"
        )
    )
    for source, keys, expected in (
        ("message = ", '"text', 'message = "text"'),
        ("message = ", "'text", "message = 'text'"),
        ("", "pri" + Keys.TAB, "print"),
        (
            "def calc_total():\n    pass\n\n",
            "calc_t" + Keys.TAB,
            "def calc_total():\n    pass\n\ncalc_total",
        ),
        (
            "price_total = 0\n",
            "price_t" + Keys.TAB,
            "price_total = 0\nprice_total",
        ),
        ("def calc_total():\n", Keys.TAB, "def calc_total():\n    "),
    ):
        browser.execute_script(
            "const editor = monaco.editor.getEditors()[0];"
            "const model = editor.getModel();"
            "model.setValue(arguments[0]);"
            "editor.setPosition(model.getPositionAt(arguments[0].length));"
            "editor.focus();",
            source,
        )
        ActionChains(browser).send_keys(keys).perform()
        ready.until(
            lambda driver, code=expected: driver.execute_script(
                "return monaco.editor.getModels()[0].getValue()"
                " === arguments[0];",
                code,
            ),
            f"Keystrokes {keys!r} should produce {expected!r}",
        )


@pytest.mark.e2e
def test_editor_falls_back_to_autosaving_textarea(
    browser: webdriver.Chrome,
    live_server: str,
    db_session: Session,
    seeded_beginner: int,
) -> None:
    """Allow code editing and immediate draft recovery with the CDN down."""
    browser.execute_cdp_cmd("Network.enable", {})
    browser.execute_cdp_cmd(
        "Network.setBlockedURLs",
        {"urls": ["*cdn.jsdelivr.net/npm/monaco-editor@*"]},
    )
    ready = _start_beginner(browser, live_server, db_session)
    textarea_selector = (
        By.CSS_SELECTOR,
        '[data-testid="game-editor"] textarea',
    )
    textarea = ready.until(
        expected_conditions.visibility_of_element_located(textarea_selector)
    )
    assert textarea.get_property("value") == ""
    textarea.send_keys(Keys.END, "# draft")
    draft = textarea.get_property("value")
    browser.refresh()
    ready.until(
        lambda driver: (
            driver.find_element(*textarea_selector).get_property("value")
            == draft
        )
    )
