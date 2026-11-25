"""
File: support.py
Description: Shared Selenium helpers for the game page: data-testid
    selectors, registering and starting a run, and typing into Monaco.
Author(s): Richard Hall, Tyler Black
"""

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions
from selenium.webdriver.support.ui import WebDriverWait
from sqlalchemy.orm import Session

from src.business.auth_service import AuthService
from src.data.repositories.user_repository import UserRepository

PASSWORD = "password123"


def selector(test_id: str) -> tuple[str, str]:
    """Return a Selenium locator for a ``data-testid`` attribute.

    Args:
        test_id: The element's ``data-testid`` value.

    Returns:
        A ``(By, value)`` locator.
    """
    return By.CSS_SELECTOR, f'[data-testid="{test_id}"]'


def start_run(
    browser: webdriver.Chrome,
    live_server: str,
    db_session: Session,
    tier: str,
    username: str = "Submitter",
) -> WebDriverWait:
    """Register a player, log in, and start a run on ``tier``.

    Args:
        browser: The Selenium driver.
        live_server: The live server's base URL.
        db_session: The test session, used to register the player.
        tier: The difficulty to start, such as ``"medium"``.
        username: The player to register and log in as.

    Returns:
        A ``WebDriverWait`` for the play page, which is now loaded.
    """
    AuthService(UserRepository(db_session)).register(
        username, PASSWORD, PASSWORD
    )
    browser.get(f"{live_server}/login")
    ready = WebDriverWait(browser, 15)
    ready.until(
        expected_conditions.visibility_of_element_located(
            selector("login-username")
        )
    ).send_keys(username)
    browser.find_element(*selector("login-password")).send_keys(PASSWORD)
    browser.find_element(*selector("login-submit")).click()
    ready.until(
        expected_conditions.element_to_be_clickable(
            selector("home-start-link")
        )
    ).click()
    ready.until(
        expected_conditions.element_to_be_clickable(
            selector(f"start-tier-{tier}-button")
        )
    ).click()
    ready.until(expected_conditions.url_matches(r"/play/\d+$"))
    return ready


def write_code(
    browser: webdriver.Chrome, ready: WebDriverWait, code: str
) -> None:
    """Put ``code`` in the Monaco editor, the way a paste would.

    Args:
        browser: The Selenium driver.
        ready: A wait used until Monaco has loaded.
        code: The program text.
    """
    ready.until(
        lambda driver: driver.execute_script(
            "return !!window.monaco && monaco.editor.getEditors().length > 0"
        )
    )
    browser.execute_script(
        "monaco.editor.getEditors()[0].setValue(arguments[0])", code
    )
