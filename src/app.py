"""
File: app.py
Description: Flask application factory. Builds the app and registers the
    presentation-layer blueprints.
Author(s): Tyler Black
"""

import os
from typing import Any

from flask import Flask

from src.data.database import db
from src.presentation.main_routes import main_blueprint

DEFAULT_DATABASE_URL = (
    "postgresql+psycopg://rokos:rokos@localhost:5433/rokos_tasks"
)


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
    if config_overrides:
        app.config.update(config_overrides)

    database_url = app.config.get(
        "DATABASE_URL",
        os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL),
    )
    db.init(database_url)

    @app.teardown_appcontext
    def teardown_database_session(
        exception: BaseException | None = None,
    ) -> None:
        """Remove scoped session at the end of each request."""
        db.remove()

    app.register_blueprint(main_blueprint)
    return app
