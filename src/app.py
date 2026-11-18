"""
File: app.py
Description: Flask application factory. Builds the app and registers the
    presentation-layer blueprints.
Author(s): Tyler Black
"""

from typing import Any

from flask import Flask

from src.presentation.main_routes import main_blueprint


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
    app.register_blueprint(main_blueprint)
    return app
