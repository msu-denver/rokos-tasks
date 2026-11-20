"""
File: reference_runner.py
Description: Subprocess execution for trusted seed reference solutions.
Author(s): Tyler Black
"""

import subprocess
import sys
from dataclasses import dataclass


class ReferenceRunnerError(Exception):
    """Base exception for errors during reference solution execution."""


class ReferenceTimeoutError(ReferenceRunnerError):
    """Raised when a reference solution exceeds its execution time limit."""


class ReferenceExecutionError(ReferenceRunnerError):
    """Raised when a reference solution exits with a non-zero exit code."""

    def __init__(
        self,
        message: str,
        returncode: int,
        stderr: str,
        stdout: str,
    ) -> None:
        """Initialize with execution details."""
        super().__init__(message)
        self.returncode = returncode
        self.stderr = stderr
        self.stdout = stdout


@dataclass(frozen=True)
class ReferenceRunResult:
    """Execution output and exit status of a reference run."""

    stdout: str
    stderr: str
    returncode: int

    @property
    def success(self) -> bool:
        """Return True if execution finished with exit code 0."""
        return self.returncode == 0


def run_reference(
    code: str,
    input_text: str = "",
    timeout: float = 5.0,
    check: bool = False,
) -> ReferenceRunResult:
    """Execute a trusted seed reference solution in an isolated subprocess.

    This runner is ONLY for trusted, hand-written seed reference
    solutions during offline campaign validation and output generation.
    It must NEVER be used to run untrusted player code; player code is
    always executed within the isolated Docker sandbox runner built in US6.

    Args:
        code: Python source code of the reference solution.
        input_text: Stdin input to feed to the program.
        timeout: Maximum wall-clock seconds before timing out. Default is 5.
        check: If True, raise ReferenceExecutionError on non-zero exit code.

    Returns:
        ReferenceRunResult containing stdout, stderr, and returncode.

    Raises:
        ReferenceTimeoutError: If execution exceeds the specified timeout.
        ReferenceExecutionError: If check is True and returncode is non-zero.
    """
    try:
        proc = subprocess.run(
            [sys.executable, "-I", "-c", code],
            input=input_text,
            capture_output=True,
            timeout=timeout,
            text=True,
        )
    except subprocess.TimeoutExpired as exc:
        raise ReferenceTimeoutError(
            f"Reference solution timed out after {timeout} seconds."
        ) from exc

    result = ReferenceRunResult(
        stdout=proc.stdout,
        stderr=proc.stderr,
        returncode=proc.returncode,
    )
    if check and not result.success:
        raise ReferenceExecutionError(
            f"Reference solution exited with code {proc.returncode}: "
            f"{proc.stderr.strip()}",
            returncode=proc.returncode,
            stderr=proc.stderr,
            stdout=proc.stdout,
        )
    return result
