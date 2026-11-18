"""
File: test_login_logout.py
Description: End-to-end Selenium browser tests for player login, session
    persistence, header logout, and protected route redirection.
Author(s): Tyler Black
"""

import pytest
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions
from selenium.webdriver.support.ui import WebDriverWait


@pytest.mark.e2e
def test_login_logout_and_protected_page_flow(
    browser: webdriver.Chrome, live_server: str
) -> None:
    """Verify player can log in, log out, and get redirected."""
    browser.get(f"{live_server}/register")
    reg_user_input = WebDriverWait(browser, 10).until(
        expected_conditions.visibility_of_element_located(
            (By.CSS_SELECTOR, '[data-testid="register-username"]')
        )
    )
    reg_user_input.send_keys("StellarPilot")
    browser.find_element(
        By.CSS_SELECTOR, '[data-testid="register-password"]'
    ).send_keys("stellar_pass_99")
    browser.find_element(
        By.CSS_SELECTOR, '[data-testid="register-confirm"]'
    ).send_keys("stellar_pass_99")
    browser.find_element(
        By.CSS_SELECTOR, '[data-testid="register-submit"]'
    ).click()

    WebDriverWait(browser, 10).until(
        expected_conditions.visibility_of_element_located(
            (By.CSS_SELECTOR, '[data-testid="home-username"]')
        )
    )

    logout_button = WebDriverWait(browser, 10).until(
        expected_conditions.element_to_be_clickable(
            (By.CSS_SELECTOR, '[data-testid="header-logout"]')
        )
    )
    logout_button.click()

    WebDriverWait(browser, 10).until(
        expected_conditions.visibility_of_element_located(
            (By.CSS_SELECTOR, '[data-testid="login-username"]')
        )
    )
    flash_msg = WebDriverWait(browser, 10).until(
        expected_conditions.visibility_of_element_located(
            (By.CSS_SELECTOR, '[data-testid="flash-message"]')
        )
    )
    assert flash_msg.text == "You've been logged out."

    login_user_input = browser.find_element(
        By.CSS_SELECTOR, '[data-testid="login-username"]'
    )
    login_user_input.send_keys("stellarpilot")
    browser.find_element(
        By.CSS_SELECTOR, '[data-testid="login-password"]'
    ).send_keys("stellar_pass_99")
    browser.find_element(
        By.CSS_SELECTOR, '[data-testid="login-submit"]'
    ).click()

    home_user = WebDriverWait(browser, 10).until(
        expected_conditions.visibility_of_element_located(
            (By.CSS_SELECTOR, '[data-testid="home-username"]')
        )
    )
    assert home_user.text == "StellarPilot"

    header_user = WebDriverWait(browser, 10).until(
        expected_conditions.visibility_of_element_located(
            (By.CSS_SELECTOR, '[data-testid="header-username"]')
        )
    )
    assert header_user.text == "StellarPilot"

    header_logout = browser.find_element(
        By.CSS_SELECTOR, '[data-testid="header-logout"]'
    )
    header_logout.click()

    WebDriverWait(browser, 10).until(
        expected_conditions.visibility_of_element_located(
            (By.CSS_SELECTOR, '[data-testid="login-username"]')
        )
    )

    browser.get(f"{live_server}/start")

    WebDriverWait(browser, 10).until(
        expected_conditions.visibility_of_element_located(
            (By.CSS_SELECTOR, '[data-testid="login-username"]')
        )
    )
    assert "/login" in browser.current_url

    login_flash = WebDriverWait(browser, 10).until(
        expected_conditions.visibility_of_element_located(
            (By.CSS_SELECTOR, '[data-testid="flash-message"]')
        )
    )
    assert login_flash.text == "Please log in to continue."


@pytest.mark.e2e
def test_login_invalid_credentials_shows_error(
    browser: webdriver.Chrome, live_server: str
) -> None:
    """Verify invalid credentials display error message on login form."""
    browser.get(f"{live_server}/login")

    username_input = WebDriverWait(browser, 10).until(
        expected_conditions.visibility_of_element_located(
            (By.CSS_SELECTOR, '[data-testid="login-username"]')
        )
    )
    username_input.send_keys("NonExistentPlayer")
    browser.find_element(
        By.CSS_SELECTOR, '[data-testid="login-password"]'
    ).send_keys("wrong_password")
    browser.find_element(
        By.CSS_SELECTOR, '[data-testid="login-submit"]'
    ).click()

    error_elem = WebDriverWait(browser, 10).until(
        expected_conditions.visibility_of_element_located(
            (By.CSS_SELECTOR, '[data-testid="login-error"]')
        )
    )
    assert error_elem.text == "Invalid username or password."
