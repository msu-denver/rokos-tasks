"""
File: test_game_routes.py
Description: Tests difficulty availability, run creation, and ownership.
Author(s): Tyler Black
"""

import json
import re
from datetime import UTC, datetime

import pytest
from flask import Flask
from flask.testing import FlaskClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.data.models.campaign import Campaign
from src.data.models.game_run import GameRun
from src.data.repositories.campaign_repository import CampaignRepository
from src.data.repositories.run_repository import RunRepository


@pytest.fixture
def player(client: FlaskClient) -> FlaskClient:
    """Register a player and return the authenticated test client."""
    response = client.post(
        "/register",
        data={
            "username": "GameRoutePlayer",
            "password": "password123",
            "confirm": "password123",
        },
    )
    assert response.status_code == 302
    return client


def test_start_screen_shows_all_tier_rules_and_availability(
    player: FlaskClient, seeded_beginner: int, db_session: Session
) -> None:
    """Display exact rules and ignore campaigns that are not validated."""
    campaigns = CampaignRepository(db_session)
    campaigns.add(
        Campaign(
            title="Quarantined medium",
            slug="medium/quarantined",
            difficulty="medium",
            status="quarantined",
            content_hash="a" * 64,
        )
    )
    campaigns.commit()

    response = player.get("/start")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    for tier, stages, time, lives, multiplier in (
        ("beginner", "2", "4 min", "4", "1.0x"),
        ("easy", "3", "5 min", "3", "1.25x"),
        ("medium", "3", "6 min", "3", "1.5x"),
        ("hard", "4", "7 min", "3", "2.0x"),
        ("expert", "5", "8 min", "2", "2.5x"),
        ("impossible", "5", "8 min", "1", "3.0x"),
    ):
        card_id = f"start-tier-{tier}"
        assert f'data-testid="{card_id}"' in html
        assert f'data-testid="{card_id}-stages">{stages}<' in html
        assert f'data-testid="{card_id}-time">{time}<' in html
        assert f'data-testid="{card_id}-lives">{lives}<' in html
        assert f'data-testid="{card_id}-multiplier">{multiplier}<' in html
        if tier == "beginner":
            assert f'data-testid="{card_id}-button"' in html
        else:
            assert f'data-testid="{card_id}-coming-soon">Coming soon<' in html
            assert f'data-testid="{card_id}-button"' not in html


def test_start_screen_hides_resume_for_player_without_runs(
    player: FlaskClient,
) -> None:
    """Hide Resume run when the player has never started a run."""
    response = player.get("/start")
    assert response.status_code == 200
    assert 'data-testid="start-resume-run"' not in response.get_data(
        as_text=True
    )


@pytest.mark.parametrize("status", ["won", "lost", "abandoned"])
def test_start_screen_hides_resume_for_finished_run(
    player: FlaskClient, seeded_beginner: int, db_session: Session, status: str
) -> None:
    """Hide Resume run when the player's only run has ended."""
    start = player.post("/runs", data={"difficulty": "beginner"})
    assert start.status_code == 302
    play_url = start.headers["Location"]
    runs = RunRepository(db_session)
    run = runs.get(int(play_url.rsplit("/", 1)[1]))
    assert run is not None
    run.status = status
    run.ended_at = datetime.now(UTC)
    runs.commit()

    response = player.get("/start")
    assert response.status_code == 200
    assert 'data-testid="start-resume-run"' not in response.get_data(
        as_text=True
    )


def test_start_run_cancel_and_confirm_replacement(
    player: FlaskClient, seeded_beginner: int, db_session: Session
) -> None:
    """Keep the original on cancel and replace it only on confirmation."""
    first = player.post("/runs", data={"difficulty": "beginner"})
    assert first.status_code == 302
    first_url = first.headers["Location"]
    assert first_url.startswith("/play/")
    assert player.get(first_url).status_code == 200

    resume_link = (
        f'href="{first_url}" data-testid="start-resume-run">Resume run</a>'
    )
    start = player.get("/start")
    assert start.status_code == 200
    start_html = start.get_data(as_text=True)
    assert resume_link in start_html
    assert 'data-testid="start-tier-beginner-button"' in start_html
    assert 'data-testid="start-confirm-abandon"' not in start_html

    unavailable = player.post("/runs", data={"difficulty": "hard"})
    assert unavailable.status_code == 200
    unavailable_html = unavailable.get_data(as_text=True)
    assert 'data-testid="start-error">No campaigns for this tier yet.' in (
        unavailable_html
    )
    assert resume_link in unavailable_html

    runs = RunRepository(db_session)
    first_id = int(first_url.rsplit("/", 1)[1])
    old_run = runs.get(first_id)
    assert old_run is not None
    old_run.score = 50
    runs.commit()

    pending = player.post("/runs", data={"difficulty": "beginner"})
    assert pending.status_code == 200
    html = pending.get_data(as_text=True)
    assert 'data-testid="start-confirm-abandon"' in html
    assert "abandon your current run with a score of 0" in html
    cancel_link = 'href="/start" data-testid="start-confirm-abandon-cancel"'
    assert cancel_link in html
    assert 'name="difficulty" value="beginner"' in html

    canceled = player.get("/start")
    assert canceled.status_code == 200
    canceled_html = canceled.get_data(as_text=True)
    assert 'data-testid="start-tier-beginner-button"' in canceled_html
    assert resume_link in canceled_html
    db_session.refresh(old_run)
    assert (old_run.status, old_run.score, old_run.ended_at) == (
        "in_progress",
        50,
        None,
    )
    run_ids = select(GameRun.id).where(GameRun.user_id == old_run.user_id)
    assert db_session.scalars(run_ids).all() == [first_id]

    confirmation = {
        "difficulty": "beginner",
        "replace_active": "yes",
        "active_run_id": first_id,
    }
    second = player.post("/runs", data=confirmation)
    assert second.status_code == 302
    second_url = second.headers["Location"]
    assert second_url != first_url

    db_session.refresh(old_run)
    assert (old_run.status, old_run.score) == ("abandoned", 0)
    active_run = runs.active_for(old_run.user_id)
    assert active_run is not None
    assert second_url == f"/play/{active_run.id}"
    assert active_run.campaign_id == seeded_beginner
    assert old_run.ended_at == active_run.started_at
    assert runs.last_started_by_user(old_run.user_id) == {
        active_run.campaign_id: active_run.started_at
    }
    assert set(db_session.scalars(run_ids)) == {first_id, active_run.id}

    replay = player.post("/runs", data=confirmation)
    assert replay.status_code == 200
    assert f'name="active_run_id" value="{active_run.id}"' in (
        replay.get_data(as_text=True)
    )
    db_session.refresh(active_run)
    assert active_run.status == "in_progress"
    assert set(db_session.scalars(run_ids)) == {first_id, active_run.id}


def test_play_returns_404_for_another_player(
    player: FlaskClient, seeded_beginner: int
) -> None:
    """Keep the run private after logging in as a different player."""
    response = player.post("/runs", data={"difficulty": "beginner"})
    play_url = response.headers["Location"]
    assert player.post("/logout").status_code == 302
    assert player.get(play_url).headers["Location"].startswith("/login?next=")
    player.post(
        "/register",
        data={
            "username": "OtherPlayer",
            "password": "password123",
            "confirm": "password123",
        },
    )
    assert player.get(play_url).status_code == 404


def test_play_returns_404_for_missing_run(player: FlaskClient) -> None:
    """Return the same status for missing runs as for foreign runs."""
    assert player.get("/play/0").status_code == 404


def test_play_serializes_only_public_stage_content(
    player: FlaskClient, seeded_beginner: int, db_session: Session
) -> None:
    """The page shows the prompt; the check script and reference never.

    US4: the page HTML has no check script, so a player can't read the
    rules' code or the reference program from the browser.
    """
    campaigns = CampaignRepository(db_session)
    campaign = campaigns.get(seeded_beginner)
    assert campaign is not None
    stage = campaign.stages[0]
    private_check = 'def check(game):\n    game.fail("private </script>")\n'
    private_reference = "private_reference_program"
    stage.check_script = private_check
    stage.reference_program = private_reference
    campaigns.commit()

    start = player.post("/runs", data={"difficulty": "beginner"})
    response = player.get(start.headers["Location"])
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Light exactly one lamp." in html
    for private in ("private </script>", "def check", private_reference):
        assert private not in html
    payload = re.search(
        r'<script id="stage-data" type="application/json">(.*?)</script>', html
    )
    assert payload is not None
    assert json.loads(payload[1]) == {"stage": 1}


def test_play_uses_current_stage_and_remaining_lives(
    player: FlaskClient, seeded_beginner: int, db_session: Session
) -> None:
    """Read the second stage's prompt and progress from the same run."""
    start = player.post("/runs", data={"difficulty": "beginner"})
    play_url = start.headers["Location"]
    runs = RunRepository(db_session)
    run = runs.get(int(play_url.rsplit("/", 1)[1]))
    assert run is not None
    run.current_stage = 2
    run.lives = 3
    runs.commit()

    response = player.get(play_url)
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'aria-label="Beginner, stage 2 of 2"' in html
    assert html.count("stage-bar-cell--current") == 1
    assert html.count("stage-bar-cell--done") == 1
    assert "tier-badge--beginner" in html
    assert 'aria-label="3 of 4 lives"' in html
    assert re.search(r'data-testid="game-timer"[^>]*>\s*00:00\s*<', html)
    assert "A light that never changes is a wall." in html
    payload = re.search(
        r'<script id="stage-data" type="application/json">(.*?)</script>', html
    )
    assert payload is not None
    assert json.loads(payload[1]) == {"stage": 2}


@pytest.mark.parametrize("status", ["won", "lost", "abandoned"])
def test_finished_runs_link_back_to_start(
    player: FlaskClient, seeded_beginner: int, db_session: Session, status: str
) -> None:
    """Provide a way to start over when the owned run has ended."""
    start = player.post("/runs", data={"difficulty": "beginner"})
    play_url = start.headers["Location"]
    runs = RunRepository(db_session)
    run = runs.get(int(play_url.rsplit("/", 1)[1]))
    assert run is not None
    run.status = status
    run.ended_at = datetime.now(UTC)
    runs.commit()

    response = player.get(play_url)
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'data-testid="game-run-over">This run is over.' in html
    assert 'href="/start">Start a run' in html
    assert 'id="stage-data"' not in html
    assert 'data-testid="game-editor"' not in html
    body = re.search(r'<body\b[^>]*\sclass="([^"]*)"', html)
    assert body is None or "page-game" not in body[1].split()
    assert 'data-testid="game-tier"' not in html


@pytest.mark.parametrize("difficulty", ["unknown", None])
def test_create_run_rejects_invalid_difficulty(
    player: FlaskClient, difficulty: str | None
) -> None:
    """Reject malformed requests before starting a run."""
    form = {"difficulty": difficulty} if difficulty is not None else {}
    assert player.post("/runs", data=form).status_code == 400


def test_create_run_rejects_invalid_confirmation_id(
    player: FlaskClient,
) -> None:
    """Reject a malformed ID on a replacement request."""
    form = {
        "difficulty": "beginner",
        "replace_active": "yes",
        "active_run_id": "invalid",
    }
    assert player.post("/runs", data=form).status_code == 400


def test_create_run_requires_login_and_csrf(
    app: Flask, client: FlaskClient
) -> None:
    """Protect run creation with both an account and a valid form token."""
    data = {"difficulty": "beginner"}
    assert (
        client.post("/runs", data=data)
        .headers["Location"]
        .startswith("/login?next=")
    )
    client.post(
        "/register",
        data={
            "username": "CsrfGamePlayer",
            "password": "password123",
            "confirm": "password123",
        },
    )
    app.config["WTF_CSRF_ENABLED"] = True
    assert client.post("/runs", data=data).status_code == 400
