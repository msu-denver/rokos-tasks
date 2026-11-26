"""
File: harness.py
Description: The check-script harness. Runs inside its own sandbox slot:
    the runner writes this file plus `run(<check script>)` as main.py.
    The check script gets a `game` object: `game.screen()` is what the
    player's program printed so far, `game.send(line)` types one input
    line and returns the next screen, and `game.finished` says whether
    the program has exited. Each send is a one-line JSON request to the
    runner, which plays it on the player's program. The check script
    never sees the player's code. Standard library only.
Author(s): Richard Hall, Tyler Black
"""

import json
import sys
from typing import TextIO

DEFAULT_RULE = "A stage rule was broken."


class RuleBrokenError(Exception):
    """Raised by a check script when the program breaks a stage rule."""


class Screen(str):
    """One screen the player's program printed, with small grid helpers."""

    @property
    def rows(self) -> list[str]:
        """Return the screen's lines (an empty screen has no rows)."""
        return self.split("\n") if self else []

    def find(self, char: str) -> list[tuple[int, int]]:
        """Return the ``(row, column)`` of every ``char`` on the screen."""
        return [
            (row_index, column)
            for row_index, row in enumerate(self.rows)
            for column, cell in enumerate(row)
            if cell == char
        ]


class Channel:
    """The line protocol between this harness and the runner server."""

    def __init__(self, reader: TextIO, writer: TextIO) -> None:
        """Talk over ``reader`` (from the runner) and ``writer`` (to it)."""
        self._reader = reader
        self._writer = writer

    def send(self, message: dict) -> None:
        """Send one message as a single JSON line."""
        self._writer.write(f"{json.dumps(message)}\n")
        self._writer.flush()

    def receive(self) -> dict:
        """Return the runner's next one-line JSON message."""
        reply = self._reader.readline()
        if not reply:
            raise EOFError("the runner closed the channel")
        return json.loads(reply)

    def request(self, message: dict) -> dict:
        """Send ``message`` and return the runner's reply."""
        self.send(message)
        return self.receive()


class Game:
    """What a check script uses to play the player's program."""

    def __init__(self, channel: Channel, first: dict) -> None:
        """Play through ``channel``, starting from the ``first`` screen."""
        self._channel = channel
        self._update(first)

    def _update(self, reply: dict) -> None:
        """Keep the screen and finished flag from a runner reply."""
        self._screen = Screen(reply["screen"])
        self._finished = bool(reply["finished"])

    def screen(self) -> Screen:
        """Return what the program printed since it last asked for input.

        Before any ``send``, that is everything it printed first. Once
        the program has exited, it is what it printed last.
        """
        return self._screen

    @property
    def finished(self) -> bool:
        """Return True once the program has exited cleanly."""
        return self._finished

    def send(self, line: str = "") -> Screen:
        """Type ``line`` as the program's input and return the next screen.

        Sending to a program that has already exited fails the run.

        Args:
            line: One line of input, or "" for an empty line.

        Returns:
            Everything the program printed until it asked for input
            again or exited.
        """
        if not isinstance(line, str) or "\n" in line or "\r" in line:
            raise ValueError("an input must be one line of text")
        self._update(self._channel.request({"send": line}))
        return self._screen

    def check(self, condition: object, rule: str) -> None:
        """Fail with ``rule`` unless ``condition`` is true."""
        if not condition:
            raise RuleBrokenError(rule)

    def fail(self, rule: str) -> None:
        """Fail with ``rule``."""
        raise RuleBrokenError(rule)


def run(
    check_source: str,
    reader: TextIO | None = None,
    writer: TextIO | None = None,
) -> None:
    """Run a check script against the player's program.

    The runner first sends the program's first screen. Ends by sending
    ``{"done": true, "rule": null}`` if every rule held, or the broken
    rule's text. Any other error crashes this process, which the runner
    reports as a check-script error, never as the player's fault.

    Args:
        check_source: The check script. It defines ``check(game)``.
        reader: Messages from the runner (stdin by default).
        writer: Messages to the runner (stdout by default).
    """
    channel = Channel(reader or sys.stdin, writer or sys.stdout)
    first = channel.receive()
    # A stray print in the check script must not corrupt the protocol.
    real_stdout, sys.stdout = sys.stdout, sys.stderr
    rule = None
    try:
        namespace: dict = {"__name__": "check_script"}
        exec(compile(check_source, "check_script.py", "exec"), namespace)
        namespace["check"](Game(channel, first))
    except RuleBrokenError as broken:
        rule = str(broken) or DEFAULT_RULE
    finally:
        sys.stdout = real_stdout
    channel.send({"done": True, "rule": rule})
