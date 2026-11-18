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
    """Log in, select Beginner, and see Stage 1 with four lives."""
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
