"""
File: test_pong_campaign.py
Description: US6 tests for the ASCII Pong seed campaign's check scripts:
    every reference passes, each broken program fails with the rule it
    breaks, and programs that differ in speed, start, or serve (AC3) all
    pass. Uses the same Grader the runner container uses.
Author(s): Richard Hall, Tyler Black
"""

import json
from pathlib import Path

import pytest

from src.business.campaigns.check_runner import run_check, run_screens
from src.business.campaigns.validator import screen_program
from tests.conftest import requires_host_play

ROOT = Path(__file__).resolve().parents[2]
PONG = json.loads(
    (ROOT / "content/campaigns/seed/medium/pong.json").read_text("utf-8")
)
PROGRAMS = ROOT / "tests/fixtures/pong"


def check_script(stage: int) -> str:
    return PONG["stages"][stage - 1]["check_script"]


def grade_fixture(name: str, stage: int) -> dict:
    """Grade a fixture program, or the stage's own ``broken_program``."""
    if name == "broken_program":
        code = PONG["stages"][stage - 1]["broken_program"]
    else:
        code = (PROGRAMS / name).read_text("utf-8")
    return run_check(code, check_script(stage))


@requires_host_play
@pytest.mark.parametrize("stage", [1, 2, 3])
def test_reference_passes(stage: int):
    reference = PONG["stages"][stage - 1]["reference_program"]
    assert run_check(reference, check_script(stage))["verdict"] == "pass"


@requires_host_play
@pytest.mark.parametrize(
    ("name", "stage", "rule"),
    [
        (
            "broken_program",
            1,
            "The board must show exactly one ball (O).",
        ),
        (
            "broken_program",
            2,
            "Pressing q must move only the left paddle up one row.",
        ),
        (
            "stage2_no_edge_stop.py",
            2,
            "Holding q must move the paddle until it stops at the edge.",
        ),
        (
            "broken_program",
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
            "The ball must move exactly one row up or down every turn.",
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
    assert verdict["last_screen"] is not None


@requires_host_play
def test_two_balls_names_the_rule_on_the_first_screen():
    """US6 AC2: a board with two O characters fails before any input."""
    verdict = grade_fixture("broken_program", 1)
    assert (verdict["turn"], verdict["inputs"]) == (0, [])
    assert verdict["last_screen"].count("O") == 2


@requires_host_play
def test_stage_one_is_a_plain_script():
    """Stage 1's reference prints the board and exits, asking nothing."""
    reference = PONG["stages"][0]["reference_program"]
    assert "input" not in reference
    verdict = run_check(reference, check_script(1))
    assert verdict["verdict"] == "pass"
    assert verdict["inputs"] == []


@requires_host_play
def test_main_function_script_passes_stage_one():
    """A normal `if __name__ == "__main__": main()` script passes."""
    reference = PONG["stages"][0]["reference_program"]
    body = "".join(f"    {line}\n" for line in reference.splitlines())
    code = f'def main():\n{body}\n\nif __name__ == "__main__":\n    main()\n'
    assert run_check(code, check_script(1))["verdict"] == "pass"


@requires_host_play
def test_stage_one_board_that_waits_for_input_fails():
    """Stage 1 reads no input, so a program that asks for some fails."""
    reference = PONG["stages"][0]["reference_program"]
    verdict = run_check(reference + "input()\n", check_script(1))
    assert (verdict["reason"], verdict["rule"]) == (
        "rule",
        "Print the board, then end. This stage reads no input.",
    )


@requires_host_play
def test_stage_one_program_fails_stage_two():
    """Printing once and exiting can't satisfy a stage that reads keys."""
    stage_one = PONG["stages"][0]["reference_program"]
    verdict = run_check(stage_one, check_script(2))
    assert verdict["verdict"] == "fail"


@requires_host_play
def test_different_speed_start_and_paddles_pass():
    """US6 AC3: 3 columns per turn from a corner passes like the reference."""
    assert grade_fixture("stage3_fast_from_corner.py", 3)["verdict"] == "pass"


@requires_host_play
def test_random_serve_passes_three_runs():
    """US6 AC3: a random start and serve passes on 3 separate runs."""
    verdicts = [grade_fixture("stage3_random_serve.py", 3) for _ in range(3)]
    assert [verdict["verdict"] for verdict in verdicts] == ["pass"] * 3


@requires_host_play
def test_turn_limit_fails_with_its_rule():
    """With too few turns to see every event, the verdict is a fail."""
    rushed = check_script(3).replace("TURN_LIMIT = 400", "TURN_LIMIT = 3")
    reference = PONG["stages"][2]["reference_program"]
    verdict = run_check(reference, rushed)
    assert verdict["rule"] == (
        "Within 3 turns the ball must bounce off a wall, bounce off a "
        "paddle, and score a miss."
    )


@requires_host_play
def test_oversized_score_fails_instead_of_crashing():
    """A score past int()'s digit cap is a FAIL, not a check_error."""
    screen = run_screens(PONG["stages"][2]["reference_program"], [])[0]
    huge = screen.replace("0 0", f"{'9' * 5000} 0")
    verdict = run_check(screen_program(huge), check_script(3))
    assert (verdict["reason"], verdict["rule"]) == (
        "rule",
        "The last line must be the score: two whole numbers, like 0 0.",
    )


@requires_host_play
def test_crash_is_reported_with_traceback():
    """US6 AC2: a crash fails with the player's traceback."""
    verdict = run_check("raise ValueError('no ball')\n", check_script(1))
    assert verdict["reason"] == "crashed"
    assert "ValueError: no ball" in verdict["traceback"]
