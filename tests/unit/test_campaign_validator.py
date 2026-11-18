"""
File: test_campaign_validator.py
Description: Unit tests for CampaignValidator rules and quality checks.
Author(s): Tyler Black
"""

import copy
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from src.business.campaigns.reference_runner import ReferenceTimeoutError
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

    def test_starter_code_missing_on_stage_1(
        self, valid_campaign_data: dict
    ) -> None:
        """Check 6: Reject when stage 1 has empty or null starter code."""
        data = copy.deepcopy(valid_campaign_data)
        data["stages"][0]["starter_code"] = None
        errors = CampaignValidator.validate(data)
        assert any(
            "Stage 1 must have non-empty starter_code" in err for err in errors
        )

    def test_starter_code_present_on_stage_2(
        self, valid_campaign_data: dict
    ) -> None:
        """Check 6: Reject when stage 2 has starter code (must be null)."""
        data = copy.deepcopy(valid_campaign_data)
        data["stages"][1]["starter_code"] = "print('extra')"
        errors = CampaignValidator.validate(data)
        assert any("starter_code must be null" in err for err in errors)

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
        with patch("src.business.campaigns.validator.run_reference") as m_run:
            from src.business.campaigns.reference_runner import (
                ReferenceRunResult,
                ReferenceTimeoutError,
            )

            m_run.side_effect = [
                ReferenceRunResult("6", "", 0),
                ReferenceTimeoutError("timed out"),
                ReferenceRunResult("6", "", 0),
                ReferenceRunResult("6", "", 0),
                ReferenceRunResult("11", "", 0),
                ReferenceRunResult("21", "", 0),
                ReferenceRunResult("11", "", 0),
                ReferenceRunResult("11", "", 0),
                ReferenceRunResult("11", "", 0),
            ]
            errors = CampaignValidator.validate(data)
            assert any(
                "hidden_test 1: reference solution timed out" in err
                for err in errors
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
