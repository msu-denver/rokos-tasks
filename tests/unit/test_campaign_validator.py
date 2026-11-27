"""
File: test_campaign_validator.py
Description: Unit tests for CampaignValidator: the schema, tier rules,
    check-script rules, and the game-design §4.4 quality checks played
    on a small two-stage fixture campaign.
Author(s): Tyler Black, Richard Hall, Steph Rivera
"""

import copy
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from src.business.campaigns.check_runner import (
    CheckRunError,
    TrustedSeedPlayer,
)
from src.business.campaigns.validator import (
    HUGE_NUMBER_DIGITS,
    MAX_HUGE_NUMBER_PROBES,
    CampaignValidator,
    check_script_problems,
    huge_number_screens,
    screen_program,
)
from src.runner.grading import CHECK_SCRIPT_BYTES
from tests.conftest import requires_host_play

FIXTURE_PATH = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "campaigns"
    / "valid_beginner.json"
)
PASS_ANYTHING = "def check(game):\n    game.screen()\n"


@pytest.fixture
def campaign() -> dict:
    """Return a fresh copy of the valid two-stage fixture campaign."""
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def errors_for(data: dict, player: object = None) -> list[str]:
    return CampaignValidator.validate(
        data, filename="t", player=player or TrustedSeedPlayer()
    )


class FlakyPlayer(TrustedSeedPlayer):
    """Fails the reference on one chosen run, like a luck-based check."""

    def __init__(self, reference: str, failing_run: int) -> None:
        """Fail the reference on run ``failing_run``."""
        self._reference = reference
        self._failing_run = failing_run
        self._runs = 0

    def grade(self, code: str, check_script: str) -> dict:
        """Return the real verdict, except on the chosen reference run."""
        verdict = super().grade(code, check_script)
        if code == self._reference:
            self._runs += 1
            if self._runs == self._failing_run:
                return {**verdict, "verdict": "fail", "reason": "rule"}
        return verdict


def test_player_is_required(campaign: dict) -> None:
    """No default player: untrusted content can't run on the host."""
    with pytest.raises(TypeError, match="player"):
        CampaignValidator.validate(campaign)  # type: ignore[call-arg]


class TestSchemaAndTiers:
    """Structure checks that run before any program is played."""

    @requires_host_play
    @pytest.mark.parametrize("input_style", ["lines", "keys"])
    def test_valid_fixture_passes(
        self, campaign: dict, input_style: str
    ) -> None:
        """A static stage and either interactive style pass every check."""
        campaign["stages"][1]["input"] = input_style
        assert errors_for(campaign) == []

    def test_valid_file_passes(self) -> None:
        """The fixture file on disk passes too."""
        assert CampaignValidator.validate_file(FIXTURE_PATH) == []

    def test_unknown_difficulty(self, campaign: dict) -> None:
        """An unknown tier is a schema error."""
        campaign["difficulty"] = "god_mode"
        (error,) = errors_for(campaign)
        assert "Schema error at 'difficulty'" in error

    @pytest.mark.parametrize(
        "field",
        ["starter_code", "samples", "hidden_tests", "expected_output"],
    )
    def test_old_grading_fields_are_rejected(
        self, campaign: dict, field: str
    ) -> None:
        """The stdin/stdout fields are gone; check scripts grade alone."""
        campaign["stages"][0][field] = None
        (error,) = errors_for(campaign)
        assert f"'{field}' was unexpected" in error

    @pytest.mark.parametrize(
        "field",
        ["check_script", "reference_program", "broken_program", "input"],
    )
    def test_required_stage_fields(self, campaign: dict, field: str) -> None:
        """Every stage needs its input style, check script, and programs."""
        del campaign["stages"][1][field]
        (error,) = errors_for(campaign)
        assert f"'{field}' is a required property" in error
        assert "stages/1" in error

    @pytest.mark.parametrize("input_style", ["mouse", "", None, 1])
    def test_invalid_input_style(
        self, campaign: dict, input_style: object
    ) -> None:
        """Unknown input styles and non-string values are schema errors."""
        campaign["stages"][0]["input"] = input_style
        errors = errors_for(campaign)
        assert errors
        assert all(
            "Schema error at 'stages/0/input'" in error for error in errors
        )

    def test_malformed_fields_return_schema_errors(
        self, campaign: dict
    ) -> None:
        """Wrong types are reported, one error each."""
        campaign["title"] = ""
        campaign["stages"][0]["stage"] = "one"
        errors = errors_for(campaign)
        assert len(errors) == 2
        assert all("Schema error" in error for error in errors)

    @requires_host_play
    def test_wrong_stage_count(self, campaign: dict) -> None:
        """A tier's stage count is enforced."""
        campaign["stages"].append(copy.deepcopy(campaign["stages"][1]))
        campaign["stages"][2]["stage"] = 3
        assert (
            "[t] Tier 'beginner' requires 2 stages, but found 3."
            in errors_for(campaign)
        )

    @requires_host_play
    def test_stage_numbers_out_of_order(self, campaign: dict) -> None:
        """Stages are numbered 1, 2, 3, ... in order."""
        campaign["stages"][1]["stage"] = 5
        assert (
            "[t] Stage index 2: expected stage number 2, got 5."
            in errors_for(campaign)
        )

    def test_validate_file_missing_path(self, tmp_path: Path) -> None:
        """A missing file is reported, not raised."""
        missing = tmp_path / "nope.json"
        assert CampaignValidator.validate_file(missing) == [
            f"[{missing}] File does not exist."
        ]

    def test_validate_file_corrupt_json(self, tmp_path: Path) -> None:
        """Bad JSON is reported, not raised."""
        corrupt = tmp_path / "bad.json"
        corrupt.write_text("{not json", encoding="utf-8")
        (error,) = CampaignValidator.validate_file(corrupt)
        assert "Invalid JSON" in error

    def test_schema_file_not_found_raises(self, tmp_path: Path) -> None:
        """A missing schema is a setup error."""
        with (
            patch.object(CampaignValidator, "_schema", None),
            patch(
                "src.business.campaigns.validator.SCHEMA_PATH",
                tmp_path / "missing.json",
            ),
            pytest.raises(FileNotFoundError),
        ):
            CampaignValidator.validate({}, player=TrustedSeedPlayer())


class TestCheckScriptRules:
    """A check script uses only the helper API (game-design §4.4)."""

    def test_good_script_has_no_problems(self) -> None:
        """A script that only plays the game is fine."""
        assert check_script_problems(PASS_ANYTHING) == []

    @pytest.mark.parametrize(
        ("source", "problem"),
        [
            (
                "import os\ndef check(game):\n    pass\n",
                "check_script must not import anything.",
            ),
            (
                "from os import path\ndef check(game):\n    pass\n",
                "check_script must not import anything.",
            ),
            (
                "def check(game):\n    __import__('os')\n",
                "check_script may only use the helper API, not __import__.",
            ),
            (
                "def check(game):\n    open('/etc/passwd')\n",
                "check_script may only use the helper API, not open.",
            ),
            (
                "def check(game):\n    getattr(game, '_channel')\n",
                "check_script may only use the helper API, not getattr.",
            ),
            (
                "def check(game):\n    game.__class__.__subclasses__()\n",
                "check_script may only use the helper API, not "
                "__class__, __subclasses__.",
            ),
            ("def run(game):\n    pass\n", "must define check(game)."),
            ("def check(game, x):\n    pass\n", "must define check(game)."),
            ("def check(*game):\n    pass\n", "must define check(game)."),
            ("def check(game:\n", "syntax error on line 1."),
        ],
    )
    def test_rule_breaks(self, source: str, problem: str) -> None:
        """Each way out of the helper API is caught."""
        problems = check_script_problems(source)
        assert any(problem in found for found in problems), problems

    def test_size_cap(self) -> None:
        """A check script over the runner's cap is rejected."""
        source = PASS_ANYTHING + "#" * CHECK_SCRIPT_BYTES
        assert check_script_problems(source) == [
            f"check_script is larger than {CHECK_SCRIPT_BYTES} bytes."
        ]

    def test_bad_script_is_reported_without_playing(
        self, campaign: dict
    ) -> None:
        """A script that breaks the rules is never played."""
        campaign["stages"][0]["check_script"] = "import os\n" + PASS_ANYTHING
        player = TrustedSeedPlayer()
        with patch.object(player, "grade") as grade:
            errors = errors_for(campaign, player=player)
        assert "[t] Stage 1: check_script must not import anything." in (
            errors
        )
        assert all(
            call.args[1] != campaign["stages"][0]["check_script"]
            for call in grade.call_args_list
        )


class TestQualityChecks:
    """The game-design §4.4 checks, played with real programs."""

    @requires_host_play
    def test_reference_must_pass(self, campaign: dict) -> None:
        """A reference that fails its check is reported."""
        stage = campaign["stages"][0]
        stage["reference_program"] = stage["broken_program"]
        assert errors_for(campaign)[0] == (
            "[t] Stage 1: reference_program failed its check script on "
            "run 1 of 3 (rule: The board must show exactly one O.)."
        )

    @requires_host_play
    def test_reference_crash_is_described(self, campaign: dict) -> None:
        """A crashing reference says how it failed."""
        campaign["stages"][0]["reference_program"] = "1 / 0\n"
        assert errors_for(campaign)[0].endswith(
            "(the program crashed at turn 0)."
        )

    @requires_host_play
    @pytest.mark.parametrize("failing_run", [2, 3])
    def test_flaky_check_is_caught_on_any_run(
        self, campaign: dict, failing_run: int
    ) -> None:
        """A check that passes by luck fails on a later run."""
        reference = campaign["stages"][0]["reference_program"]
        player = FlakyPlayer(reference, failing_run)
        assert errors_for(campaign, player=player)[0].startswith(
            f"[t] Stage 1: reference_program failed its check script on "
            f"run {failing_run} of 3"
        )

    @requires_host_play
    def test_reference_must_finish_inside_the_time_budget(
        self, campaign: dict
    ) -> None:
        """A slow reference breaks the 10% time budget."""
        with patch(
            "src.business.campaigns.validator.TIME_BUDGET_SECONDS", 0.0
        ):
            errors = errors_for(campaign)
        assert len(errors) == 2
        assert "over the 0.00 s budget (10% of the time limit)" in errors[0]

    @requires_host_play
    def test_broken_program_must_fail(self, campaign: dict) -> None:
        """Checks too weak to catch the broken program are reported."""
        stage = campaign["stages"][1]
        stage["broken_program"] = stage["reference_program"]
        assert errors_for(campaign) == [
            "[t] Stage 2: broken_program passes the check script."
        ]

    @requires_host_play
    def test_stage_must_add_something(self, campaign: dict) -> None:
        """Stage N's checks must fail the stage N-1 reference."""
        stages = campaign["stages"]
        stages[1]["input"] = "none"
        stages[1]["reference_program"] = stages[0]["reference_program"]
        stages[1]["check_script"] = stages[0]["check_script"]
        stages[1]["broken_program"] = stages[0]["broken_program"]
        errors = errors_for(campaign)
        assert (
            "[t] Stage 2: the previous stage's reference_program passes "
            "this check script, so the stage adds nothing new."
        ) in errors

    @requires_host_play
    def test_empty_program_must_fail(self, campaign: dict) -> None:
        """A check that passes an empty program is reported."""
        campaign["stages"][0]["check_script"] = "def check(game):\n    pass\n"
        errors = errors_for(campaign)
        assert "[t] Stage 1: an empty program passes the check script." in (
            errors
        )

    @requires_host_play
    def test_fixed_screen_must_fail_from_stage_two(
        self, campaign: dict
    ) -> None:
        """A first-screen check passes a static screen: Stage 1 only."""
        stage = campaign["stages"][1]
        stage["input"] = "none"
        stage["reference_program"] = (
            "print('...')\nprint('..O')\nprint('...')\n"
        )
        stage["broken_program"] = campaign["stages"][0]["broken_program"]
        stage["check_script"] = (
            "def check(game):\n"
            "    rows = game.screen().rows\n"
            "    game.check(rows == ['...', '..O', '...'], 'Start right.')\n"
        )
        assert errors_for(campaign) == [
            "[t] Stage 2: a program printing one fixed screen passes the "
            "check script."
        ]

    @requires_host_play
    def test_stage_one_may_be_static(self, campaign: dict) -> None:
        """Stage 1's check passes a fixed screen and that is allowed."""
        screen = TrustedSeedPlayer().screens(
            campaign["stages"][0]["reference_program"], []
        )[0]
        verdict = TrustedSeedPlayer().grade(
            screen_program(screen), campaign["stages"][0]["check_script"]
        )
        assert verdict["verdict"] == "pass"
        assert errors_for(campaign) == []

    @requires_host_play
    def test_huge_numbers_must_not_crash_the_check(
        self, campaign: dict
    ) -> None:
        """An unbounded int() on a screen is a check_error in waiting."""
        stage = campaign["stages"][0]
        stage["input"] = "lines"
        stage["reference_program"] = screen_program("5")
        stage["broken_program"] = screen_program("6")
        stage["check_script"] = (
            "def check(game):\n"
            "    rows = game.screen().rows\n"
            "    game.check(rows and rows[0].isdecimal(), 'A number.')\n"
            "    game.check(int(rows[0]) == 5, 'Five.')\n"
            "    if not game.finished:\n"
            "        game.send('next')\n"
        )
        campaign["stages"] = [stage]
        campaign["difficulty"] = "beginner"
        errors = errors_for(campaign)
        assert any(
            "check script broke on a screen of huge numbers" in error
            for error in errors
        ), errors
        assert HUGE_NUMBER_DIGITS > 4300

    def test_huge_numbers_go_in_one_at_a_time(self) -> None:
        """A check that bounds only the first number is still caught."""
        huge = "9" * HUGE_NUMBER_DIGITS
        assert huge_number_screens("a 1 b 22\nc 3 d 4") == [
            f"a {huge} b 22\nc 3 d 4",
            f"a 1 b {huge}\nc 3 d 4",
            f"a 1 b 22\nc {huge} d 4",
            f"a 1 b 22\nc 3 d {huge}",
        ]
        many = " ".join(str(number) for number in range(10))
        assert len(huge_number_screens(many)) == MAX_HUGE_NUMBER_PROBES
        assert huge_number_screens("no digits") == []

    @requires_host_play
    def test_huge_numbers_reach_a_static_check(self, campaign: dict) -> None:
        """A check that demands an exit first still gets the huge probe."""
        stage = campaign["stages"][0]
        stage["reference_program"] = "print('5')\n"
        stage["broken_program"] = "print('6')\n"
        stage["check_script"] = (
            "def check(game):\n"
            "    game.check(game.finished, 'Exit.')\n"
            "    rows = game.screen().rows\n"
            "    game.check(rows and rows[0].isdecimal(), 'A number.')\n"
            "    game.check(int(rows[0]) == 5, 'Five.')\n"
        )
        campaign["stages"] = [stage]
        errors = errors_for(campaign)
        assert any(
            "check script broke on a screen of huge numbers" in error
            for error in errors
        ), errors

    @requires_host_play
    def test_crashing_check_script_is_reported(self, campaign: dict) -> None:
        """A check script that crashes is a campaign bug."""
        campaign["stages"][0]["check_script"] = (
            "def check(game):\n    raise RuntimeError('oops')\n"
        )
        (first, *_rest) = errors_for(campaign)
        assert first.startswith("[t] Stage 1: check script failed")

    @requires_host_play
    def test_check_script_must_fail_junk_cleanly(self, campaign: dict) -> None:
        """A script that crashes on odd screens gives players an escape."""
        campaign["stages"][0]["check_script"] = (
            "def check(game):\n"
            "    rows = game.screen().rows\n"
            "    game.check(rows[1][1] == 'O', 'Ball in the middle.')\n"
        )
        errors = errors_for(campaign)
        assert any(
            error.startswith(
                "[t] Stage 1: check script broke on a program that only "
                "prints ?"
            )
            for error in errors
        ), errors

    @requires_host_play
    def test_first_screen_failure_is_reported(self, campaign: dict) -> None:
        """If the reference's first screen can't be read, say so."""
        player = TrustedSeedPlayer()
        with patch.object(
            player, "screens", side_effect=CheckRunError("no screen")
        ):
            errors = errors_for(campaign, player=player)
        assert errors == ["[t] Stage 1: no screen", "[t] Stage 2: no screen"]


class TestInputStyles:
    """Check that the reference and check script match stage input metadata."""

    @requires_host_play
    def test_none_must_not_send_input(self, campaign: dict) -> None:
        """A stage marked none cannot use an interactive check script."""
        campaign["stages"][1]["input"] = "none"
        assert errors_for(campaign) == [
            "[t] Stage 2: A stage with input 'none' must not send input."
        ]

    @requires_host_play
    def test_none_must_finish_without_input(self, campaign: dict) -> None:
        """A passing first-screen check must not hide a waiting program."""
        stage = campaign["stages"][0]
        stage["reference_program"] += "\ninput()\n"
        assert errors_for(campaign) == [
            "[t] Stage 1: A stage with input 'none' must have a "
            "reference_program that finishes without input."
        ]

    @requires_host_play
    @pytest.mark.parametrize("input_style", ["lines", "keys"])
    def test_interactive_stage_must_exercise_input(
        self, campaign: dict, input_style: str
    ) -> None:
        """An interactive stage's check must send at least one input."""
        stage = campaign["stages"][1]
        stage["input"] = input_style
        stage["check_script"] = PASS_ANYTHING
        assert errors_for(campaign) == [
            f"[t] Stage 2: A stage with input '{input_style}' must "
            "exercise input in its check script."
        ]


class TestWithoutHostPlay:
    """Windows can't play programs, so seeds get the checks that don't."""

    def test_structure_checks_play_nothing(self, campaign: dict) -> None:
        """A valid campaign passes, and no program is ever played."""
        with patch.object(TrustedSeedPlayer, "grade") as grade:
            assert CampaignValidator.validate_structure(campaign) == []
        grade.assert_not_called()

    def test_structure_checks_still_catch_problems(
        self, campaign: dict
    ) -> None:
        """Schema, tier, and check-script problems are all still found."""
        assert CampaignValidator.validate_structure({}, "t") == [
            "[t] Schema error at 'root': 'title' is a required property",
            "[t] Schema error at 'root': 'difficulty' is a required property",
            "[t] Schema error at 'root': 'stages' is a required property",
        ]
        campaign["stages"][1]["stage"] = 5
        campaign["stages"][0]["check_script"] = "import os\n" + PASS_ANYTHING
        assert CampaignValidator.validate_structure(campaign, "t") == [
            "[t] Stage index 2: expected stage number 2, got 5.",
            "[t] Stage 1: check_script must not import anything.",
        ]

    def test_validate_file_falls_back_on_windows(self) -> None:
        """On Windows, a seed file is structure-checked, not played."""
        with (
            patch(
                "src.business.campaigns.validator.host_play_supported",
                return_value=False,
            ),
            patch.object(TrustedSeedPlayer, "grade") as grade,
        ):
            assert CampaignValidator.validate_file(FIXTURE_PATH) == []
        grade.assert_not_called()
