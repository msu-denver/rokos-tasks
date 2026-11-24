"""
File: validator.py
Description: Validates campaign definitions against schema and quality rules.
Author(s): Tyler Black
"""

import ast
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from src.business.campaigns.check_runner import CheckRunError, run_check
from src.business.campaigns.reference_runner import (
    ReferenceTimeoutError,
    run_reference,
)
from src.business.difficulty import Difficulty

SCHEMA_PATH = (
    Path(__file__).resolve().parents[3]
    / "content"
    / "campaigns"
    / "schema.json"
)

# Two passes catch a check script that depends on luck (a random serve).
CHECK_PASS_RUNS = 2


def check_script_problems(source: str) -> list[str]:
    """Return what breaks the check-script rules, or an empty list.

    A check script imports nothing and defines ``check(game)``; it gets
    everything it needs from ``game`` (game-design §4.4).

    Args:
        source: The check script's Python source.

    Returns:
        One message per problem.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError as error:
        return [f"check_script has a syntax error on line {error.lineno}."]
    problems = []
    if any(
        isinstance(node, ast.Import | ast.ImportFrom)
        for node in ast.walk(tree)
    ):
        problems.append("check_script must not import anything.")
    if not any(_is_check_function(node) for node in tree.body):
        problems.append("check_script must define check(game).")
    return problems


def _is_check_function(node: ast.stmt) -> bool:
    """Return True if ``node`` is ``def check(<one parameter>):``."""
    if not isinstance(node, ast.FunctionDef) or node.name != "check":
        return False
    arguments = node.args
    return len(arguments.args) == 1 and not (
        arguments.posonlyargs
        or arguments.kwonlyargs
        or arguments.vararg
        or arguments.kwarg
    )


def _describe(verdict: dict) -> str:
    """Return the broken rule, or how the program failed."""
    if verdict["reason"] == "rule":
        return f"rule: {verdict['rule']}"
    return f"the program {verdict['reason']} at tick {verdict['tick']}"


def normalize_output(text: str) -> str:
    """Normalize program output by stripping trailing whitespace.

    Strips trailing whitespace from each line and strips trailing
    blank lines.

    Args:
        text: Raw output string.

    Returns:
        Normalized output string.
    """
    lines = [line.rstrip() for line in text.splitlines()]
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines)


class CampaignValidator:
    """Validates campaign structures, difficulty rules, and references."""

    _schema: dict[str, Any] | None = None

    @classmethod
    def _get_schema(cls) -> dict[str, Any]:
        """Load and cache the campaign JSON Schema."""
        if cls._schema is None:
            if not SCHEMA_PATH.exists():
                raise FileNotFoundError(
                    f"Campaign schema not found at {SCHEMA_PATH}"
                )
            cls._schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        return cls._schema

    @classmethod
    def validate_file(cls, path: Path | str) -> list[str]:
        """Validate a campaign JSON file on disk.

        Args:
            path: Path to the JSON file.

        Returns:
            List of error messages, or an empty list if valid.
        """
        file_path = Path(path)
        if not file_path.exists():
            return [f"[{file_path}] File does not exist."]
        try:
            data = json.loads(file_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            return [f"[{file_path}] Invalid JSON: {exc}"]
        return cls.validate(data, filename=str(file_path))

    @classmethod
    def validate(
        cls, data: dict[str, Any], filename: str = "<campaign>"
    ) -> list[str]:
        """Validate a parsed campaign dictionary against all checks.

        Args:
            data: Parsed campaign data dictionary.
            filename: Source filename or identifier for reporting.

        Returns:
            List of validation error messages, or empty if valid.
        """
        errors: list[str] = []

        schema = cls._get_schema()
        schema_validator = Draft202012Validator(schema)
        schema_errors = sorted(
            schema_validator.iter_errors(data), key=lambda e: e.path
        )
        for s_err in schema_errors:
            loc = "/".join(str(p) for p in s_err.path) or "root"
            errors.append(
                f"[{filename}] Schema error at '{loc}': {s_err.message}"
            )
            if s_err.validator == "minItems" and loc.endswith("/samples"):
                stage_index = int(s_err.path[1]) + 1
                errors.append(
                    f"[{filename}] Stage {stage_index}: expected 1-2 samples, "
                    "found 0."
                )
        if errors:
            return errors

        diff_value = data.get("difficulty")
        valid_tiers = {d.value for d in Difficulty}
        if not diff_value or diff_value not in valid_tiers:
            return errors

        stages = data.get("stages")
        if not isinstance(stages, list):
            return errors

        difficulty = Difficulty(diff_value)
        expected_stages = difficulty.rules.stages
        if len(stages) != expected_stages:
            errors.append(
                f"[{filename}] Tier '{difficulty.value}' requires "
                f"{expected_stages} stages, but found {len(stages)}."
            )

        for idx, stage in enumerate(stages, start=1):
            if not isinstance(stage, dict):
                continue
            stage_num = stage.get("stage")
            if stage_num != idx:
                errors.append(
                    f"[{filename}] Stage index {idx}: expected stage number "
                    f"{idx}, got {stage_num}."
                )

        for stage in stages:
            if not isinstance(stage, dict):
                continue
            stage_num = stage.get("stage", "?")
            samples = stage.get("samples")
            if not isinstance(samples, list) or not (1 <= len(samples) <= 2):
                count = len(samples) if isinstance(samples, list) else 0
                errors.append(
                    f"[{filename}] Stage {stage_num}: expected 1-2 samples, "
                    f"found {count}."
                )

        for stage in stages:
            if not isinstance(stage, dict):
                continue
            stage_num = stage.get("stage", "?")
            prompt = stage.get("prompt", "")
            samples = stage.get("samples", [])
            if not isinstance(samples, list):
                continue
            for s_idx, sample in enumerate(samples, start=1):
                if not isinstance(sample, dict):
                    continue
                sample_in = sample.get("input", "")
                for line in sample_in.splitlines():
                    stripped = line.strip()
                    if stripped and stripped not in prompt:
                        errors.append(
                            f"[{filename}] Stage {stage_num} sample {s_idx}: "
                            f"input line '{line}' does not appear in prompt."
                        )
                sample_out = sample.get("expected_output", "")
                for line in sample_out.splitlines():
                    stripped = line.strip()
                    if stripped and stripped not in prompt:
                        errors.append(
                            f"[{filename}] Stage {stage_num} sample {s_idx}: "
                            f"expected output line '{line}' does not appear "
                            f"in prompt."
                        )

        for stage in stages:
            if not isinstance(stage, dict):
                continue
            # The editor always starts empty: every line is the player's.
            stage_num = stage.get("stage")
            starter = stage.get("starter_code")
            if stage_num is not None and starter is not None:
                errors.append(
                    f"[{filename}] Stage {stage_num}: starter_code must "
                    f"be null, got {starter!r}."
                )

        for stage in stages:
            if not isinstance(stage, dict):
                continue
            stage_num = stage.get("stage", "?")
            ref_code = stage.get("reference_solution")
            if not ref_code or not isinstance(ref_code, str):
                continue

            cls._validate_stage_tests(
                stage=stage,
                stage_num=stage_num,
                ref_code=ref_code,
                filename=filename,
                errors=errors,
            )

        cls._validate_incremental_contracts(
            stages=stages,
            filename=filename,
            errors=errors,
        )
        cls._validate_check_scripts(stages, filename, errors)

        return errors

    @classmethod
    def _validate_check_scripts(
        cls, stages: list[Any], filename: str, errors: list[str]
    ) -> None:
        """Check each stage's check script and play the references on it."""
        previous_reference = None
        for stage in stages:
            if not isinstance(stage, dict):
                continue
            script = stage.get("check_script")
            reference = stage.get("reference_solution")
            if script:
                prefix = f"[{filename}] Stage {stage.get('stage', '?')}"
                problems = check_script_problems(script) or cls._play_check(
                    script, reference, previous_reference
                )
                errors.extend(f"{prefix}: {problem}" for problem in problems)
            previous_reference = reference

    @classmethod
    def _play_check(
        cls, script: str, reference: str, previous_reference: str | None
    ) -> list[str]:
        """Return problems found by playing the references on ``script``.

        The stage's reference must pass on every run, and the previous
        stage's reference must fail, or the stage adds nothing new.
        """
        try:
            for attempt in range(1, CHECK_PASS_RUNS + 1):
                verdict = run_check(reference, script)
                if verdict["verdict"] != "pass":
                    return [
                        "reference solution failed its check script on "
                        f"run {attempt} of {CHECK_PASS_RUNS} "
                        f"({_describe(verdict)})."
                    ]
            if previous_reference and (
                run_check(previous_reference, script)["verdict"] == "pass"
            ):
                return [
                    "the previous stage's reference solution passes this "
                    "check script, so the stage adds nothing new."
                ]
        except CheckRunError as error:
            return [str(error)]
        return []

    @classmethod
    def _validate_stage_tests(
        cls,
        stage: dict[str, Any],
        stage_num: Any,
        ref_code: str,
        filename: str,
        errors: list[str],
    ) -> None:
        """Validate sample and hidden test outputs against reference stdout."""
        for s_idx, sample in enumerate(stage.get("samples", []), start=1):
            if not isinstance(sample, dict):
                continue
            cls._check_test_case(
                ref_code=ref_code,
                test_case=sample,
                kind="sample",
                idx=s_idx,
                stage_num=stage_num,
                filename=filename,
                errors=errors,
            )

        for h_idx, hidden in enumerate(stage.get("hidden_tests", []), start=1):
            if not isinstance(hidden, dict):
                continue
            cls._check_test_case(
                ref_code=ref_code,
                test_case=hidden,
                kind="hidden_test",
                idx=h_idx,
                stage_num=stage_num,
                filename=filename,
                errors=errors,
            )

    @classmethod
    def _check_test_case(
        cls,
        ref_code: str,
        test_case: dict[str, Any],
        kind: str,
        idx: int,
        stage_num: Any,
        filename: str,
        errors: list[str],
    ) -> None:
        """Check a test case against two runs of the reference solution."""
        inp = test_case.get("input", "")
        expected = test_case.get("expected_output", "")
        try:
            res = run_reference(ref_code, inp)
            if not res.success:
                errors.append(
                    f"[{filename}] Stage {stage_num} {kind} {idx}: reference "
                    f"solution exited with code {res.returncode}: "
                    f"{res.stderr.strip()}"
                )
                return
            repeated = run_reference(ref_code, inp)
            if not repeated.success or repeated.stdout != res.stdout:
                errors.append(
                    f"[{filename}] Stage {stage_num} {kind} {idx}: reference "
                    "solution is non-deterministic (runs did not agree)."
                )
            if normalize_output(res.stdout) != normalize_output(expected):
                errors.append(
                    f"[{filename}] Stage {stage_num} {kind} {idx}: "
                    f"expected output does not match reference stdout."
                )
        except ReferenceTimeoutError:
            errors.append(
                f"[{filename}] Stage {stage_num} {kind} {idx}: "
                f"reference solution timed out."
            )

    @classmethod
    def _validate_incremental_contracts(
        cls,
        stages: list[Any],
        filename: str,
        errors: list[str],
    ) -> None:
        """Verify that stage N's hidden tests fail stage N-1's reference."""
        for idx in range(1, len(stages)):
            prev_stage = stages[idx - 1]
            curr_stage = stages[idx]
            if not isinstance(prev_stage, dict) or not isinstance(
                curr_stage, dict
            ):
                continue

            prev_stage_num = prev_stage.get("stage", idx)
            curr_stage_num = curr_stage.get("stage", idx + 1)
            prev_ref = prev_stage.get("reference_solution")
            curr_hidden = curr_stage.get("hidden_tests", [])

            if (
                not prev_ref
                or not isinstance(curr_hidden, list)
                or not curr_hidden
            ):
                continue

            all_passed = True
            for hidden in curr_hidden:
                if not isinstance(hidden, dict):
                    continue
                inp = hidden.get("input", "")
                expected = hidden.get("expected_output", "")
                try:
                    res = run_reference(prev_ref, inp)
                    if not res.success or normalize_output(
                        res.stdout
                    ) != normalize_output(expected):
                        all_passed = False
                        break
                except ReferenceTimeoutError:
                    all_passed = False
                    break

            if all_passed:
                errors.append(
                    f"[{filename}] Stage {curr_stage_num}: hidden tests "
                    f"did not fail stage {prev_stage_num} reference "
                    f"solution."
                )
