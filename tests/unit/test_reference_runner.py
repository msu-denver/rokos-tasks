"""
File: test_reference_runner.py
Description: Unit tests for isolated reference solution execution runner.
Author(s): Tyler Black
"""

import pytest

from src.business.campaigns.reference_runner import (
    ReferenceExecutionError,
    ReferenceRunResult,
    ReferenceTimeoutError,
    run_reference,
)


class TestReferenceRunner:
    """Test suite for trusted reference solution subprocess runner."""

    def test_successful_run(self) -> None:
        """Verify normal execution captures stdout and returns success."""
        code = "print('hello world')"
        result = run_reference(code)
        assert isinstance(result, ReferenceRunResult)
        assert result.success is True
        assert result.returncode == 0
        assert result.stdout.strip() == "hello world"
        assert result.stderr == ""

    def test_run_with_stdin_input(self) -> None:
        """Verify stdin text is properly piped to the subprocess."""
        code = "name = input()\nprint(f'Hello, {name}!')"
        result = run_reference(code, input_text="Alice")
        assert result.success is True
        assert result.stdout.strip() == "Hello, Alice!"

    def test_execution_timeout(self) -> None:
        """Verify that a hanging process raises ReferenceTimeoutError."""
        code = "import time\ntime.sleep(2)"
        with pytest.raises(ReferenceTimeoutError) as exc_info:
            run_reference(code, timeout=0.1)
        assert "timed out after 0.1 seconds" in str(exc_info.value)

    def test_non_zero_exit_without_check(self) -> None:
        """Verify non-zero exit returns failure result when check is False."""
        code = "import sys\nprint('err output', file=sys.stderr)\nsys.exit(42)"
        result = run_reference(code, check=False)
        assert result.success is False
        assert result.returncode == 42
        assert "err output" in result.stderr

    def test_non_zero_exit_with_check(self) -> None:
        """Verify non-zero exit raises ReferenceExecutionError if checked."""
        code = "raise ValueError('invalid value')"
        with pytest.raises(ReferenceExecutionError) as exc_info:
            run_reference(code, check=True)
        assert exc_info.value.returncode != 0
        assert "ValueError: invalid value" in exc_info.value.stderr

    def test_runner_docstring_mentions_seed_only(self) -> None:
        """Ensure docstring warns this is strictly for seed references."""
        doc = run_reference.__doc__
        assert doc is not None
        assert "ONLY for trusted" in doc
        assert "never player code" in doc.lower() or "NEVER" in doc
