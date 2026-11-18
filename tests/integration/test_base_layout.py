"""
File: test_base_layout.py
Description: Integration tests for the base HTML layout, verifying token
    stylesheet inclusion order, header wordmark, and flash message rendering.
Author(s): Tyler Black
"""

import flask
from flask import Flask
from flask.testing import FlaskClient


def test_home_page_renders_base_layout(client: FlaskClient) -> None:
    """Verify that home page loads base layout with styles and wordmark."""
    response = client.get("/")

    assert response.status_code == 200
    html = response.get_data(as_text=True)

    tokens_index = html.find("tokens.css")
    components_index = html.find("components.css")
    assert tokens_index != -1, "tokens.css link missing from HTML head"
    assert components_index != -1, "components.css link missing from HTML head"
    assert tokens_index < components_index, (
        "tokens.css must be linked before components.css"
    )

    assert 'data-testid="header-wordmark"' in html
    assert 'href="/"' in html
    assert 'data-testid="app-title"' in html
    assert 'data-testid="app-status"' in html


def test_flashed_message_renders_with_request_context(app: Flask) -> None:
    """Verify flashed messages render with flash-message testid in template."""
    app.config["SECRET_KEY"] = "test-secret-key"

    with app.test_request_context("/"):
        flask.flash("Deprecation warning logged.")
        html = flask.render_template("base.html")

    assert 'data-testid="flash-message"' in html
    assert "Deprecation warning logged." in html


def test_flashed_message_renders_through_route(
    app: Flask, client: FlaskClient
) -> None:
    """Verify flashed messages render through an application route."""
    app.config["SECRET_KEY"] = "test-secret-key"

    @app.get("/_test/flash-demo")
    def flash_demo_route() -> str:
        flask.flash("Overlord instructions updated.")
        return flask.render_template("index.html")

    response = client.get("/_test/flash-demo")
    assert response.status_code == 200
    html = response.get_data(as_text=True)

    assert 'data-testid="flash-message"' in html
    assert "Overlord instructions updated." in html


def test_base_layout_header_actions_logged_out(client: FlaskClient) -> None:
    """Verify logged-out visitor sees login and register links in header."""
    response = client.get("/")
    assert response.status_code == 200
    html = response.get_data(as_text=True)

    assert 'data-testid="header-login"' in html
    assert 'data-testid="header-register"' in html
    assert 'data-testid="header-logout"' not in html
    assert 'data-testid="header-username"' not in html


def test_base_layout_header_actions_logged_in(client: FlaskClient) -> None:
    """Verify logged-in visitor sees username and logout button in header."""
    client.post(
        "/register",
        data={
            "username": "HeaderCheckUser",
            "password": "password123",
            "confirm": "password123",
        },
    )

    response = client.get("/")
    assert response.status_code == 200
    html = response.get_data(as_text=True)

    assert 'data-testid="header-username"' in html
    assert "HeaderCheckUser" in html
    assert 'data-testid="header-logout"' in html
    assert 'data-testid="header-login"' not in html
    assert 'data-testid="header-register"' not in html
