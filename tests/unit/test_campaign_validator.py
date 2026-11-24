"""
File: test_campaign_validator.py
Description: Unit tests for CampaignValidator rules and quality checks.
Author(s): Tyler Black, Richard Hall
"""

import copy
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from src.business.campaigns.reference_runner import (
    ReferenceRunResult,
    ReferenceTimeoutError,
    run_reference,
)
from src.business.campaigns.validator import (
    CampaignValidator,
    normalize_output,
)

FIXTURE_PATH = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "campaigns"
    / "valid_beginner.json"
)


@pytest.fixture
def valid_campaign_data() -> dict:
    """Load and return valid beginner campaign dictionary."""
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


class TestCampaignValidator:
    """Test suite covering every validator check and edge case."""

    def test_valid_fixture_passes(self, valid_campaign_data: dict) -> None:
        """Verify the valid beginner fixture passes with no errors."""
        errors = CampaignValidator.validate(valid_campaign_data)
        assert errors == []

    def test_valid_file_passes(self) -> None:
        """Verify validating valid_beginner.json from disk passes."""
        errors = CampaignValidator.validate_file(FIXTURE_PATH)
        assert errors == []

    def test_schema_error_unknown_difficulty(
        self, valid_campaign_data: dict
    ) -> None:
        """Check 1: Reject campaign when difficulty tier is unrecognized."""
        data = copy.deepcopy(valid_campaign_data)
        data["difficulty"] = "god_mode"
        errors = CampaignValidator.validate(data)
        assert any(
            "difficulty" in err or "Schema error" in err for err in errors
        )

    def test_schema_error_additional_property(
        self, valid_campaign_data: dict
    ) -> None:
        """Check 1: Reject campaign when forbidden property is present."""
        data = copy.deepcopy(valid_campaign_data)
        data["extra_field"] = "not_allowed"
        errors = CampaignValidator.validate(data)
        assert any("extra_field" in err for err in errors)

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("difficulty", []),
            ("prompt", None),
            ("samples", None),
            ("hidden_tests", []),
        ],
    )
    def test_malformed_fields_return_schema_errors(
        self, valid_campaign_data: dict, field: str, value: object
    ) -> None:
        """Reject malformed input before attempting to run references."""
        if field == "difficulty":
            valid_campaign_data[field] = value
        else:
            valid_campaign_data["stages"][0][field] = value

        with patch("src.business.campaigns.validator.run_reference") as run:
            errors = CampaignValidator.validate(valid_campaign_data)
        assert any("Schema error" in error for error in errors)
        run.assert_not_called()

    def test_wrong_stage_count(self, valid_campaign_data: dict) -> None:
        """Check 2: Reject when stage count doesn't match tier requirement."""
        data = copy.deepcopy(valid_campaign_data)
        # Beginner requires 2 stages; pop one stage
        data["stages"].pop()
        errors = CampaignValidator.validate(data)
        assert any("requires 2 stages, but found 1" in err for err in errors)

    def test_stage_numbers_out_of_order(
        self, valid_campaign_data: dict
    ) -> None:
        """Check 3: Reject when stage numbers are not strictly 1..N."""
        data = copy.deepcopy(valid_campaign_data)
        data["stages"][1]["stage"] = 3
        errors = CampaignValidator.validate(data)
        assert any("expected stage number 2, got 3" in err for err in errors)

    def test_sample_count_too_many(self, valid_campaign_data: dict) -> None:
        """Check 4: Reject when stage has more than 2 samples."""
        data = copy.deepcopy(valid_campaign_data)
        extra_sample = {"input": "7", "expected_output": "8"}
        data["stages"][0]["samples"].append(extra_sample)
        data["stages"][0]["samples"].append(
            {"input": "9", "expected_output": "10"}
        )
        errors = CampaignValidator.validate(data)
        assert any("expected 1-2 samples, found 3" in err for err in errors)

    def test_sample_count_zero(self, valid_campaign_data: dict) -> None:
        """Check 4: Reject when stage has 0 samples."""
        data = copy.deepcopy(valid_campaign_data)
        data["stages"][0]["samples"] = []
        errors = CampaignValidator.validate(data)
        assert any("expected 1-2 samples, found 0" in err for err in errors)

    def test_sample_input_missing_from_prompt(
        self, valid_campaign_data: dict
    ) -> None:
        """Check 5: Reject when sample input text does not appear in prompt."""
        data = copy.deepcopy(valid_campaign_data)
        data["stages"][0]["prompt"] = (
            "Add one to the input number. Example: prints 6."
        )
        errors = CampaignValidator.validate(data)
        assert any(
            "input line '5' does not appear in prompt" in err for err in errors
        )

    def test_sample_output_missing_from_prompt(
        self, valid_campaign_data: dict
    ) -> None:
        """Check 5: Reject when sample output does not appear in prompt."""
        data = copy.deepcopy(valid_campaign_data)
        data["stages"][0]["prompt"] = (
            "Add one to the input number. Example: 5."
        )
        errors = CampaignValidator.validate(data)
        assert any(
            "expected output line '6' does not appear in prompt" in err
            for err in errors
        )

    @pytest.mark.parametrize("stage_number", [1, 2])
    def test_starter_code_rejected(
        self, valid_campaign_data: dict, stage_number: int
    ) -> None:
        """Check 6: Reject non-null starter code on any stage."""
        starter_code = "print(1)"
        valid_campaign_data["stages"][stage_number - 1]["starter_code"] = (
            starter_code
        )
        errors = CampaignValidator.validate(valid_campaign_data)
        assert errors == [
            f"[<campaign>] Stage {stage_number}: starter_code must be null, "
            f"got {starter_code!r}."
        ]

    def test_null_starter_code_allowed_on_all_stages(
        self, valid_campaign_data: dict
    ) -> None:
        """Check 6: Accept a campaign with null starter code on all stages."""
        assert all(
            stage["starter_code"] is None
            for stage in valid_campaign_data["stages"]
        )
        assert CampaignValidator.validate(valid_campaign_data) == []

    def test_wrong_expected_output(self, valid_campaign_data: dict) -> None:
        """Check 7: Reject when expected_output doesn't match reference."""
        data = copy.deepcopy(valid_campaign_data)
        data["stages"][0]["hidden_tests"][0]["expected_output"] = "999"
        errors = CampaignValidator.validate(data)
        assert any(
            "expected output does not match reference stdout" in err
            for err in errors
        )

    def test_reference_crashes_on_test(
        self, valid_campaign_data: dict
    ) -> None:
        """Check 7: Reject when reference solution throws exception."""
        data = copy.deepcopy(valid_campaign_data)
        data["stages"][0]["reference_solution"] = "raise RuntimeError('boom')"
        errors = CampaignValidator.validate(data)
        assert any(
            "reference solution exited with code" in err for err in errors
        )

    def test_reference_times_out_on_test(
        self, valid_campaign_data: dict
    ) -> None:
        """Check 7: Reject when reference solution exceeds timeout."""
        data = copy.deepcopy(valid_campaign_data)
        with patch(
            "src.business.campaigns.validator.run_reference",
            side_effect=ReferenceTimeoutError("timed out"),
        ):
            errors = CampaignValidator.validate(data)
            assert any("reference solution timed out" in err for err in errors)

    def test_non_deterministic_reference(
        self, valid_campaign_data: dict
    ) -> None:
        """Check 8: Reject when reference produces varying outputs."""
        data = copy.deepcopy(valid_campaign_data)
        data["stages"][0]["reference_solution"] = (
            "import time\nprint(time.time())\n"
        )
        # Even if expected output matched one run, determinism check fails
        errors = CampaignValidator.validate(data)
        assert any("non-deterministic" in err for err in errors)

    def test_stage_n_tests_pass_stage_n_minus_one(
        self, valid_campaign_data: dict
    ) -> None:
        """Check 9: Reject when stage N tests pass stage N-1 reference."""
        data = copy.deepcopy(valid_campaign_data)
        # Make stage 2 identical to stage 1 so stage 1 reference passes stage 2
        data["stages"][1]["reference_solution"] = data["stages"][0][
            "reference_solution"
        ]
        data["stages"][1]["prompt"] = (
            "Add one to the input number. Example: `5` prints `6`."
        )
        data["stages"][1]["samples"] = data["stages"][0]["samples"]
        data["stages"][1]["hidden_tests"] = data["stages"][0]["hidden_tests"]
        errors = CampaignValidator.validate(data)
        assert any(
            "hidden tests did not fail stage 1 reference solution" in err
            for err in errors
        )

    def test_validate_file_missing_path(self) -> None:
        """Verify validate_file returns clear error for non-existent file."""
        errors = CampaignValidator.validate_file("nonexistent.json")
        assert any("File does not exist" in err for err in errors)

    def test_validate_file_corrupt_json(self, tmp_path: Path) -> None:
        """Verify validate_file reports JSON decoding error."""
        bad_file = tmp_path / "broken.json"
        bad_file.write_text("{bad json", encoding="utf-8")
        errors = CampaignValidator.validate_file(bad_file)
        assert any("Invalid JSON" in err for err in errors)

    def test_normalize_output_variations(self) -> None:
        """Verify normalize_output handles trailing spaces and blank lines."""
        raw = "line 1   \nline 2\t\n\n\n"
        expected = "line 1\nline 2"
        assert normalize_output(raw) == expected
        assert normalize_output("") == ""
        assert normalize_output("   \n\n") == ""

    def test_schema_file_not_found_raises(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Verify _get_schema raises FileNotFoundError when absent."""
        CampaignValidator._schema = None
        fake_path = Path("/nonexistent/schema.json")
        monkeypatch.setattr(
            "src.business.campaigns.validator.SCHEMA_PATH", fake_path
        )
        with pytest.raises(FileNotFoundError):
            CampaignValidator._get_schema()
        CampaignValidator._schema = None

    def test_stages_not_a_list(self) -> None:
        """Verify non-list stages returns schema errors early."""
        errors = CampaignValidator.validate(
            {
                "title": "Bad",
                "difficulty": "beginner",
                "stages": "not-a-list",
            }
        )
        assert any("Schema error" in err for err in errors)

    def test_hidden_test_execution_failure(
        self, valid_campaign_data: dict
    ) -> None:
        """Verify reference execution failure on a hidden test."""
        data = copy.deepcopy(valid_campaign_data)
        data["stages"][0]["reference_solution"] = (
            "num = int(input())\n"
            "if num == 10:\n    raise RuntimeError('boom')\n"
            "print(num + 1)\n"
        )
        errors = CampaignValidator.validate(data)
        assert any(
            "hidden_test 1: reference solution exited with code" in err
            for err in errors
        )

    def test_hidden_test_times_out(self, valid_campaign_data: dict) -> None:
        """Verify reference timeout on a hidden test."""
        data = copy.deepcopy(valid_campaign_data)
        reference = data["stages"][0]["reference_solution"]

        def run_with_timeout(code: str, stdin: str) -> ReferenceRunResult:
            if code == reference and stdin == "10":
                raise ReferenceTimeoutError("timed out")
            return run_reference(code, stdin)

        with patch(
            "src.business.campaigns.validator.run_reference",
            side_effect=run_with_timeout,
        ):
            errors = CampaignValidator.validate(data)
            assert any(
                "hidden_test 1: reference solution timed out" in err
                for err in errors
            )

    def test_reference_nondeterminism_on_hidden_input(
        self, valid_campaign_data: dict
    ) -> None:
        """Reject a reference that varies only on a hidden test."""
        valid_campaign_data["stages"][0]["reference_solution"] = (
            "import time\n"
            "number = int(input())\n"
            "print(time.time_ns() if number == 10 else number + 1)\n"
        )

        errors = CampaignValidator.validate(valid_campaign_data)

        assert any(
            "hidden_test 1: reference solution is non-deterministic" in error
            for error in errors
        )

    def test_non_dict_elements_skipped_safely(
        self, valid_campaign_data: dict
    ) -> None:
        """Verify non-dict items in stages or samples are handled safely."""
        data = copy.deepcopy(valid_campaign_data)
        data["stages"].append("not-a-dict")
        data["stages"][0]["samples"].append("not-a-dict")
        errors = CampaignValidator.validate(data)
        assert any("Schema error" in err for err in errors)


TICK_FIXTURE_PATH = FIXTURE_PATH.with_name("valid_tick_beginner.json")


@pytest.fixture
def tick_campaign() -> dict:
    """Load a valid campaign whose stages have check scripts (US6)."""
    return json.loads(TICK_FIXTURE_PATH.read_text(encoding="utf-8"))


class TestCheckScripts:
    """Check-script rules and playback against the reference solutions."""

    def test_tick_campaign_is_valid(self, tick_campaign: dict) -> None:
        """A stage whose reference passes its check script is valid."""
        assert CampaignValidator.validate(tick_campaign) == []

    @pytest.mark.parametrize(
        ("script", "message"),
        [
            ("import os\ndef check(game):\n    pass\n", "must not import"),
            (
                "def check(game):\n    from os import path\n",
                "must not import",
            ),
            (
                "def check(game):\n    __import__('os')\n",
                "must not import",
            ),
            ("def play(game):\n    pass\n", "must define check(game)"),
            ("def check(game, extra):\n    pass\n", "must define check"),
            ("def check(*game):\n    pass\n", "must define check"),
            ("check = lambda game: None\n", "must define check"),
            ("def check(game)\n    pass\n", "syntax error on line 1"),
        ],
    )
    def test_check_script_shape_rules(
        self, tick_campaign: dict, script: str, message: str
    ) -> None:
        """A check script imports nothing and defines check(game)."""
        tick_campaign["stages"][0]["check_script"] = script
        errors = CampaignValidator.validate(tick_campaign, "tick.json")
        assert any(
            err.startswith("[tick.json] Stage 1:") and message in err
            for err in errors
        )

    def test_reference_must_pass_its_check_script(
        self, tick_campaign: dict
    ) -> None:
        """A check the reference can't pass names the broken rule."""
        tick_campaign["stages"][0]["check_script"] = (
            "def check(game):\n"
            "    game.check(len(game.tick().rows) == 4, 'Four rows.')\n"
        )
        errors = CampaignValidator.validate(tick_campaign)
        assert any(
            "failed its check script on run 1 of 2 (rule: Four rows.)" in err
            for err in errors
        )

    def test_reference_crash_is_described(self, tick_campaign: dict) -> None:
        """A reference that crashes under the check says how and when."""
        tick_campaign["stages"][0]["reference_solution"] = "input()\n1 / 0\n"
        errors = CampaignValidator.validate(tick_campaign)
        assert any("the program crashed at tick 1" in err for err in errors)

    def test_flaky_check_is_caught_on_the_second_run(
        self, tick_campaign: dict
    ) -> None:
        """A check that passes only sometimes fails validation."""
        passed = {"verdict": "pass"}
        failed = {"verdict": "fail", "reason": "rule", "rule": "r", "tick": 1}
        with patch(
            "src.business.campaigns.validator.run_check",
            side_effect=[passed, failed],
        ):
            errors = CampaignValidator._play_check("s", "ref", None)
        assert errors == [
            "reference solution failed its check script on run 2 of 2 "
            "(rule: r)."
        ]

    def test_stage_must_add_something(self, tick_campaign: dict) -> None:
        """Stage 2's check must fail stage 1's reference."""
        stages = tick_campaign["stages"]
        stages[1]["check_script"] = stages[0]["check_script"]
        errors = CampaignValidator.validate(tick_campaign)
        assert any(
            err.startswith("[<campaign>] Stage 2:") and "adds nothing" in err
            for err in errors
        )

    def test_broken_check_script_is_reported(
        self, tick_campaign: dict
    ) -> None:
        """A check script that crashes is a campaign error, with detail."""
        tick_campaign["stages"][0]["check_script"] = (
            "def check(game):\n    game.tick()\n    1 / 0\n"
        )
        errors = CampaignValidator.validate(tick_campaign)
        assert any(
            "check script failed" in err and "ZeroDivisionError" in err
            for err in errors
        )

    def test_check_script_must_survive_junk_frames(
        self, tick_campaign: dict
    ) -> None:
        """A check that crashes on an empty frame could spare a life."""
        tick_campaign["stages"][0]["check_script"] = (
            "def check(game):\n"
            "    ball = game.tick('go').find('O')[0]\n"
            "    game.check(ball == (1, 1), 'The O starts in the middle.')\n"
        )
        errors = CampaignValidator.validate(tick_campaign)
        assert any(
            "check script broke on empty frames" in err and "IndexError" in err
            for err in errors
        )

    def test_junk_program_must_not_pass(self, tick_campaign: dict) -> None:
        """A check script that any program passes checks nothing."""
        tick_campaign["stages"][0]["check_script"] = (
            "def check(game):\n    game.tick('go')\n"
        )
        errors = CampaignValidator.validate(tick_campaign)
        assert any("a program printing a single ? passes" in e for e in errors)
