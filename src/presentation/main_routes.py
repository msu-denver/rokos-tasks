"""
File: main_routes.py
Description: Routes that aren't part of a feature: the placeholder home
    page and a health check for Docker and CI.
Author(s): Tyler Black
"""

from flask import Blueprint, render_template

main_blueprint = Blueprint("main", __name__)


@main_blueprint.get("/")
def home() -> str:
    """Render the placeholder home page.

    Returns:
        The rendered home page HTML.
    """
    return render_template("index.html")


@main_blueprint.get("/health")
def health() -> dict[str, str]:
    """Report that the web app is up.

    Returns:
        A JSON body ``{"status": "ok"}``.
    """
    return {"status": "ok"}
