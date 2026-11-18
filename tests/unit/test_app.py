"""
File: test_app.py
Description: Unit tests for the Flask application factory and the
    placeholder routes.
Author(s): Tyler Black
"""

from flask.testing import FlaskClient

from src.app import create_app


def test_create_app_uses_defaults_without_overrides():
    app = create_app()

    assert app.testing is False
    assert "main" in app.blueprints


def test_create_app_applies_config_overrides():
    app = create_app({"TESTING": True, "SECRET_KEY": "test-key"})

    assert app.testing is True
    assert app.config["SECRET_KEY"] == "test-key"


def test_home_page_renders_title(client: FlaskClient):
    response = client.get("/")

    assert response.status_code == 200
    assert b'data-testid="app-title"' in response.data


def test_health_reports_ok(client: FlaskClient):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}
