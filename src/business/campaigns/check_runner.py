"""
File: check_runner.py
Description: Plays trusted seed programs locally for offline campaign
    validation: a stage's check script against a program (`run_check`),
    or a program through fixed input lines (`run_screens`). Uses the
    runner's own code in host mode, because `make validate-campaigns`
    runs on the host, where the runner container isn't reachable. Also
    defines `CheckPlayer`, the interface the validator plays through, so
    untrusted campaigns can be validated in the runner instead.
Author(s): Richard Hall, Tyler Black
"""

import sys
import tempfile
from pathlib import Path
from typing import Protocol

from src.runner.grading import CheckScriptError, Grader
from src.runner.limits import SandboxLimits
from src.runner.session import LaunchError, ProgramError, ProgramSession
from src.runner.slots import Slot, SlotCompromisedError

# macOS rejects the address-space limit, and only trusted code runs here.
LOCAL_LIMITS = SandboxLimits(memory_bytes=None)


def host_play_supported() -> bool:
    """Return True if this machine can play programs locally.

    The local player reuses the runner's code, which needs POSIX features
    (``pass_fds``, waiting on pipes, rlimits), so it can't run on Windows.
    There, seeds are only structure-checked; Linux CI plays them all.
    """
    return sys.platform != "win32"


class CheckRunError(Exception):
    """The check couldn't be played: the check script or sandbox failed."""


class CheckPlayer(Protocol):
    """Plays campaign programs for the validator.

    The local functions in this module only accept trusted, hand-written
    seed content. A campaign written by the LLM (US11) must be validated
    with a player that runs everything in the runner container.
    """

    def grade(self, code: str, check_script: str) -> dict:
        """Return the ``/grade`` verdict of ``check_script`` on ``code``."""

    def screens(self, code: str, inputs: list[str]) -> list[str]:
        """Return the screens ``code`` prints, typing ``inputs`` in turn."""


class TrustedSeedPlayer:
    """Plays trusted seed files on the host. Never for untrusted content."""

    def grade(self, code: str, check_script: str) -> dict:
        """Return the verdict of ``check_script`` on ``code``."""
        return run_check(code, check_script)

    def screens(self, code: str, inputs: list[str]) -> list[str]:
        """Return the screens ``code`` prints, typing ``inputs`` in turn."""
        return run_screens(code, inputs)


def run_check(code: str, check_script: str) -> dict:
    """Play trusted ``code`` with ``check_script`` and return the verdict.

    This is ONLY for trusted, hand-written seed programs and check
    scripts during offline campaign validation. It must NEVER run player
    code or LLM-written content: those always go to the runner container.

    Args:
        code: A seed program (reference, broken, or a validator probe).
        check_script: The stage's check script.

    Returns:
        The verdict, in the runner's ``/grade`` reply format.

    Raises:
        CheckRunError: If the check script or the local sandbox failed.
    """
    with (
        tempfile.TemporaryDirectory() as program_dir,
        tempfile.TemporaryDirectory() as check_dir,
    ):
        grader = Grader(LOCAL_LIMITS)
        try:
            return grader.grade(
                Slot(None, Path(program_dir)),
                Slot(None, Path(check_dir)),
                code,
                check_script,
            )
        except CheckScriptError as error:
            detail = error.stderr.strip()
            raise CheckRunError(
                f"check script failed: {error}. {detail}"
            ) from error
        except (LaunchError, SlotCompromisedError) as error:
            raise CheckRunError(
                f"the local sandbox failed: {error}"
            ) from error


def run_screens(code: str, inputs: list[str]) -> list[str]:
    """Play trusted ``code`` through ``inputs`` and return its screens.

    The same trust rule as ``run_check`` applies.

    Args:
        code: A seed program.
        inputs: The lines to type, one each time the program asks.

    Returns:
        The first screen, then the screen after each input line.

    Raises:
        CheckRunError: If the program failed or the sandbox did.
    """
    with tempfile.TemporaryDirectory() as program_dir:
        session = ProgramSession(Slot(None, Path(program_dir)), LOCAL_LIMITS)
        try:
            with session:
                session.start(code)
                screens = [session.first_screen()]
                screens += [session.send(line) for line in inputs]
                return screens
        except ProgramError as error:
            raise CheckRunError(
                f"the program failed: {error.status}. {session.stderr}"
            ) from error
        except (LaunchError, SlotCompromisedError) as error:
            raise CheckRunError(
                f"the local sandbox failed: {error}"
            ) from error
