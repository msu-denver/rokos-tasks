"""
File: harness.py
Description: The check-script harness. Runs inside its own sandbox slot:
    the runner writes this file plus `run(<check script>)` as main.py.
    The check script gets a `game` object; each `game.tick(line)` becomes
    a one-line JSON request to the runner, which ticks the player's
    program and answers with the frame. The check script never sees the
    player's code. Standard library only.
Author(s): Richard Hall
"""

import json
import sys
from typing import TextIO

FRAME_END = "---"
DEFAULT_RULE = "A stage rule was broken."


class RuleBrokenError(Exception):
    """Raised by a check script when the program breaks a stage rule."""


class Frame(str):
    """One frame the player's program printed, with small grid helpers."""

    @property
    def rows(self) -> list[str]:
        """Return the frame's lines (an empty frame has no rows)."""
        return self.split("\n") if self else []

    def find(self, char: str) -> list[tuple[int, int]]:
        """Return the ``(row, column)`` of every ``char`` in the frame."""
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
        """Send one message as a single JSON line, then the frame end."""
        self._writer.write(f"{json.dumps(message)}\n{FRAME_END}\n")
        self._writer.flush()

    def request(self, message: dict) -> dict:
        """Send ``message`` and return the runner's one-line JSON reply."""
        self.send(message)
        reply = self._reader.readline()
        if not reply:
            raise EOFError("the runner closed the channel")
        return json.loads(reply)


class Game:
    """What a check script uses to play the player's program."""

    def __init__(self, channel: Channel) -> None:
        """Play through ``channel``."""
        self._channel = channel

    def tick(self, line: str = "") -> Frame:
        """Send one input line to the program and return its frame.

        Args:
            line: The keys pressed this tick, or "" for none.

        Returns:
            The frame the program printed.
        """
        if not isinstance(line, str) or "\n" in line or "\r" in line:
            raise ValueError("a tick's input must be one line of text")
        return Frame(self._channel.request({"tick": line})["frame"])

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

    Sends ``{"done": true, "rule": null}`` if every rule held, or the
    broken rule's text. Any other error crashes this process, which the
    runner reports as a check-script error, never as the player's fault.

    Args:
        check_source: The check script. It defines ``check(game)``.
        reader: Messages from the runner (stdin by default).
        writer: Messages to the runner (stdout by default).
    """
    reader = reader or sys.stdin
    channel = Channel(reader, writer or sys.stdout)
    reader.readline()
    # A stray print in the check script must not corrupt the protocol.
    real_stdout, sys.stdout = sys.stdout, sys.stderr
    rule = None
    try:
        namespace: dict = {"__name__": "check_script"}
        exec(compile(check_source, "check_script.py", "exec"), namespace)
        namespace["check"](Game(channel))
    except RuleBrokenError as broken:
        rule = str(broken) or DEFAULT_RULE
    finally:
        sys.stdout = real_stdout
    channel.send({"done": True, "rule": rule})
