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


def test_post_logout_rejected_without_csrf_token(app: Flask) -> None:
    """Verify POST /logout without CSRF token returns 400 when CSRF is on."""
    app.config["WTF_CSRF_ENABLED"] = True
    client = app.test_client()

    response = client.post("/logout")
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


def test_get_login_renders_form_fields(client: FlaskClient) -> None:
    """Verify login page renders form elements and register link."""
    response = client.get("/login")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'data-testid="login-username"' in html
    assert 'data-testid="login-password"' in html
    assert 'data-testid="login-submit"' in html
    assert 'data-testid="login-register-link"' in html
    assert "New here? Create an account" in html
    assert 'href="/register"' in html


def test_post_login_valid_credentials_redirects_home(
    client: FlaskClient, db_session: Session
) -> None:
    """Verify valid login redirects to home and establishes session."""
    from werkzeug.security import generate_password_hash

    repo = UserRepository(db_session)
    repo.add(
        User(
            username="FlightPilot",
            password_hash=generate_password_hash("pilot_pass_123"),
        )
    )
    db_session.commit()

    response = client.post(
        "/login",
        data={
            "username": "flightpilot",
            "password": "pilot_pass_123",
        },
    )

    assert response.status_code == 302
    assert response.headers["Location"] == "/"

    home_response = client.get("/")
    assert home_response.status_code == 200
    home_html = home_response.get_data(as_text=True)
    assert 'data-testid="home-username"' in home_html
    assert "FlightPilot" in home_html
    assert 'data-testid="header-username"' in home_html
    assert 'data-testid="header-logout"' in home_html


def test_post_login_failures_render_identical_message(
    client: FlaskClient, db_session: Session
) -> None:
    """Verify wrong username and wrong password render identical bodies."""
    from werkzeug.security import generate_password_hash

    response_unknown = client.post(
        "/login",
        data={
            "username": "IdenticalTarget",
            "password": "wrong_password_999",
        },
    )

    repo = UserRepository(db_session)
    repo.add(
        User(
            username="IdenticalTarget",
            password_hash=generate_password_hash("correct_password_123"),
        )
    )
    db_session.commit()

    response_wrong_pw = client.post(
        "/login",
        data={
            "username": "IdenticalTarget",
            "password": "wrong_password_999",
        },
    )

    assert response_unknown.status_code == 200
    assert response_wrong_pw.status_code == 200
    assert response_unknown.get_data(
        as_text=True
    ) == response_wrong_pw.get_data(as_text=True)

    html = response_unknown.get_data(as_text=True)
    assert 'data-testid="login-error"' in html
    assert "Invalid username or password." in html

    home_response = client.get("/")
    assert 'data-testid="home-username"' not in home_response.get_data(
        as_text=True
    )


def test_post_login_with_safe_next_redirects_to_target(
    client: FlaskClient, db_session: Session
) -> None:
    """Verify login with safe next parameter redirects to requested page."""
    from werkzeug.security import generate_password_hash

    repo = UserRepository(db_session)
    repo.add(
        User(
            username="StartSeeker",
            password_hash=generate_password_hash("pass12345"),
        )
    )
    db_session.commit()

    response = client.post(
        "/login?next=/start",
        data={
            "username": "StartSeeker",
            "password": "pass12345",
        },
    )

    assert response.status_code == 302
    assert response.headers["Location"] == "/start"


def test_post_login_with_unsafe_next_falls_back_to_home(
    client: FlaskClient, db_session: Session
) -> None:
    """Verify login with open redirect attempts falls back to home page."""
    from werkzeug.security import generate_password_hash

    repo = UserRepository(db_session)
    repo.add(
        User(
            username="SafeSurfer",
            password_hash=generate_password_hash("pass12345"),
        )
    )
    db_session.commit()

    response = client.post(
        "/login?next=https://evil.com",
        data={
            "username": "SafeSurfer",
            "password": "pass12345",
        },
    )

    assert response.status_code == 302
    assert response.headers["Location"] == "/"


def test_logged_in_user_visiting_login_redirects_to_home(
    client: FlaskClient, db_session: Session
) -> None:
    """Verify authenticated user visiting /login is redirected to home."""
    from werkzeug.security import generate_password_hash

    repo = UserRepository(db_session)
    repo.add(
        User(
            username="AlreadyIn",
            password_hash=generate_password_hash("pass12345"),
        )
    )
    db_session.commit()

    client.post(
        "/login",
        data={"username": "AlreadyIn", "password": "pass12345"},
    )

    response = client.get("/login")
    assert response.status_code == 302
    assert response.headers["Location"] == "/"


def test_get_logout_returns_method_not_allowed(client: FlaskClient) -> None:
    """Verify GET /logout returns 405 Method Not Allowed."""
    response = client.get("/logout")
    assert response.status_code == 405


def test_post_logout_clears_session_and_protects_routes(
    client: FlaskClient, db_session: Session
) -> None:
    """Verify logout terminates session and protected pages redirect."""
    from werkzeug.security import generate_password_hash

    repo = UserRepository(db_session)
    repo.add(
        User(
            username="LogMeOut",
            password_hash=generate_password_hash("pass12345"),
        )
    )
    db_session.commit()

    client.post(
        "/login",
        data={"username": "LogMeOut", "password": "pass12345"},
    )

    start_resp = client.get("/start")
    assert start_resp.status_code == 200
    assert 'data-testid="start-title"' in start_resp.get_data(as_text=True)

    logout_resp = client.post("/logout")
    assert logout_resp.status_code == 302
    assert logout_resp.headers["Location"] == "/login"

    follow_login = client.get("/login")
    content = follow_login.get_data(as_text=True)
    assert "You&#39;ve been logged out." in content or (
        "You've been logged out." in content
    )

    after_logout_start = client.get("/start")
    assert after_logout_start.status_code == 302
    assert "/login" in after_logout_start.headers["Location"]


def test_unauthenticated_get_start_redirects_to_login(
    client: FlaskClient,
) -> None:
    """Verify unauthenticated access to /start redirects to login."""
    response = client.get("/start")
    assert response.status_code == 302
    assert "/login?next=" in response.headers["Location"]

    follow_resp = client.get(response.headers["Location"])
    assert follow_resp.status_code == 200
    html = follow_resp.get_data(as_text=True)
    assert 'data-testid="flash-message"' in html
    assert "Please log in to continue." in html
