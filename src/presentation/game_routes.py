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
)
from src.business.grading_service import (
    CodeTooLargeError,
    RunFinishedError,
    StageNotGradableError,
)
from src.business.runner_client import (
    CheckScriptBrokenError,
    RunnerUnavailableError,
)
from src.business.service_factory import (
    build_game_service,
    build_grading_service,
)

game_blueprint = Blueprint("game", __name__)
logger = logging.getLogger(__name__)

# Placeholder wording until the PO decides; US10 moves it to dialogue.
NOT_GRADABLE = "This stage can't be graded yet."
UNAVAILABLE = "Grading is unavailable. This submit didn't count."


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
    """Show the current stage and lives for one of the player's runs."""
    try:
        stage = build_game_service().get_stage_view(current_user.id, run_id)
    except RunNotFoundError:
        abort(404)
    return render_template("game/play.html", stage=stage, run_id=run_id)


def _message(status: HTTPStatus, message: str) -> tuple[Response, int]:
    return jsonify(message=message), status


@game_blueprint.post("/game/submit")
@login_required
def submit() -> tuple[Response, int]:
    """Grade the editor's code for the run's current stage (US6)."""
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        abort(400)
    run_id, code = payload.get("run_id"), payload.get("code")
    if (
        not isinstance(run_id, int)
        or isinstance(run_id, bool)
        or not isinstance(code, str)
    ):
        abort(400)

    grading = build_grading_service(current_app.config["RUNNER_URL"])
    try:
        verdict = grading.grade(current_user.id, run_id, code)
    except RunNotFoundError:
        abort(404)
    except RunFinishedError:
        abort(409)
    except CodeTooLargeError:
        abort(400)
    except StageNotGradableError:
        return _message(HTTPStatus.UNPROCESSABLE_ENTITY, NOT_GRADABLE)
    except (RunnerUnavailableError, CheckScriptBrokenError):
        logger.exception("grading failed for run %s", run_id)
        return _message(HTTPStatus.SERVICE_UNAVAILABLE, UNAVAILABLE)
    return jsonify(verdict=verdict.to_dict()), HTTPStatus.OK
