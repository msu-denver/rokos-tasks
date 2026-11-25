"""
File: test_home_page.py
Description: Selenium smoke test: the placeholder home page loads in a
    real browser. Proves the e2e setup works locally and in CI.
Author(s): Tyler Black
"""

import pytest
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions
from selenium.webdriver.support.ui import WebDriverWait


@pytest.mark.e2e
def test_home_page_shows_title(browser: webdriver.Chrome, live_server: str):
    browser.get(live_server)

    title = WebDriverWait(browser, 10).until(
        expected_conditions.visibility_of_element_located(
            (By.CSS_SELECTOR, '[data-testid="app-title"]')
        )
    )

    assert title.text == "Roko's Tasks"
    assert browser.title == "Roko's Tasks"
