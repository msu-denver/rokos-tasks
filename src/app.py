"""
File: app.py
Description: Flask application factory. Builds the app and registers the
    presentation-layer blueprints.
Author(s): Tyler Black, Richard Hall
"""

import os
from typing import Any

from flask import Flask
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect

from src.business.service_factory import build_auth_service
from src.data.database import db
from src.presentation.auth_routes import auth_blueprint
from src.presentation.game_routes import game_blueprint
from src.presentation.main_routes import main_blueprint

DEFAULT_DATABASE_URL = (
    "postgresql+psycopg://rokos:rokos@localhost:5433/rokos_tasks"
)
MAX_REQUEST_BYTES = 1024 * 1024
# The runner is only reachable from inside the Compose network.
DEFAULT_RUNNER_URL = "http://runner:9000"

csrf = CSRFProtect()
login_manager = LoginManager()
login_manager.login_view = "auth.login"
login_manager.login_message = "Please log in to continue."


@login_manager.user_loader
def load_user(user_id: str) -> Any:
    """Load user by identifier for Flask-Login.

    Args:
        user_id: String user ID from the session cookie.

    Returns:
        The loaded User entity, or None if not found or invalid.
    """
    try:
        ident = int(user_id)
    except (ValueError, TypeError):
        return None
    auth_service = build_auth_service()
    return auth_service.get_user(ident)


def create_app(config_overrides: dict[str, Any] | None = None) -> Flask:
    """Create and configure the Flask application.

    Args:
        config_overrides: Settings that replace the defaults, used by
            tests (for example ``{"TESTING": True}``).

    Returns:
        The configured Flask app.
    """
    app = Flask(
        __name__,
        template_folder="presentation/templates",
        static_folder="presentation/static",
    )
    app.config["SECRET_KEY"] = os.getenv(
        "SECRET_KEY", "dev-secret-key-change-in-production"
    )
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    # The largest request is a Submit: 64 KB of code, JSON-escaped.
    app.config["MAX_CONTENT_LENGTH"] = MAX_REQUEST_BYTES

    if config_overrides:
        app.config.update(config_overrides)

    if "WTF_CSRF_ENABLED" not in app.config:
        app.config["WTF_CSRF_ENABLED"] = not app.config.get("TESTING", False)

    app.config.setdefault(
        "RUNNER_URL", os.getenv("RUNNER_URL", DEFAULT_RUNNER_URL)
    )

    database_url = app.config.get(
        "DATABASE_URL",
        os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL),
    )
    db.init(database_url)

    csrf.init_app(app)
    login_manager.init_app(app)

    @app.teardown_appcontext
    def teardown_database_session(
        exception: BaseException | None = None,
    ) -> None:
        """Remove scoped session at the end of each request."""
        db.remove()

    app.register_blueprint(main_blueprint)
    app.register_blueprint(auth_blueprint)
    app.register_blueprint(game_blueprint)
    return app


def create_dev_app() -> Flask:
    """Build the local preview with a separate browser session cookie."""
    return create_app({"SESSION_COOKIE_NAME": "rokos_dev_session"})
