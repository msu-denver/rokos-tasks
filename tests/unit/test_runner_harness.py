"""
File: test_runner_harness.py
Description: Unit tests for the check-script harness, run in-process with
    a scripted runner on the other end of the line protocol: the Frame
    helpers, game.tick/check/fail, the done message, and stdout safety.
Author(s): Richard Hall
"""

import io
import json
import sys

import pytest

from src.runner.harness import Frame, Game, RuleBrokenError, run


class ScriptedRunner:
    """Plays the runner's side: answers each tick request with a frame."""

    def __init__(self, frames: list[str]) -> None:
        """Answer the start line, then one tick request per frame."""
        replies = ["start"] + [json.dumps({"frame": f}) for f in frames]
        self.reader = io.StringIO("\n".join(replies) + "\n")
        self.writer = io.StringIO()

    def messages(self) -> list[dict]:
        """Return every message the harness sent, decoded."""
        chunks = self.writer.getvalue().split("\n---\n")
        return [json.loads(chunk) for chunk in chunks if chunk]


def run_script(source: str, frames: list[str]) -> list[dict]:
    runner = ScriptedRunner(frames)
    run(source, runner.reader, runner.writer)
    return runner.messages()


def test_frame_rows_and_find():
    frame = Frame("..O\n|..\n..|")
    assert frame.rows == ["..O", "|..", "..|"]
    assert frame.find("|") == [(1, 0), (2, 2)]
    assert frame.find("O") == [(0, 2)]
    assert Frame("").rows == []


def test_passing_script_sends_ticks_then_done():
    source = (
        "def check(game):\n"
        "    frame = game.tick('q')\n"
        "    game.check(frame.find('O') == [(0, 0)], 'ball at top left')\n"
        "    game.tick()\n"
    )
    assert run_script(source, ["O.", ".."]) == [
        {"tick": "q"},
        {"tick": ""},
        {"done": True, "rule": None},
    ]


def test_broken_rule_is_reported():
    source = (
        "def check(game):\n"
        "    frame = game.tick()\n"
        "    game.check(len(frame.find('O')) == 1, 'Exactly one ball.')\n"
    )
    messages = run_script(source, ["OO"])
    assert messages[-1] == {"done": True, "rule": "Exactly one ball."}


def test_fail_with_empty_rule_uses_the_default():
    messages = run_script("def check(game):\n    game.fail('')\n", [])
    assert messages == [{"done": True, "rule": "A stage rule was broken."}]


def test_stray_print_goes_to_stderr(capsys):
    source = "def check(game):\n    print('debugging')\n    game.tick()\n"
    messages = run_script(source, ["frame"])
    assert messages == [{"tick": ""}, {"done": True, "rule": None}]
    assert "debugging" in capsys.readouterr().err
    assert sys.stdout is not sys.stderr


def test_script_errors_crash_the_harness():
    with pytest.raises(KeyError):
        run_script("x = 1\n", [])
    with pytest.raises(ZeroDivisionError):
        run_script("def check(game):\n    1 / 0\n", [])


def test_closed_channel_is_an_error():
    runner = ScriptedRunner([])
    with pytest.raises(EOFError):
        run(
            "def check(game):\n    game.tick()\n", runner.reader, runner.writer
        )


@pytest.mark.parametrize("line", ["a\nb", "a\rb", 5])
def test_tick_input_must_be_one_line(line: object):
    with pytest.raises(ValueError, match="one line"):
        Game(channel=None).tick(line)


def test_check_passes_on_true_condition():
    Game(channel=None).check(True, "never raised")
    with pytest.raises(RuleBrokenError, match="raised"):
        Game(channel=None).check(0, "raised")
