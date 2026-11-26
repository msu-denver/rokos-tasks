"""
File: test_submit_route.py
Description: Integration tests for POST /game/submit (US6, US7): the
    Flask route, GameService, GradingService, RunnerClient, and the
    runner's HTTP API with the real check scripts, end to end. Covers
    verdicts, errors, access rules, and how each verdict changes the run.
Author(s): Richard Hall, Tyler Black
"""

import json
from pathlib import Path

import pytest
from flask import Flask, Response
from flask.testing import FlaskClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.business.game_service import GameService, StaleSubmitError
from src.business.grading_service import MAX_CODE_BYTES
from src.data.models import Checkpoint, Submission
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
    """Start a run and return its ID from the redirect."""
    response = player.post("/runs", data={"difficulty": difficulty})
    return int(response.headers["Location"].rsplit("/", 1)[1])


def submit(
    player: FlaskClient, run_id: object, code: object, stage: object = 1
) -> Response:
    """Post a program for grading from a page showing ``stage``."""
    return player.post(
        "/game/submit", json={"run_id": run_id, "stage": stage, "code": code}
    )


@requires_host_play
def test_reference_passes(
    player: FlaskClient, seeded_pong: int, db_session: Session
) -> None:
    """US6 AC1, US7 AC1: a pass opens stage 2 with a checkpoint."""
    run_id = start_run(player, "medium")
    response = submit(player, run_id, STAGE_1)
    assert response.status_code == 200
    body = response.get_json()
    verdict = body["verdict"]
    assert (verdict["passed"], verdict["heading"]) == (True, "PASS")
    assert verdict["reason"] is None
    assert body["stage"] == {
        "number": 2,
        "prompt": PONG["stages"][1]["prompt"],
    }
    assert body["checkpoint"] == STAGE_1
    run = db_session.get_one(GameRun, run_id)
    assert run.current_stage == body["run"]["stage"] == 2
    assert run.score == body["run"]["score"] == body["run"]["stage_points"] > 0
    checkpoint = db_session.scalars(
        select(Checkpoint).where(Checkpoint.run_id == run_id)
    ).one()
    assert (checkpoint.stage_number, checkpoint.code) == (1, STAGE_1)


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


@requires_host_play
def test_failing_submit_costs_a_life_and_records_attempt(
    player: FlaskClient, seeded_pong: int, db_session: Session
) -> None:
    """US7 AC2: a fail costs one life and records the attempt."""
    run_id = start_run(player, "medium")
    response = submit(player, run_id, TWO_BALLS)
    assert response.status_code == 200
    body = response.get_json()
    assert body["run"] == {
        "status": "in_progress",
        "lives": 2,
        "stage": 1,
        "score": 0,
        "stage_points": 0,
    }
    assert body["stage"] is body["checkpoint"] is None
    run = db_session.get_one(GameRun, run_id)
    assert (run.lives, run.current_stage) == (2, 1)
    attempt = db_session.scalars(
        select(Submission).where(Submission.run_id == run_id)
    ).one()
    assert (attempt.stage_number, attempt.code, attempt.passed) == (
        1,
        TWO_BALLS,
        False,
    )


@requires_host_play
def test_beginner_campaign_can_be_won(
    player: FlaskClient, seeded_beginner: int, db_session: Session
) -> None:
    """#19 AC1, US7 AC3: pass both Beginner stages to win the run."""
    run_id = start_run(player, "beginner")
    for number, stage in enumerate(TRAFFIC["stages"], start=1):
        response = submit(player, run_id, stage["reference_program"], number)
        assert response.status_code == 200
        body = response.get_json()
        assert body["verdict"]["passed"] is True
        assert body["run"]["stage_points"] > 0
    assert body["run"]["status"] == "won"
    assert body["stage"] is None
    run = db_session.get_one(GameRun, run_id)
    assert (run.status, run.current_stage, run.lives) == ("won", 2, 4)
    assert run.score == body["run"]["score"] > body["run"]["stage_points"]
    assert player.get(f"/play/{run_id}").status_code == 200


@requires_host_play
def test_four_failures_end_beginner_run(
    player: FlaskClient, seeded_beginner: int, db_session: Session
) -> None:
    """US7 AC3: four fails lose a Beginner run with a 0 score."""
    run_id = start_run(player, "beginner")
    first, second = TRAFFIC["stages"]
    passed = submit(player, run_id, first["reference_program"]).get_json()
    assert passed["run"]["score"] > 0
    for lives in (3, 2, 1, 0):
        response = submit(player, run_id, second["broken_program"], 2)
        assert response.status_code == 200
        body = response.get_json()
        assert body["verdict"]["passed"] is False
        assert body["run"]["lives"] == lives
        expected = None if lives == 0 else first["reference_program"]
        assert body["checkpoint"] == expected
    assert (body["run"]["status"], body["run"]["score"]) == ("lost", 0)
    run = db_session.get_one(GameRun, run_id)
    assert (run.status, run.lives, run.score) == ("lost", 0, 0)


@pytest.mark.parametrize("code", ["print('\ud800')", "print(1)\0"])
def test_code_that_is_not_text_is_a_bad_request(
    player: FlaskClient, seeded_pong: int, db_session: Session, code: str
):
    """A lone surrogate or a NUL gets 400 and costs nothing."""
    run_id = start_run(player, "medium")
    response = submit(player, run_id, code)
    assert response.status_code == 400
    assert db_session.get_one(GameRun, run_id).lives == 3
    assert (
        db_session.scalars(
            select(Submission).where(Submission.run_id == run_id)
        ).all()
        == []
    )


@requires_host_play
def test_submit_from_an_old_page_is_refused(
    player: FlaskClient, seeded_pong: int, db_session: Session
) -> None:
    """A page still on Stage 1 after the pass gets 409 before grading."""
    run_id = start_run(player, "medium")
    assert submit(player, run_id, STAGE_1).status_code == 200
    score = db_session.get_one(GameRun, run_id).score

    response = submit(player, run_id, TWO_BALLS, stage=1)
    assert response.status_code == 409
    assert response.get_json() == {"message": "This page is out of date."}
    run = db_session.get_one(GameRun, run_id)
    assert (run.lives, run.current_stage, run.score) == (3, 2, score)
    attempts = db_session.scalars(
        select(Submission).where(Submission.run_id == run_id)
    ).all()
    assert [attempt.passed for attempt in attempts] == [True]


def test_runner_down_does_not_count(
    app: Flask, player: FlaskClient, seeded_pong: int, db_session: Session
) -> None:
    """An unavailable runner leaves the run and attempt history intact."""
    run_id = start_run(player, "medium")
    app.config["RUNNER_URL"] = "http://127.0.0.1:9"
    response = submit(player, run_id, STAGE_1)
    assert response.status_code == 503
    assert response.get_json() == {
        "message": "Grading is unavailable. This submit didn't count."
    }
    _assert_uncounted(db_session, run_id)


def test_broken_check_script_does_not_count(
    player: FlaskClient, seeded_pong: int, db_session: Session
) -> None:
    """Errors in a check script leave the run and attempt history intact."""
    run_id = start_run(player, "medium")
    run = db_session.get(GameRun, run_id)
    stage = db_session.scalars(
        select(Stage).where(
            Stage.campaign_id == run.campaign_id, Stage.number == 1
        )
    ).one()
    stage.check_script = "def check(game):\n    1 / 0\n"
    db_session.commit()
    assert submit(player, run_id, STAGE_1).status_code == 503
    _assert_uncounted(db_session, run_id)


def test_missing_check_script_does_not_count(
    player: FlaskClient, seeded_pong: int, db_session: Session
) -> None:
    """A missing stage check script returns the grading-unavailable error."""
    run_id = start_run(player, "medium")
    missing_stage = len(PONG["stages"]) + 1
    db_session.get_one(GameRun, run_id).current_stage = missing_stage
    db_session.commit()

    response = submit(player, run_id, STAGE_1, missing_stage)

    assert response.status_code == 503
    assert response.get_json() == {
        "message": "Grading is unavailable. This submit didn't count."
    }
    _assert_uncounted(db_session, run_id, stage=missing_stage)


def _assert_uncounted(
    db_session: Session, run_id: int, *, stage: int = 1
) -> None:
    run = db_session.get_one(GameRun, run_id)
    db_session.refresh(run)
    assert (run.lives, run.current_stage, run.score) == (3, stage, 0)
    assert (
        db_session.scalars(
            select(Submission).where(Submission.run_id == run_id)
        ).one_or_none()
        is None
    )


def test_stale_submit_returns_conflict(
    player: FlaskClient, seeded_pong: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    """US7 AC5: a verdict for a run that changed while grading gets 409."""

    def reject(
        self: GameService, user_id: int, run_id: int, code: str, stage: int
    ) -> None:
        raise StaleSubmitError

    monkeypatch.setattr(GameService, "submit_stage", reject)
    response = submit(player, start_run(player, "medium"), STAGE_1)
    assert response.status_code == 409
    assert response.get_json() == {"message": "This page is out of date."}


@pytest.mark.parametrize(
    "body",
    [
        None,
        {"run_id": "1", "stage": 1, "code": ""},
        {"run_id": True, "stage": 1, "code": ""},
        {"run_id": 1, "stage": 1, "code": 5},
        {"run_id": 1, "code": ""},
        {"run_id": 1, "stage": "1", "code": ""},
        {"run_id": 1, "stage": True, "code": ""},
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
