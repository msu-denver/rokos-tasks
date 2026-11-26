"""
File: game_routes.py
Description: Game blueprint providing player interaction and campaign routes.
Author(s): Tyler Black, Richard Hall
"""

import logging
from http import HTTPStatus

from flask import (
    Blueprint,
    abort,
    current_app,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required
from werkzeug.wrappers import Response

from src.business.campaign_selector import NoCampaignAvailableError
from src.business.difficulty import Difficulty
from src.business.game_service import (
    ActiveRunExistsError,
    GameService,
    RunNotFoundError,
    StaleSubmitError,
)
from src.business.grading_service import (
    InvalidCodeError,
    RunFinishedError,
    StageNotGradableError,
)
from src.business.runner_client import (
    CheckScriptBrokenError,
    RunnerUnavailableError,
)
from src.business.service_factory import build_game_service

game_blueprint = Blueprint("game", __name__)
logger = logging.getLogger(__name__)

# Placeholder wording until the PO decides; US10 moves it to dialogue.
UNAVAILABLE = "Grading is unavailable. This submit didn't count."
STALE = "This page is out of date."


def _render_start(game: GameService, error: str | None = None) -> str:
    run = game.active_run(current_user.id)
    return render_template(
        "game/start.html",
        tiers=game.tier_overview(),
        resume_run_id=run.id if run is not None else None,
        error=error,
    )


@game_blueprint.get("/start")
@login_required
def start() -> str:
    """Show the difficulty tiers and any run the player can resume."""
    return _render_start(build_game_service())


@game_blueprint.post("/runs")
@login_required
def create_run() -> Response | str:
    """Start a run at the requested difficulty and open its play page."""
    try:
        difficulty = Difficulty(request.form.get("difficulty"))
    except ValueError:
        abort(400)

    replace_active = request.form.get("replace_active") == "yes"
    expected_active_id = request.form.get("active_run_id", type=int)
    if "active_run_id" in request.form and expected_active_id is None:
        abort(400)

    game = build_game_service()
    try:
        run = game.start_run(
            current_user.id,
            difficulty,
            replace_active=replace_active,
            expected_active_id=expected_active_id,
        )
    except ActiveRunExistsError as error:
        return render_template(
            "game/start.html",
            active_run_id=error.run_id,
            replacement_difficulty=difficulty,
        )
    except NoCampaignAvailableError:
        return _render_start(game, "No campaigns for this tier yet.")
    return redirect(url_for("game.play", run_id=run.id))


@game_blueprint.get("/play/<int:run_id>")
@login_required
def play(run_id: int) -> str:
    """Show the current stage or the result of the player's run."""
    game = build_game_service()
    try:
        stage = game.get_stage_view(current_user.id, run_id)
        if stage is None:
            result = game.get_result_view(current_user.id, run_id)
            return render_template(
                "game/play.html", stage=None, result=result, run_id=run_id
            )
    except RunNotFoundError:
        abort(404)
    return render_template("game/play.html", stage=stage, run_id=run_id)


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _message(status: HTTPStatus, message: str) -> tuple[Response, int]:
    return jsonify(message=message), status


@game_blueprint.post("/game/submit")
@login_required
def submit() -> tuple[Response, int]:
    """Grade the editor's code and apply the verdict to the run."""
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        abort(400)
    run_id, stage = payload.get("run_id"), payload.get("stage")
    code = payload.get("code")
    if not (_is_int(run_id) and _is_int(stage) and isinstance(code, str)):
        abort(400)

    game = build_game_service(current_app.config["RUNNER_URL"])
    try:
        result = game.submit_stage(current_user.id, run_id, code, stage)
    except RunNotFoundError:
        abort(404)
    except RunFinishedError:
        abort(409)
    except InvalidCodeError:
        abort(400)
    except StaleSubmitError:
        return _message(HTTPStatus.CONFLICT, STALE)
    except (
        RunnerUnavailableError,
        CheckScriptBrokenError,
        StageNotGradableError,
    ):
        logger.exception("grading failed for run %s", run_id)
        return _message(HTTPStatus.SERVICE_UNAVAILABLE, UNAVAILABLE)
    return jsonify(result.to_dict()), HTTPStatus.OK
