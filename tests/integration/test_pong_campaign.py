"""
File: test_pong_campaign.py
Description: US6 tests for the ASCII Pong seed campaign's check scripts:
    every reference passes, each broken program fails with the rule it
    breaks, and programs that differ in speed, start, or serve (AC3) all
    pass. Uses the same Grader the runner container uses.
Author(s): Richard Hall
"""

import json
from pathlib import Path

import pytest

from src.business.campaigns.check_runner import run_check

ROOT = Path(__file__).resolve().parents[2]
PONG = json.loads(
    (ROOT / "content/campaigns/seed/medium/pong.json").read_text("utf-8")
)
PROGRAMS = ROOT / "tests/fixtures/pong"


def check_script(stage: int) -> str:
    return PONG["stages"][stage - 1]["check_script"]


def grade_fixture(name: str, stage: int) -> dict:
    code = (PROGRAMS / name).read_text("utf-8")
    return run_check(code, check_script(stage))


@pytest.mark.parametrize("stage", [1, 2, 3])
def test_reference_passes(stage: int):
    reference = PONG["stages"][stage - 1]["reference_solution"]
    assert run_check(reference, check_script(stage))["verdict"] == "pass"


@pytest.mark.parametrize(
    ("name", "stage", "rule"),
    [
        (
            "stage1_two_balls.py",
            1,
            "The board must show exactly one ball (O).",
        ),
        (
            "stage2_wrong_paddle.py",
            2,
            "Pressing q must move only the left paddle up one row.",
        ),
        (
            "stage2_no_edge_stop.py",
            2,
            "Holding q must move the paddle until it stops at the edge.",
        ),
        (
            "stage3_ball_through_paddle.py",
            3,
            "The ball must bounce off the right paddle when it covers the "
            "ball's row.",
        ),
        (
            "stage3_score_wrong_side.py",
            3,
            "When the ball gets past the left paddle, the other side must "
            "score.",
        ),
        (
            "stage3_ball_stuck_on_row.py",
            3,
            "The ball must move exactly one row up or down every tick.",
        ),
        (
            "stage3_bad_serve.py",
            3,
            "After a miss, the ball must be served from columns 5 to 14.",
        ),
    ],
)
def test_broken_program_fails_with_its_rule(name: str, stage: int, rule: str):
    verdict = grade_fixture(name, stage)
    assert verdict["verdict"] == "fail"
    assert (verdict["reason"], verdict["rule"]) == ("rule", rule)
    assert verdict["last_frame"] is not None


def test_two_balls_names_the_rule_at_tick_one():
    """US6 AC2: a frame with two O characters fails on that tick."""
    verdict = grade_fixture("stage1_two_balls.py", 1)
    assert verdict["tick"] == 1
    assert verdict["last_frame"].count("O") == 2


def test_different_speed_start_and_paddles_pass():
    """US6 AC3: 3 columns per tick from a corner passes like the reference."""
    assert grade_fixture("stage3_fast_from_corner.py", 3)["verdict"] == "pass"


def test_random_serve_passes_three_runs():
    """US6 AC3: a random start and serve passes on 3 separate runs."""
    verdicts = [grade_fixture("stage3_random_serve.py", 3) for _ in range(3)]
    assert [verdict["verdict"] for verdict in verdicts] == ["pass"] * 3


def test_tick_limit_fails_with_its_rule():
    """With too few ticks to see every event, the verdict is a fail."""
    rushed = check_script(3).replace("TICK_LIMIT = 400", "TICK_LIMIT = 3")
    reference = PONG["stages"][2]["reference_solution"]
    verdict = run_check(reference, rushed)
    assert verdict["rule"] == (
        "Within 3 ticks the ball must bounce off a wall, bounce off a "
        "paddle, and score a miss."
    )


def test_crash_is_reported_with_traceback():
    """US6 AC2: a crash fails with the player's traceback."""
    verdict = run_check(
        "input()\nraise ValueError('no ball')\n", check_script(1)
    )
    assert verdict["reason"] == "crashed"
    assert "ValueError: no ball" in verdict["traceback"]
