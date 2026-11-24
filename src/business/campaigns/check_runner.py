"""
File: check_runner.py
Description: Plays a trusted seed reference solution with a stage's check
    script, locally, for offline campaign validation. Uses the runner's
    own grading code in host mode, because `make validate-campaigns`
    runs on the host, where the runner container isn't reachable.
Author(s): Richard Hall
"""

import tempfile
from pathlib import Path

from src.runner.grading import CheckScriptError, Grader
from src.runner.limits import SandboxLimits
from src.runner.session import LaunchError
from src.runner.slots import Slot, SlotCompromisedError

# macOS rejects the address-space limit, and only trusted code runs here.
LOCAL_LIMITS = SandboxLimits(memory_bytes=None)


class CheckRunError(Exception):
    """The check couldn't be played: the check script or sandbox failed."""


def run_check(code: str, check_script: str) -> dict:
    """Play trusted ``code`` with ``check_script`` and return the verdict.

    This is ONLY for trusted, hand-written seed reference solutions and
    check scripts during offline campaign validation, the same role as
    ``reference_runner.run_reference``. It must NEVER run player code:
    player code is always graded by the runner container (``/grade``).

    Args:
        code: A seed reference solution.
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
