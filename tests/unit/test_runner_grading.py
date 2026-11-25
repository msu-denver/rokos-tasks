"""
File: test_runner_grading.py
Description: Unit tests for Grader in host mode: a real player program
    and a real check script, each in its own slot, relayed tick by tick.
    Covers pass, a broken rule, crashes, timeouts, what the check script
    can see, and check-script failures.
Author(s): Richard Hall, Tyler Black
"""

import sys
from pathlib import Path
from textwrap import dedent

import pytest

from src.runner.grading import (
    CheckScriptError,
    Grader,
    harness_program,
    parse_check_request,
)
from src.runner.limits import SandboxLimits
from src.runner.slots import Slot

POSIX_ONLY = pytest.mark.skipif(
    sys.platform == "win32", reason="Linux only; CI runs it (POSIX APIs)"
)
HOST_LIMITS = SandboxLimits(memory_bytes=None, tick_seconds=2.0)

ONE_BALL = dedent(
    """
    def check(game):
        for key in ["", "q", ""]:
            frame = game.tick(key)
            game.check(
                len(frame.find("O")) == 1,
                "The board must show exactly one ball.",
            )
    """
)

BALL_PROGRAM = dedent(
    """
    import sys
    for line in sys.stdin:
        print("....")
        print(".O..")
        print("---")
    """
)


# Writes junk straight to the real stdout, past the harness's redirect.
PROTOCOL_BREAKER = dedent(
    """
    import sys
    def check(game):
        sys.__stdout__.write("junk\\n---\\n")
        sys.__stdout__.flush()
        game.tick()
    """
)


@pytest.fixture
def slots(tmp_path: Path) -> tuple[Slot, Slot]:
    (tmp_path / "program").mkdir()
    (tmp_path / "check").mkdir()
    return Slot(None, tmp_path / "program"), Slot(None, tmp_path / "check")


def grade(
    slots: tuple[Slot, Slot],
    code: str,
    check_script: str = ONE_BALL,
    limits: SandboxLimits = HOST_LIMITS,
) -> dict:
    return Grader(limits).grade(slots[0], slots[1], code, check_script)


@POSIX_ONLY
def test_program_that_follows_the_rules_passes(slots):
    assert grade(slots, BALL_PROGRAM) == {
        "verdict": "pass",
        "reason": None,
        "rule": None,
        "tick": 3,
        "inputs": ["", "q", ""],
        "last_frame": "....\n.O..",
        "traceback": "",
    }


@POSIX_ONLY
def test_broken_rule_names_the_rule_tick_and_frame(slots):
    two_balls = BALL_PROGRAM.replace(".O..", ".OO.")
    verdict = grade(slots, two_balls)
    assert verdict["verdict"] == "fail"
    assert verdict["reason"] == "rule"
    assert verdict["rule"] == "The board must show exactly one ball."
    assert verdict["tick"] == 1
    assert verdict["inputs"] == [""]
    assert verdict["last_frame"] == "....\n.OO."


@POSIX_ONLY
def test_crash_fails_with_the_traceback(slots):
    verdict = grade(slots, "input()\nraise ValueError('bad paddle')\n")
    assert verdict["reason"] == "crashed"
    assert "ValueError: bad paddle" in verdict["traceback"]
    assert verdict["last_frame"] is None


@POSIX_ONLY
def test_infinite_loop_fails_with_a_timeout(slots):
    limits = SandboxLimits(memory_bytes=None, tick_seconds=0.5)
    verdict = grade(slots, "input()\nwhile True:\n    pass\n", limits=limits)
    assert verdict["reason"] == "tick_timeout"


@POSIX_ONLY
def test_check_script_sees_frames_only(slots):
    """The check script can't find the player's code anywhere it looks."""
    snoop = dedent(
        """
        def check(game):
            frame = game.tick("")
            seen = repr(globals()) + repr(dir(game)) + frame
            game.check("SECRET_PLAYER_CODE" not in seen, "leaked")
        """
    )
    code = "# SECRET_PLAYER_CODE\n" + BALL_PROGRAM
    verdict = grade(slots, code, snoop)
    assert verdict["verdict"] == "pass"
    check_files = [path.name for path in slots[1].directory.iterdir()]
    assert check_files == []


@pytest.mark.parametrize(
    "broken_script",
    [
        "def check(game):\n    1 / 0\n",
        "x = 1\n",
        "def check(game):\n    while True:\n        pass\n",
        PROTOCOL_BREAKER,
    ],
)
@POSIX_ONLY
def test_broken_check_script_is_a_check_error(slots, broken_script: str):
    limits = SandboxLimits(memory_bytes=None, tick_seconds=0.5)
    with pytest.raises(CheckScriptError) as error:
        grade(slots, BALL_PROGRAM, broken_script, limits)
    assert isinstance(error.value.stderr, str)


@POSIX_ONLY
def test_check_script_that_plays_forever_is_stopped(slots, monkeypatch):
    monkeypatch.setattr("src.runner.grading.MAX_TICKS", 3)
    endless = "def check(game):\n    while True:\n        game.tick()\n"
    with pytest.raises(CheckScriptError, match="too long"):
        grade(slots, BALL_PROGRAM, endless)


@pytest.mark.parametrize(
    "frame",
    ["not json", "[1]", '{"tick": 5}', '{"tick": "a\\nb"}', '{"done": 1}'],
)
def test_bad_check_messages_are_rejected(frame: str):
    with pytest.raises(CheckScriptError):
        parse_check_request(frame)


def test_good_check_messages_are_accepted():
    assert parse_check_request('{"tick": "q"}') == {"tick": "q"}
    assert parse_check_request('{"done": true, "rule": null}') == {
        "done": True,
        "rule": None,
    }


def test_harness_program_embeds_the_script():
    program = harness_program("def check(game):\n    pass\n")
    assert program.rstrip().endswith("run('def check(game):\\n    pass\\n')")
    assert "class Game" in program
