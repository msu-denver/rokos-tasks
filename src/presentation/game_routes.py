"""
File: game_routes.py
Description: Game blueprint providing player interaction and campaign routes.
Author(s): Tyler Black
"""

from flask import Blueprint, abort, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from werkzeug.wrappers import Response

from src.business.campaign_selector import NoCampaignAvailableError
from src.business.difficulty import Difficulty
from src.business.game_service import GameService, RunNotFoundError
from src.business.service_factory import build_game_service

game_blueprint = Blueprint("game", __name__)


def _render_start(game: GameService, error: str | None = None) -> str:
    return render_template(
        "game/start.html",
        tiers=game.tier_overview(),
        error=error,
    )


@game_blueprint.get("/start")
@login_required
def start() -> str:
    """Show difficulty tiers and their campaign availability."""
    return _render_start(build_game_service())


@game_blueprint.post("/runs")
@login_required
def create_run() -> Response | str:
    """Start a run at the requested difficulty and open its play page."""
    try:
        difficulty = Difficulty(request.form.get("difficulty"))
    except ValueError:
        abort(400)

    game = build_game_service()
    try:
        run = game.start_run(current_user.id, difficulty)
    except NoCampaignAvailableError:
        return _render_start(game, "No campaigns for this tier yet.")
    return redirect(url_for("game.play", run_id=run.id))


@game_blueprint.get("/play/<int:run_id>")
@login_required
def play(run_id: int) -> str:
    """Show the current stage and lives for one of the player's runs."""
    try:
        stage = build_game_service().get_stage_view(current_user.id, run_id)
    except RunNotFoundError:
        abort(404)
    return render_template("game/play.html", stage=stage, run_id=run_id)
