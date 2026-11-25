"""
File: test_submit_route.py
Description: Integration tests for POST /game/submit (US6): the Flask
    route, GradingService, RunnerClient, and the runner's HTTP API with
    the real Pong check scripts, end to end. Covers verdicts, errors,
    access rules, and that lives don't change (US7).
Author(s): Richard Hall, Tyler Black
"""

import json
from pathlib import Path

import pytest
from flask import Flask
from flask.testing import FlaskClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.business.grading_service import MAX_CODE_BYTES
from src.data.models.campaign import Stage
from src.data.models.game_run import GameRun
from tests.conftest import requires_host_play

ROOT = Path(__file__).resolve().parents[2]
PONG = json.loads(
    (ROOT / "content/campaigns/seed/medium/pong.json").read_text("utf-8")
)
STAGE_1 = PONG["stages"][0]["reference_program"]
TWO_BALLS = PONG["stages"][0]["broken_program"]
TRAFFIC = json.loads(
    (ROOT / "content/campaigns/seed/beginner/traffic_light.json").read_text(
        "utf-8"
    )
)


@pytest.fixture
def player(client: FlaskClient) -> FlaskClient:
    """Register a player and return the authenticated test client."""
    client.post(
        "/register",
        data={
            "username": "SubmitPlayer",
            "password": "password123",
            "confirm": "password123",
        },
    )
    return client


def start_run(player: FlaskClient, difficulty: str) -> int:
    response = player.post("/runs", data={"difficulty": difficulty})
    return int(response.headers["Location"].rsplit("/", 1)[1])


def submit(player: FlaskClient, run_id: object, code: object):
    return player.post("/game/submit", json={"run_id": run_id, "code": code})


@requires_host_play
def test_reference_passes(player: FlaskClient, seeded_pong: int):
    """US6 AC1: the Pong stage 1 reference gets a pass."""
    response = submit(player, start_run(player, "medium"), STAGE_1)
    assert response.status_code == 200
    verdict = response.get_json()["verdict"]
    assert (verdict["passed"], verdict["heading"]) == (True, "PASS")
    assert verdict["reason"] is None


@requires_host_play
def test_broken_rule_is_named(player: FlaskClient, seeded_pong: int):
    """US6 AC2: a board with two O characters fails with the rule."""
    verdict = submit(
        player, start_run(player, "medium"), TWO_BALLS
    ).get_json()["verdict"]
    assert verdict["heading"] == "FAIL"
    assert verdict["reason"] == "The board must show exactly one ball (O)."
    assert verdict["last_screen"].count("O") == 2


@requires_host_play
def test_crash_shows_the_traceback(player: FlaskClient, seeded_pong: int):
    """US6 AC2: a crash fails with a traceback that names main.py."""
    code = "print('thinking')\nraise ValueError('no ball')\n"
    verdict = submit(player, start_run(player, "medium"), code).get_json()[
        "verdict"
    ]
    assert verdict["reason"] == "Crashed."
    assert 'File "main.py", line 2' in verdict["traceback"]
    assert "/sandbox" not in verdict["traceback"]
    assert "ValueError: no ball" in verdict["traceback"]


def test_lives_do_not_change(
    player: FlaskClient, seeded_pong: int, db_session: Session
):
    """US7 owns lives: a failed Submit leaves them as they were."""
    run_id = start_run(player, "medium")
    submit(player, run_id, TWO_BALLS)
    run = db_session.get(GameRun, run_id)
    db_session.refresh(run)
    assert (run.lives, run.current_stage) == (3, 1)


@requires_host_play
def test_beginner_stage_is_graded(player: FlaskClient, seeded_beginner: int):
    """#19 AC1: Beginner stages are graded by check scripts too."""
    reference = TRAFFIC["stages"][0]["reference_program"]
    response = submit(player, start_run(player, "beginner"), reference)
    assert response.status_code == 200
    assert response.get_json()["verdict"]["passed"] is True


def test_lone_surrogate_is_a_bad_request(
    player: FlaskClient, seeded_pong: int
):
    """Code that isn't valid text gets 400, not a server error."""
    response = submit(player, start_run(player, "medium"), "print('\ud800')")
    assert response.status_code == 400


def test_runner_down_does_not_count(
    app: Flask, player: FlaskClient, seeded_pong: int
):
    run_id = start_run(player, "medium")
    app.config["RUNNER_URL"] = "http://127.0.0.1:9"
    response = submit(player, run_id, STAGE_1)
    assert response.status_code == 503
    assert response.get_json() == {
        "message": "Grading is unavailable. This submit didn't count."
    }


def test_broken_check_script_does_not_count(
    player: FlaskClient, seeded_pong: int, db_session: Session
):
    run_id = start_run(player, "medium")
    run = db_session.get(GameRun, run_id)
    stage = db_session.scalars(
        select(Stage).where(
            Stage.campaign_id == run.campaign_id, Stage.number == 1
        )
    ).one()
    stage.check_script = "def check(game):\n    1 / 0\n"
    db_session.flush()
    assert submit(player, run_id, STAGE_1).status_code == 503


@pytest.mark.parametrize(
    "body",
    [
        None,
        {"run_id": "1", "code": ""},
        {"run_id": True, "code": ""},
        {"run_id": 1, "code": 5},
    ],
)
def test_bad_body_is_400(player: FlaskClient, body: object):
    assert player.post("/game/submit", json=body).status_code == 400


def test_huge_request_is_refused(player: FlaskClient):
    """Flask refuses bodies over 1 MB before reading them."""
    body = {"run_id": 1, "code": "x" * (1024 * 1024)}
    assert player.post("/game/submit", json=body).status_code == 413


def test_oversized_code_is_400(player: FlaskClient, seeded_pong: int):
    run_id = start_run(player, "medium")
    response = submit(player, run_id, "x" * (MAX_CODE_BYTES + 1))
    assert response.status_code == 400


def test_other_players_run_is_404(
    player: FlaskClient, client: FlaskClient, seeded_pong: int, app: Flask
):
    run_id = start_run(player, "medium")
    stranger = app.test_client()
    stranger.post(
        "/register",
        data={
            "username": "Stranger",
            "password": "password123",
            "confirm": "password123",
        },
    )
    assert submit(stranger, run_id, STAGE_1).status_code == 404
    assert submit(player, 999999, STAGE_1).status_code == 404


def test_finished_run_is_409(
    player: FlaskClient, seeded_pong: int, db_session: Session
):
    run_id = start_run(player, "medium")
    db_session.get(GameRun, run_id).status = "lost"
    db_session.flush()
    assert submit(player, run_id, STAGE_1).status_code == 409


def test_submit_requires_login_and_csrf(
    app: Flask, client: FlaskClient, seeded_pong: int
):
    response = client.post("/game/submit", json={"run_id": 1, "code": ""})
    assert response.headers["Location"].startswith("/login?next=")
    client.post(
        "/register",
        data={
            "username": "CsrfSubmitter",
            "password": "password123",
            "confirm": "password123",
        },
    )
    run_id = start_run(client, "medium")
    app.config["WTF_CSRF_ENABLED"] = True
    assert submit(client, run_id, STAGE_1).status_code == 400


def test_play_page_has_submit_and_verdict(
    player: FlaskClient, seeded_pong: int
):
    run_id = start_run(player, "medium")
    html = player.get(f"/play/{run_id}").get_data(as_text=True)
    for test_id in (
        "game-submit",
        "game-verdict",
        "game-verdict-heading",
        "game-verdict-reason",
        "game-verdict-traceback",
        "game-verdict-frame",
    ):
        assert f'data-testid="{test_id}"' in html
    assert 'data-submit-url="/game/submit"' in html
    assert "check_script" not in html
    assert "def check" not in html
