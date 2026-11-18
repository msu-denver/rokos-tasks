"""
File: test_app.py
Description: Unit tests for the Flask application factory and the
    placeholder routes.
Author(s): Tyler Black
"""

from flask import Flask
from flask.testing import FlaskClient

from src.app import create_app, load_user


def test_create_app_uses_defaults_without_overrides():
    app = create_app()

    assert app.testing is False
    assert "main" in app.blueprints
    assert "auth" in app.blueprints
    assert "game" in app.blueprints
    assert app.config["SESSION_COOKIE_HTTPONLY"] is True
    assert app.config["SESSION_COOKIE_SAMESITE"] == "Lax"


def test_login_manager_configuration():
    from src.app import login_manager

    assert login_manager.login_view == "auth.login"
    assert login_manager.login_message == "Please log in to continue."


def test_create_app_applies_config_overrides():
    app = create_app({"TESTING": True, "SECRET_KEY": "test-key"})

    assert app.testing is True
    assert app.config["SECRET_KEY"] == "test-key"


def test_load_user_with_invalid_id_returns_none(app: Flask):
    with app.app_context():
        assert load_user("invalid-id") is None


def test_load_user_with_missing_id_returns_none(app: Flask):
    with app.app_context():
        assert load_user("999999") is None


def test_home_page_renders_title(client: FlaskClient):
    response = client.get("/")

    assert response.status_code == 200
    assert b'data-testid="app-title"' in response.data


def test_health_reports_ok(client: FlaskClient):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}
