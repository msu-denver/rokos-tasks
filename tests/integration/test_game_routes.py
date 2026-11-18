"""
File: test_game_routes.py
Description: Tests difficulty availability, starting, resuming, and ownership.
Author(s): Tyler Black
"""

import pytest
from flask import Flask
from flask.testing import FlaskClient
from sqlalchemy.orm import Session

from src.data.models.campaign import Campaign
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


def test_start_resume_and_replace_run(
    player: FlaskClient, seeded_beginner: int, db_session: Session
) -> None:
    """Start a run, offer resumption, and persist an atomic replacement."""
    first = player.post("/runs", data={"difficulty": "beginner"})
    assert first.status_code == 302
    first_url = first.headers["Location"]
    assert first_url.startswith("/play/")
    play_html = player.get(first_url).get_data(as_text=True)
    assert 'data-testid="play-stage">Stage 1<' in play_html
    assert 'data-testid="play-lives">4<' in play_html

    start_html = player.get("/start").get_data(as_text=True)
    assert f'href="{first_url}" data-testid="start-resume-run"' in start_html

    unavailable = player.post("/runs", data={"difficulty": "hard"})
    assert unavailable.status_code == 200
    unavailable_html = unavailable.get_data(as_text=True)
    assert 'data-testid="start-error">No campaigns for this tier yet.' in (
        unavailable_html
    )
    assert f'href="{first_url}"' in unavailable_html

    second = player.post("/runs", data={"difficulty": "beginner"})
    assert second.status_code == 302
    second_url = second.headers["Location"]
    assert second_url != first_url

    runs = RunRepository(db_session)
    old_run = runs.get(int(first_url.rsplit("/", 1)[1]))
    assert old_run is not None
    assert (old_run.status, old_run.score) == ("abandoned", 0)
    active_run = runs.active_for(old_run.user_id)
    assert active_run is not None
    assert second_url == f"/play/{active_run.id}"
    assert active_run.campaign_id == seeded_beginner
    assert old_run.ended_at == active_run.started_at
    assert runs.last_started_by_user(old_run.user_id) == {
        active_run.campaign_id: active_run.started_at
    }


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


@pytest.mark.parametrize("difficulty", ["unknown", None])
def test_create_run_rejects_invalid_difficulty(
    player: FlaskClient, difficulty: str | None
) -> None:
    """Reject malformed requests before starting a run."""
    form = {"difficulty": difficulty} if difficulty is not None else {}
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
