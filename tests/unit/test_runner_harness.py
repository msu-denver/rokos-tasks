"""
File: test_runner_harness.py
Description: Unit tests for the check-script harness, run in-process with
    a scripted runner on the other end of the line protocol: the Screen
    helpers, game.screen/send/finished/check/fail, the done message, and
    stdout safety.
Author(s): Richard Hall, Tyler Black
"""

import io
import json
import sys

import pytest

from src.runner.harness import Game, RuleBrokenError, Screen, run


class ScriptedRunner:
    """Plays the runner's side: the first screen, then one per send."""

    def __init__(self, screens: list[str], finished_last: bool = False):
        """Reply with ``screens`` in order; the last may be finished."""
        replies = [
            {
                "screen": screen,
                "finished": finished_last and index == len(screens) - 1,
            }
            for index, screen in enumerate(screens)
        ]
        lines = [json.dumps(reply) for reply in replies]
        self.reader = io.StringIO("".join(line + "\n" for line in lines))
        self.writer = io.StringIO()

    def messages(self) -> list[dict]:
        """Return every message the harness sent, decoded."""
        return [
            json.loads(line) for line in self.writer.getvalue().splitlines()
        ]


def run_script(
    source: str, screens: list[str], finished_last: bool = False
) -> list[dict]:
    runner = ScriptedRunner(screens, finished_last)
    run(source, runner.reader, runner.writer)
    return runner.messages()


def test_screen_rows_and_find():
    screen = Screen("..O\n|..\n..|")
    assert screen.rows == ["..O", "|..", "..|"]
    assert screen.find("|") == [(1, 0), (2, 2)]
    assert screen.find("O") == [(0, 2)]
    assert Screen("").rows == []


def test_passing_script_sends_lines_then_done():
    source = (
        "def check(game):\n"
        "    game.check(game.screen() == 'start', 'first screen')\n"
        "    screen = game.send('q')\n"
        "    game.check(screen.find('O') == [(0, 0)], 'ball at top left')\n"
        "    game.check(game.screen() is screen, 'screen is the latest')\n"
        "    game.send()\n"
    )
    assert run_script(source, ["start", "O.", ".."]) == [
        {"send": "q"},
        {"send": ""},
        {"done": True, "rule": None},
    ]


def test_check_script_that_sends_nothing_reads_the_first_screen():
    source = (
        "def check(game):\n"
        "    game.check(game.screen().rows == ['.O.'], 'one ball')\n"
        "    game.check(game.finished, 'exits')\n"
    )
    messages = run_script(source, [".O."], finished_last=True)
    assert messages == [{"done": True, "rule": None}]


def test_finished_follows_the_latest_reply():
    source = (
        "def check(game):\n"
        "    game.check(not game.finished, 'still running')\n"
        "    game.send('x')\n"
        "    game.check(not game.finished, 'program exited')\n"
    )
    messages = run_script(source, ["a", "b"], finished_last=True)
    assert messages[-1] == {"done": True, "rule": "program exited"}


def test_broken_rule_is_reported():
    source = (
        "def check(game):\n"
        "    screen = game.screen()\n"
        "    game.check(len(screen.find('O')) == 1, 'Exactly one ball.')\n"
    )
    messages = run_script(source, ["OO"])
    assert messages[-1] == {"done": True, "rule": "Exactly one ball."}


def test_fail_with_empty_rule_uses_the_default():
    messages = run_script("def check(game):\n    game.fail('')\n", [""])
    assert messages == [{"done": True, "rule": "A stage rule was broken."}]


def test_stray_print_goes_to_stderr(capsys):
    source = "def check(game):\n    print('debugging')\n    game.send()\n"
    messages = run_script(source, ["first", "second"])
    assert messages == [{"send": ""}, {"done": True, "rule": None}]
    assert "debugging" in capsys.readouterr().err
    assert sys.stdout is not sys.stderr


def test_script_errors_crash_the_harness():
    with pytest.raises(KeyError):
        run_script("x = 1\n", [""])
    with pytest.raises(ZeroDivisionError):
        run_script("def check(game):\n    1 / 0\n", [""])


def test_closed_channel_is_an_error():
    with pytest.raises(EOFError):
        run_script("def check(game):\n    game.send()\n", [""])
    with pytest.raises(EOFError):
        run_script("def check(game):\n    pass\n", [])


@pytest.mark.parametrize("line", ["a\nb", "a\rb", 5])
def test_input_must_be_one_line(line: object):
    game = Game(channel=None, first={"screen": "", "finished": False})
    with pytest.raises(ValueError, match="one line"):
        game.send(line)


def test_check_passes_on_true_condition():
    game = Game(channel=None, first={"screen": "", "finished": False})
    game.check(True, "never raised")
    with pytest.raises(RuleBrokenError, match="raised"):
        game.check(0, "raised")
