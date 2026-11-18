"""
File: test_start_run.py
Description: Selenium coverage for choosing a tier and opening Stage 1.
Author(s): Tyler Black
"""

import pytest
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions
from selenium.webdriver.support.ui import WebDriverWait
from sqlalchemy.orm import Session

from src.business.auth_service import AuthService
from src.data.repositories.user_repository import UserRepository


@pytest.mark.e2e
def test_start_beginner_run(
    browser: webdriver.Chrome,
    live_server: str,
    db_session: Session,
    seeded_beginner: int,
) -> None:
    """Start Beginner, then check the tier layout with a run to resume."""
    AuthService(UserRepository(db_session)).register(
        "RunStarter", "password123", "password123"
    )
    browser.get(f"{live_server}/login")
    ready = WebDriverWait(browser, 10)

    def selector(test_id: str) -> tuple[str, str]:
        return By.CSS_SELECTOR, f'[data-testid="{test_id}"]'

    ready.until(
        expected_conditions.visibility_of_element_located(
            selector("login-username")
        )
    ).send_keys("RunStarter")
    browser.find_element(*selector("login-password")).send_keys("password123")
    browser.find_element(*selector("login-submit")).click()
    ready.until(
        expected_conditions.element_to_be_clickable(
            selector("home-start-link")
        )
    ).click()
    ready.until(
        expected_conditions.element_to_be_clickable(
            selector("start-tier-beginner-button")
        )
    ).click()

    ready.until(expected_conditions.url_matches(r"/play/\d+$"))
    stage = ready.until(
        expected_conditions.visibility_of_element_located(
            selector("play-stage")
        )
    )
    assert stage.text == "Stage 1"
    assert browser.find_element(*selector("play-lives")).text == "4"

    browser.get(f"{live_server}/start")
    ready.until(
        expected_conditions.visibility_of_element_located(
            selector("start-resume-run")
        )
    )
    for width, height, needs_scroll in ((1280, 640, False), (390, 560, True)):
        browser.execute_cdp_cmd(
            "Emulation.setDeviceMetricsOverride",
            {
                "width": width,
                "height": height,
                "deviceScaleFactor": 1,
                "mobile": False,
            },
        )
        horizontal, vertical = browser.execute_script(
            "const page = document.scrollingElement;"
            "return [page.scrollWidth - page.clientWidth,"
            "page.scrollHeight - page.clientHeight];"
        )
        assert horizontal == 0
        assert (vertical > 0) == needs_scroll, (width, height, vertical)

    last_tier = browser.find_element(*selector("start-tier-impossible"))
    scroll, top, bottom, viewport_height = browser.execute_script(
        "window.scrollTo(0, document.scrollingElement.scrollHeight);"
        "const {top, bottom} = arguments[0].getBoundingClientRect();"
        "return [window.scrollY, top, bottom, window.innerHeight];",
        last_tier,
    )
    assert scroll > 0
    assert 0 <= top < bottom <= viewport_height
