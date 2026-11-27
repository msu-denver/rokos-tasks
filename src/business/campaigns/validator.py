"""
File: validator.py
Description: Validates campaign definitions against the schema and the
    automated quality checks in game-design §4.4: every stage is graded
    only by its check script, which must pass the reference program,
    fail the broken program, the previous stage's reference, an empty
    program, and (from Stage 2 on) a program that prints one fixed screen
    every time it asks for input.
Author(s): Tyler Black, Richard Hall, Steph Rivera
"""

import ast
import json
import re
import time
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from src.business.campaigns.check_runner import (
    CheckPlayer,
    CheckRunError,
    TrustedSeedPlayer,
    host_play_supported,
)
from src.business.difficulty import Difficulty
from src.runner.grading import CHECK_SCRIPT_BYTES
from src.runner.limits import PRODUCTION_LIMITS

SCHEMA_PATH = (
    Path(__file__).resolve().parents[3]
    / "content"
    / "campaigns"
    / "schema.json"
)

# Three passes catch a check script that depends on luck (a random serve).
CHECK_PASS_RUNS = 3
# The reference must finish the checks in under this share of the time
# limit, so a reasonable program never times out (§4.4).
TIME_BUDGET_SECONDS = PRODUCTION_LIMITS.run_seconds * 0.10
# Digits per number in the "huge numbers" probe: past int()'s default
# 4,300-digit cap, so an unbounded int() in a check script crashes on it.
HUGE_NUMBER_DIGITS = 5000
# The probe makes one number huge at a time, for at most this many numbers
# on the reference's first screen, so a check that bounds the first number
# still has to bound the next.
MAX_HUGE_NUMBER_PROBES = 6
# Programs that follow no stage's rules. A check script must fail each
# one cleanly: if odd screens crash it, a player could print them on
# purpose to get a check_error instead of losing a life.
_SCREEN_LOOP = "while True:\n    print({screen})\n    input()\n"
JUNK_PROGRAMS = {
    "an empty program": "",
    "a program that only prints ?": "print('?')\n",
    "empty screens": "while True:\n    input()\n",
    "a screen of ? every turn": _SCREEN_LOOP.format(screen="'?'"),
    "echoed input": "while True:\n    print(input())\n",
}
# Built-ins that reach outside the helper API (files, code, attributes).
FORBIDDEN_NAMES = frozenset(
    {
        "breakpoint",
        "compile",
        "delattr",
        "eval",
        "exec",
        "getattr",
        "globals",
        "input",
        "locals",
        "open",
        "setattr",
        "vars",
    }
)
_DIGITS = re.compile(r"\d+")


def check_script_problems(source: str) -> list[str]:
    """Return what breaks the check-script rules, or an empty list.

    A check script defines ``check(game)``, stays under the size cap, and
    uses only the helper API: it imports nothing, calls no built-in that
    reaches files, code, or attributes, and touches no dunder name
    (game-design §4.4).

    Args:
        source: The check script's Python source.

    Returns:
        One message per problem.
    """
    if len(source.encode()) > CHECK_SCRIPT_BYTES:
        return [f"check_script is larger than {CHECK_SCRIPT_BYTES} bytes."]
    try:
        tree = ast.parse(source)
    except SyntaxError as error:
        return [f"check_script has a syntax error on line {error.lineno}."]
    problems = []
    nodes = list(ast.walk(tree))
    if any(isinstance(node, ast.Import | ast.ImportFrom) for node in nodes):
        problems.append("check_script must not import anything.")
    names = sorted({name for node in nodes if (name := _forbidden_name(node))})
    if names:
        problems.append(
            "check_script may only use the helper API, not "
            + ", ".join(names)
            + "."
        )
    if not any(_is_check_function(node) for node in tree.body):
        problems.append("check_script must define check(game).")
    return problems


def _forbidden_name(node: ast.AST) -> str | None:
    """Return the forbidden name or dunder that ``node`` uses, if any."""
    if isinstance(node, ast.Name):
        name = node.id
    elif isinstance(node, ast.Attribute):
        name = node.attr
    else:
        return None
    if name in FORBIDDEN_NAMES or name.startswith("__"):
        return name
    return None


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
    return f"the program {verdict['reason']} at turn {verdict['turn']}"


def screen_program(screen: str) -> str:
    """Return a program that prints ``screen`` each time before input."""
    return _SCREEN_LOOP.format(screen=f"{screen!r}")


def static_program(screen: str) -> str:
    """Return a program that prints ``screen`` once and exits."""
    return f"print({screen!r})\n"


def huge_number_screens(screen: str) -> list[str]:
    """Return copies of ``screen`` with one of its numbers made huge."""
    return [
        screen[: number.start()]
        + "9" * HUGE_NUMBER_DIGITS
        + screen[number.end() :]
        for number in list(_DIGITS.finditer(screen))[:MAX_HUGE_NUMBER_PROBES]
    ]


class CampaignValidator:
    """Validates campaign structure, tier rules, and check scripts."""

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
        """Validate a trusted campaign JSON file on disk.

        On a machine that can't play programs (Windows), only the checks
        that don't play anything run; Linux CI runs the rest.

        Args:
            path: Path to the JSON file (a hand-written seed).

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
        if not host_play_supported():
            return cls.validate_structure(data, filename=str(file_path))
        return cls.validate(
            data, filename=str(file_path), player=TrustedSeedPlayer()
        )

    @classmethod
    def validate_structure(
        cls, data: dict[str, Any], filename: str = "<campaign>"
    ) -> list[str]:
        """Run every check that doesn't play a program.

        That's the schema, the tier rules, and the check-script rules.
        It's for trusted seed files on a machine that can't play programs
        (Windows); ``validate`` runs these plus the §4.4 play checks.

        Args:
            data: Parsed campaign data dictionary.
            filename: Source filename or identifier for reporting.

        Returns:
            List of validation error messages, or empty if valid.
        """
        errors = cls._schema_errors(data, filename)
        if errors:
            return errors
        errors = cls._tier_errors(data, filename)
        for stage in data["stages"]:
            prefix = f"[{filename}] Stage {stage['stage']}"
            errors.extend(
                f"{prefix}: {problem}"
                for problem in check_script_problems(stage["check_script"])
            )
        return errors

    @classmethod
    def validate(
        cls,
        data: dict[str, Any],
        filename: str = "<campaign>",
        *,
        player: CheckPlayer,
    ) -> list[str]:
        """Validate a parsed campaign dictionary against all checks.

        Args:
            data: Parsed campaign data dictionary.
            filename: Source filename or identifier for reporting.
            player: Plays the campaign's programs. Required, so nobody
                runs an untrusted campaign on the host by accident: only
                committed seed files may use ``TrustedSeedPlayer``; an
                LLM-written campaign needs a player backed by the runner.

        Returns:
            List of validation error messages, or empty if valid.
        """
        errors = cls._schema_errors(data, filename)
        if errors:
            return errors
        errors = cls._tier_errors(data, filename)
        previous_reference = None
        for stage in data["stages"]:
            prefix = f"[{filename}] Stage {stage['stage']}"
            problems = check_script_problems(stage["check_script"])
            if not problems:
                problems = _StageCheck(
                    player, stage, previous_reference
                ).problems()
            errors.extend(f"{prefix}: {problem}" for problem in problems)
            previous_reference = stage["reference_program"]
        return errors

    @classmethod
    def _schema_errors(cls, data: Any, filename: str) -> list[str]:
        """Return one message per JSON Schema error."""
        schema_validator = Draft202012Validator(cls._get_schema())
        return [
            f"[{filename}] Schema error at "
            f"'{'/'.join(str(p) for p in error.path) or 'root'}': "
            f"{error.message}"
            for error in sorted(
                schema_validator.iter_errors(data), key=lambda e: e.path
            )
        ]

    @staticmethod
    def _tier_errors(data: dict[str, Any], filename: str) -> list[str]:
        """Return problems with the tier's stage count and stage numbers."""
        errors = []
        stages = data["stages"]
        difficulty = Difficulty(data["difficulty"])
        expected_stages = difficulty.rules.stages
        if len(stages) != expected_stages:
            errors.append(
                f"[{filename}] Tier '{difficulty.value}' requires "
                f"{expected_stages} stages, but found {len(stages)}."
            )
        for idx, stage in enumerate(stages, start=1):
            if stage["stage"] != idx:
                errors.append(
                    f"[{filename}] Stage index {idx}: expected stage number "
                    f"{idx}, got {stage['stage']}."
                )
        return errors


class _StageCheck:
    """Plays one stage's programs on its check script (game-design §4.4)."""

    def __init__(
        self,
        player: CheckPlayer,
        stage: dict[str, Any],
        previous_reference: str | None,
    ) -> None:
        """Check ``stage``; ``previous_reference`` is None for Stage 1."""
        self._player = player
        self._input_style = stage["input"]
        self._script = stage["check_script"]
        self._reference = stage["reference_program"]
        self._broken = stage["broken_program"]
        self._previous_reference = previous_reference

    def problems(self) -> list[str]:
        """Return every problem found, or an empty list."""
        try:
            problems = self._reference_problems()
            if problems:
                return problems
            first_screen = self._player.screens(self._reference, [])[0]
        except CheckRunError as error:
            return [str(error)]
        return (
            self._must_fail("broken_program", self._broken)
            + self._previous_problems()
            + self._probe_problems(first_screen)
        )

    def _input_style_problems(self, verdict: dict) -> list[str]:
        """Check that grading exercises the declared input style."""
        inputs = verdict["inputs"]

        if self._input_style == "none" and inputs:
            return [
                "A stage with input 'none' must not send input."
            ]

        if self._input_style in ("lines", "keys") and not inputs:
            return [
                f"A stage with input '{self._input_style}' must "
                "exercise input in its check script."
            ]

        return []

    def _completion_problems(self) -> list[str]:
        """Ensure a non-interactive reference exits without input."""
        if self._input_style != "none":
            return []

        script = (
            "def check(game):\n"
            "    game.check(game.finished, "
            "'The program must finish without input.')\n"
        )

        verdict = self._player.grade(self._reference, script)

        if verdict["verdict"] != "pass":
            return [
                "A stage with input 'none' must have a "
                "reference_program that finishes without input."
            ]

        return []

    def _completion_problems(self) -> list[str]:
        """Ensure a non-interactive reference exits without input."""
        if self._input_style != "none":
            return []

        script = (
            "def check(game):\n"
            "    game.check(game.finished, "
            "'The program must finish without input.')\n"
        )

        verdict = self._player.grade(self._reference, script)

        if verdict["verdict"] != "pass":
            return [
                "A stage with input 'none' must have a "
                "reference_program that finishes without input."
            ]

        return []

    def _reference_problems(self) -> list[str]:
        """The reference passes every run within the time budget."""
        fastest = float("inf")
        for attempt in range(1, CHECK_PASS_RUNS + 1):
            started = time.monotonic()
            verdict = self._player.grade(self._reference, self._script)
            fastest = min(fastest, time.monotonic() - started)
            if verdict["verdict"] != "pass":
                return [
                    "reference_program failed its check script on run "
                    f"{attempt} of {CHECK_PASS_RUNS} ({_describe(verdict)})."
                ]

            problems = self._input_style_problems(verdict)
            if problems:
                return problems

        if fastest >= TIME_BUDGET_SECONDS:
            return [
                f"reference_program took {fastest:.2f} s, over the "
                f"{TIME_BUDGET_SECONDS:.2f} s budget (10% of the time "
                "limit)."
            ]

        return self._completion_problems()

    def _previous_problems(self) -> list[str]:
        """Stage N's checks fail the stage N-1 reference."""
        if self._previous_reference is None:
            return []
        try:
            if self._passes(self._previous_reference):
                return [
                    "the previous stage's reference_program passes this "
                    "check script, so the stage adds nothing new."
                ]
        except CheckRunError as error:
            return [
                "check script broke on the previous stage's "
                f"reference_program: {error}"
            ]
        return []

    def _probe_problems(self, first_screen: str) -> list[str]:
        """Junk programs fail; from Stage 2, so does one fixed screen."""
        problems = []
        for name, program in JUNK_PROGRAMS.items():
            problems += self._must_fail(name, program)
        if self._previous_reference is not None:
            problems += self._must_fail(
                "a program printing one fixed screen",
                screen_program(first_screen),
            )
        # Passing is fine here; crashing the check script is not. Each
        # screen is played both ways, since a check may first test whether
        # the program exits.
        for huge in huge_number_screens(first_screen):
            for program in (screen_program(huge), static_program(huge)):
                problems += self._crash_problems(
                    "a screen of huge numbers", program
                )
        return list(dict.fromkeys(problems))

    def _must_fail(self, name: str, program: str) -> list[str]:
        """Return a problem unless the check script fails ``program``."""
        try:
            if self._passes(program):
                return [f"{name} passes the check script."]
        except CheckRunError as error:
            return [f"check script broke on {name}: {error}"]
        return []

    def _crash_problems(self, name: str, program: str) -> list[str]:
        """Return a problem if ``program`` crashes the check script."""
        try:
            self._passes(program)
        except CheckRunError as error:
            return [f"check script broke on {name}: {error}"]
        return []

    def _passes(self, program: str) -> bool:
        """Return True if the check script passes ``program``."""
        return self._player.grade(program, self._script)["verdict"] == "pass"
