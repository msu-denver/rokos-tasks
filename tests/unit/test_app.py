"""
File: test_app.py
Description: Unit tests for the Flask application factory and the
    placeholder routes.
Author(s): Tyler Black
"""

import json
import re
from pathlib import Path

import pytest
from flask import Flask
from flask.cli import ScriptInfo
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


def test_preview_keeps_web_login_form_valid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Preserve both CSRF sessions when opening both apps on one host."""
    launch_path = Path(__file__).resolve().parents[2] / ".claude/launch.json"
    launch = json.loads(launch_path.read_text(encoding="utf-8"))
    preview = launch["configurations"][0]
    arguments = preview["runtimeArgs"]
    preview_import = arguments[arguments.index("--app") + 1]

    web_app = create_app({"SECRET_KEY": "test-docker-key"})
    monkeypatch.setenv("SECRET_KEY", "test-preview-key")
    preview_app = ScriptInfo(app_import_path=preview_import).load_app()
    browser = web_app.test_client()
    apps = [
        (web_app, "http://localhost:8000"),
        (preview_app, f"http://localhost:{preview['port']}"),
    ]
    tokens = []
    for application, url in apps:
        browser.application = application
        page = browser.get("/login", base_url=url)
        token = re.search(
            r'name="csrf_token" type="hidden" value="([^"]+)"',
            page.get_data(as_text=True),
        )
        assert token is not None
        tokens.append(token[1])

    for (application, url), token in zip(apps, tokens, strict=True):
        browser.application = application
        response = browser.post(
            "/login", base_url=url, data={"csrf_token": token}
        )
        assert response.status_code == 200, response.get_data(as_text=True)
        assert b"Invalid username or password." in response.data

    assert preview["port"] != 8000
    assert arguments[arguments.index("--port") + 1] == str(preview["port"])


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
