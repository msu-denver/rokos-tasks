"""
File: test_auth_routes.py
Description: Integration tests for authentication routes covering registration
    flow, validation errors, session login, and CSRF enforcement.
Author(s): Tyler Black
"""

from flask import Flask
from flask.testing import FlaskClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.data.models.user import User
from src.data.repositories.user_repository import UserRepository


def test_get_register_renders_form_fields(client: FlaskClient) -> None:
    """Verify registration page renders form elements and login link."""
    response = client.get("/register")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'data-testid="register-username"' in html
    assert 'data-testid="register-password"' in html
    assert 'data-testid="register-confirm"' in html
    assert 'data-testid="register-submit"' in html
    assert 'data-testid="register-login-link"' in html
    assert 'href="/login"' in html


def test_post_register_valid_creates_user_and_logs_in(
    client: FlaskClient, db_session: Session
) -> None:
    """Verify valid submission redirects to home and logs player in."""
    response = client.post(
        "/register",
        data={
            "username": "RocketPlayer",
            "password": "valid_password_1",
            "confirm": "valid_password_1",
        },
    )

    assert response.status_code == 302
    assert response.headers["Location"] == "/"

    repo = UserRepository(db_session)
    user = repo.get_by_username("rocketplayer")
    assert user is not None
    assert user.username == "RocketPlayer"

    follow_response = client.get("/")
    assert follow_response.status_code == 200
    home_html = follow_response.get_data(as_text=True)
    assert 'data-testid="home-username"' in home_html
    assert "RocketPlayer" in home_html


def test_post_register_taken_username_returns_form_with_error(
    client: FlaskClient, db_session: Session
) -> None:
    """Verify duplicate username returns 200 and keeps user count unchanged."""
    repo = UserRepository(db_session)
    repo.add(User(username="ExistingPlayer", password_hash="dummy_hash"))
    db_session.commit()
    initial_count = db_session.scalar(select(func.count(User.id)))

    response = client.post(
        "/register",
        data={
            "username": "existingplayer",
            "password": "password123",
            "confirm": "password123",
        },
    )

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'data-testid="register-error"' in html
    assert "That username is taken." in html
    assert 'value="existingplayer"' in html

    current_count = db_session.scalar(select(func.count(User.id)))
    assert current_count == initial_count


def test_post_register_invalid_input_clears_passwords(
    client: FlaskClient,
) -> None:
    """Verify validation errors re-render form with cleared password fields."""
    response = client.post(
        "/register",
        data={
            "username": "valid_user",
            "password": "short",
            "confirm": "mismatch",
        },
    )

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'data-testid="register-error"' in html
    assert "Password must be at least 8 characters." in html
    assert 'value="short"' not in html
    assert 'value="mismatch"' not in html
    assert 'value="valid_user"' in html


def test_post_register_rejected_without_csrf_token(app: Flask) -> None:
    """Verify POST without CSRF token returns 400 when CSRF is enabled."""
    app.config["WTF_CSRF_ENABLED"] = True
    client = app.test_client()

    response = client.post(
        "/register",
        data={
            "username": "unprotected_user",
            "password": "password123",
            "confirm": "password123",
        },
    )

    assert response.status_code == 400


def test_logged_in_user_visiting_register_redirects_to_home(
    client: FlaskClient,
) -> None:
    """Verify authenticated user visiting /register is redirected to home."""
    client.post(
        "/register",
        data={
            "username": "LoggedInUser",
            "password": "password123",
            "confirm": "password123",
        },
    )

    response = client.get("/register")
    assert response.status_code == 302
    assert response.headers["Location"] == "/"
