"""
File: test_runner_grading.py
Description: Unit tests for Grader in host mode: a real player program
    and a real check script, each in its own slot, relayed one screen at
    a time. Covers pass, a broken rule, crashes, timeouts, a program that
    exits early or on time, what the check script can see, and
    check-script failures.
Author(s): Richard Hall, Tyler Black
"""

import json
import sys
from pathlib import Path
from textwrap import dedent

import pytest

from src.runner.grading import (
    CheckScriptError,
    Grader,
    harness_program,
    parse_check_request,
    screen_reply,
)
from src.runner.limits import SandboxLimits
from src.runner.slots import Slot

POSIX_ONLY = pytest.mark.skipif(
    sys.platform == "win32", reason="Linux only; CI runs it (POSIX APIs)"
)
HOST_LIMITS = SandboxLimits(memory_bytes=None, turn_seconds=2.0)

ONE_BALL = dedent(
    """
    def ball_count(screen):
        return len(screen.find("O"))

    def check(game):
        rule = "The board must show exactly one ball."
        game.check(ball_count(game.screen()) == 1, rule)
        for key in ["q", ""]:
            game.check(ball_count(game.send(key)) == 1, rule)
    """
)

BALL_PROGRAM = dedent(
    """
    def draw():
        print("....")
        print(".O..")

    draw()
    while True:
        input()
        draw()
    """
)

# Stage 1 style: print once and exit, like `python main.py`.
STATIC_CHECK = dedent(
    """
    def check(game):
        game.check(game.screen().rows == ["....", ".O.."], "Draw the board.")
        game.check(game.finished, "Print the board and exit.")
    """
)


# Writes junk straight to the real stdout, past the harness's redirect.
PROTOCOL_BREAKER = dedent(
    """
    import sys
    def check(game):
        sys.__stdout__.write("junk\\n")
        sys.__stdout__.flush()
        game.send()
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
        "turn": 2,
        "inputs": ["q", ""],
        "last_screen": "....\n.O..",
        "traceback": "",
    }


@POSIX_ONLY
def test_broken_rule_names_the_rule_turn_and_screen(slots):
    moving = BALL_PROGRAM.replace(
        "    input()\n    draw()",
        ('    input()\n    print("....")\n    print(".OO.")'),
    )
    verdict = grade(slots, moving)
    assert verdict["verdict"] == "fail"
    assert verdict["reason"] == "rule"
    assert verdict["rule"] == "The board must show exactly one ball."
    assert verdict["turn"] == 1
    assert verdict["inputs"] == ["q"]
    assert verdict["last_screen"] == "....\n.OO."


@POSIX_ONLY
def test_broken_rule_on_the_first_screen_is_turn_zero(slots):
    verdict = grade(slots, "print('....')\nprint('.OO.')\n")
    assert (verdict["reason"], verdict["turn"]) == ("rule", 0)
    assert verdict["inputs"] == []
    assert verdict["last_screen"] == "....\n.OO."


@POSIX_ONLY
def test_plain_script_that_prints_and_exits_passes(slots):
    """A normal `if __name__ == "__main__": main()` script is a program."""
    code = dedent(
        """
        def main():
            print("....")
            print(".O..")


        if __name__ == "__main__":
            main()
        """
    )
    verdict = grade(slots, code, STATIC_CHECK)
    assert verdict["verdict"] == "pass"
    assert verdict["last_screen"] == "....\n.O.."


@POSIX_ONLY
def test_check_script_sees_whether_the_program_finished(slots):
    verdict = grade(slots, BALL_PROGRAM, STATIC_CHECK)
    assert verdict["rule"] == "Print the board and exit."


@POSIX_ONLY
def test_input_after_the_program_exits_fails_as_exited(slots):
    verdict = grade(slots, "print('....')\nprint('.O..')\n")
    assert verdict["reason"] == "exited"
    assert verdict["inputs"] == ["q"]
    assert verdict["last_screen"] == "....\n.O.."


@POSIX_ONLY
def test_crash_fails_with_the_traceback(slots):
    code = "print('.O..')\ninput()\nraise ValueError('bad paddle')\n"
    verdict = grade(slots, code)
    assert verdict["reason"] == "crashed"
    assert "ValueError: bad paddle" in verdict["traceback"]
    assert verdict["inputs"] == ["q"]
    assert verdict["last_screen"] == ".O.."


@POSIX_ONLY
def test_crash_before_the_first_screen_fails(slots):
    verdict = grade(slots, "raise ValueError('no board')\n")
    assert (verdict["reason"], verdict["turn"]) == ("crashed", 0)
    assert verdict["last_screen"] is None
    assert verdict["traceback"].startswith("Traceback")


@POSIX_ONLY
def test_infinite_loop_fails_with_a_timeout(slots):
    limits = SandboxLimits(memory_bytes=None, turn_seconds=0.5)
    code = "print('.O..')\ninput()\nwhile True:\n    pass\n"
    verdict = grade(slots, code, limits=limits)
    assert verdict["reason"] == "turn_timeout"


@POSIX_ONLY
def test_check_script_sees_frames_only(slots):
    """The check script can't find the player's code anywhere it looks."""
    snoop = dedent(
        """
        def check(game):
            screen = game.send("")
            seen = repr(globals()) + repr(dir(game)) + screen
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
    limits = SandboxLimits(memory_bytes=None, turn_seconds=0.5)
    with pytest.raises(CheckScriptError) as error:
        grade(slots, BALL_PROGRAM, broken_script, limits)
    assert isinstance(error.value.stderr, str)


@POSIX_ONLY
def test_check_script_that_plays_forever_is_stopped(slots, monkeypatch):
    monkeypatch.setattr("src.runner.grading.MAX_TURNS", 3)
    endless = "def check(game):\n    while True:\n        game.send()\n"
    with pytest.raises(CheckScriptError, match="too long"):
        grade(slots, BALL_PROGRAM, endless)


@pytest.mark.parametrize(
    "screen",
    ["not json", "[1]", '{"send": 5}', '{"send": "a\\nb"}', '{"done": 1}'],
)
def test_bad_check_messages_are_rejected(screen: str):
    with pytest.raises(CheckScriptError):
        parse_check_request(screen)


def test_good_check_messages_are_accepted():
    assert parse_check_request('{"send": "q"}') == {"send": "q"}
    assert parse_check_request('{"done": true, "rule": null}') == {
        "done": True,
        "rule": None,
    }


def test_harness_program_embeds_the_script():
    program = harness_program("def check(game):\n    pass\n")
    assert program.rstrip().endswith("run('def check(game):\\n    pass\\n')")
    assert "class Game" in program


def test_screen_reply_carries_the_finished_flag():
    assert json.loads(screen_reply("a\nb", True)) == {
        "screen": "a\nb",
        "finished": True,
    }
