"""
File: test_register.py
Description: End-to-end Selenium browser tests for player registration and
    error messaging.
Author(s): Tyler Black
"""

import pytest
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions
from selenium.webdriver.support.ui import WebDriverWait


@pytest.mark.e2e
def test_register_success_navigates_to_home_with_username(
    browser: webdriver.Chrome, live_server: str
) -> None:
    """Verify player can register and see their username on the home page."""
    browser.get(f"{live_server}/register")

    user_input = WebDriverWait(browser, 10).until(
        expected_conditions.visibility_of_element_located(
            (By.CSS_SELECTOR, '[data-testid="register-username"]')
        )
    )
    user_input.send_keys("NewAstronaut")
    browser.find_element(
        By.CSS_SELECTOR, '[data-testid="register-password"]'
    ).send_keys("topsecret99")
    browser.find_element(
        By.CSS_SELECTOR, '[data-testid="register-confirm"]'
    ).send_keys("topsecret99")
    browser.find_element(
        By.CSS_SELECTOR, '[data-testid="register-submit"]'
    ).click()

    username_elem = WebDriverWait(browser, 10).until(
        expected_conditions.visibility_of_element_located(
            (By.CSS_SELECTOR, '[data-testid="home-username"]')
        )
    )
    assert username_elem.text == "NewAstronaut"


@pytest.mark.e2e
def test_register_duplicate_username_shows_error(
    browser: webdriver.Chrome, live_server: str
) -> None:
    """Verify submitting taken username displays error message."""
    browser.get(f"{live_server}/register")
    user_input = WebDriverWait(browser, 10).until(
        expected_conditions.visibility_of_element_located(
            (By.CSS_SELECTOR, '[data-testid="register-username"]')
        )
    )
    user_input.send_keys("PlayerDuplicate")
    browser.find_element(
        By.CSS_SELECTOR, '[data-testid="register-password"]'
    ).send_keys("password123")
    browser.find_element(
        By.CSS_SELECTOR, '[data-testid="register-confirm"]'
    ).send_keys("password123")
    browser.find_element(
        By.CSS_SELECTOR, '[data-testid="register-submit"]'
    ).click()

    WebDriverWait(browser, 10).until(
        expected_conditions.visibility_of_element_located(
            (By.CSS_SELECTOR, '[data-testid="home-username"]')
        )
    )

    browser.delete_all_cookies()

    browser.get(f"{live_server}/register")
    user_input_retry = WebDriverWait(browser, 10).until(
        expected_conditions.visibility_of_element_located(
            (By.CSS_SELECTOR, '[data-testid="register-username"]')
        )
    )
    user_input_retry.send_keys("playerduplicate")
    browser.find_element(
        By.CSS_SELECTOR, '[data-testid="register-password"]'
    ).send_keys("password123")
    browser.find_element(
        By.CSS_SELECTOR, '[data-testid="register-confirm"]'
    ).send_keys("password123")
    browser.find_element(
        By.CSS_SELECTOR, '[data-testid="register-submit"]'
    ).click()

    error_elem = WebDriverWait(browser, 10).until(
        expected_conditions.visibility_of_element_located(
            (By.CSS_SELECTOR, '[data-testid="register-error"]')
        )
    )
    assert error_elem.text == "That username is taken."
