"""
File: game_routes.py
Description: Game blueprint providing player interaction and campaign routes.
Author(s): Tyler Black
"""

from flask import Blueprint, render_template
from flask_login import login_required

game_blueprint = Blueprint("game", __name__)


@game_blueprint.get("/start")
@login_required
def start() -> str:
    """Render the game campaign start screen for authenticated players.

    Returns:
        Rendered start screen HTML.
    """
    return render_template("game/start.html")
