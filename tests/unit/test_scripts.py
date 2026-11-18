"""
File: test_scripts.py
Description: Unit tests for fill_expected, validate_campaigns, seed.
Author(s): Tyler Black
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.exc import SQLAlchemyError

from scripts import fill_expected, seed, validate_campaigns
from src.business.campaigns.seed_loader import CampaignValidationError

FIXTURE_PATH = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "campaigns"
    / "valid_beginner.json"
)


class TestFillExpectedScript:
    """Tests for fill_expected CLI utility."""

    def test_missing_argument(self) -> None:
        """Verify fill_expected exits non-zero if no argument provided."""
        assert fill_expected.main(["scripts/fill_expected.py"]) == 1

    def test_nonexistent_file(self) -> None:
        """Verify fill_expected handles non-existent files gracefully."""
        res = fill_expected.main(
            ["scripts/fill_expected.py", "nonexistent.json"]
        )
        assert res == 1

    def test_invalid_json(self, tmp_path: Path) -> None:
        """Verify fill_expected handles malformed JSON files."""
        bad_json = tmp_path / "bad.json"
        bad_json.write_text("{broken", encoding="utf-8")
        res = fill_expected.main(["scripts/fill_expected.py", str(bad_json)])
        assert res == 1

    def test_missing_reference_solution(self, tmp_path: Path) -> None:
        """Verify error when a stage lacks reference_solution."""
        data = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        data["stages"][0]["reference_solution"] = ""
        target = tmp_path / "noref.json"
        target.write_text(json.dumps(data), encoding="utf-8")
        assert (
            fill_expected.main(["scripts/fill_expected.py", str(target)]) == 1
        )

    def test_sample_execution_failure(self, tmp_path: Path) -> None:
        """Verify error when reference solution fails on sample."""
        data = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        data["stages"][0]["reference_solution"] = "import sys; sys.exit(1)"
        target = tmp_path / "fail_sample.json"
        target.write_text(json.dumps(data), encoding="utf-8")
        assert (
            fill_expected.main(["scripts/fill_expected.py", str(target)]) == 1
        )

    def test_sample_execution_timeout(self, tmp_path: Path) -> None:
        """Verify error when reference solution times out on sample."""
        data = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        data["stages"][0]["reference_solution"] = "import time; time.sleep(10)"
        target = tmp_path / "timeout_sample.json"
        target.write_text(json.dumps(data), encoding="utf-8")
        patch_target = "src.business.campaigns.reference_runner.run_reference"
        with patch(patch_target) as mock_run:
            from src.business.campaigns.reference_runner import (
                ReferenceTimeoutError,
            )

            mock_run.side_effect = ReferenceTimeoutError("Timed out")
            assert (
                fill_expected.main(["scripts/fill_expected.py", str(target)])
                == 1
            )

    def test_hidden_execution_failure(self, tmp_path: Path) -> None:
        """Verify error when reference solution fails on hidden test."""
        data = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        # Fails when input is 10 (the hidden test input)
        data["stages"][0]["reference_solution"] = (
            "num = int(input())\n"
            "if num == 10:\n    raise RuntimeError('boom')\n"
            "print(num + 1)\n"
        )
        target = tmp_path / "fail_hidden.json"
        target.write_text(json.dumps(data), encoding="utf-8")
        assert (
            fill_expected.main(["scripts/fill_expected.py", str(target)]) == 1
        )

    def test_hidden_execution_timeout(self, tmp_path: Path) -> None:
        """Verify error when reference solution times out on hidden test."""
        data = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        target = tmp_path / "timeout_hidden.json"
        target.write_text(json.dumps(data), encoding="utf-8")
        with patch("scripts.fill_expected.run_reference") as mock_run:
            from src.business.campaigns.reference_runner import (
                ReferenceRunResult,
                ReferenceTimeoutError,
            )

            # Let sample succeed, hidden time out
            mock_run.side_effect = [
                ReferenceRunResult("6", "", 0),
                ReferenceTimeoutError("Timed out"),
            ]
            assert (
                fill_expected.main(["scripts/fill_expected.py", str(target)])
                == 1
            )

    def test_successful_fill(self, tmp_path: Path) -> None:
        """Verify successful update of all expected outputs."""
        data = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        data["stages"][0]["samples"][0]["expected_output"] = ""
        target = tmp_path / "fill_me.json"
        target.write_text(json.dumps(data), encoding="utf-8")

        ret = fill_expected.main(["scripts/fill_expected.py", str(target)])
        assert ret == 0

        updated_data = json.loads(target.read_text(encoding="utf-8"))
        sample_out = updated_data["stages"][0]["samples"][0]["expected_output"]
        assert sample_out == "6"


class TestValidateCampaignsScript:
    """Tests for validate_campaigns CLI utility."""

    def test_validate_all_empty_directory(self, tmp_path: Path) -> None:
        """Verify exits 0 when no campaign files are found."""
        ret = validate_campaigns.main(
            ["scripts/validate_campaigns.py", str(tmp_path / "none.json")]
        )
        assert ret == 1

    def test_validate_valid_file(self) -> None:
        """Verify exits 0 on valid campaign fixture."""
        ret = validate_campaigns.main(
            ["scripts/validate_campaigns.py", str(FIXTURE_PATH)]
        )
        assert ret == 0

    def test_validate_invalid_file(self, tmp_path: Path) -> None:
        """Verify exits 1 when validation fails."""
        data = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        data["difficulty"] = "super_hard"
        bad_file = tmp_path / "invalid.json"
        bad_file.write_text(json.dumps(data), encoding="utf-8")

        ret = validate_campaigns.main(
            ["scripts/validate_campaigns.py", str(bad_file)]
        )
        assert ret == 1


class TestSeedScript:
    """Tests for seed CLI utility."""

    @pytest.mark.parametrize(
        "error",
        [
            SQLAlchemyError("db error"),
            CampaignValidationError(["validation failed"]),
            json.JSONDecodeError("bad json", "{", 0),
            OSError("file error"),
        ],
    )
    def test_seed_failure_rolls_back(
        self, tmp_path: Path, error: Exception
    ) -> None:
        """Verify database transaction rolls back on expected errors."""
        mock_session = MagicMock()
        mock_db = MagicMock()
        mock_db.session = mock_session
        with patch("scripts.seed.db", mock_db):
            with patch("scripts.seed.SeedLoader") as mock_loader_cls:
                mock_loader_cls.return_value.load_directory.side_effect = error
                ret = seed.main(["scripts/seed.py", str(tmp_path)])
                assert ret == 1
                mock_session.rollback.assert_called_once()
                mock_db.remove.assert_called_once()

    def test_seed_unhandled_exception_raises(self, tmp_path: Path) -> None:
        """Verify unhandled exceptions bubble up instead of being caught."""
        mock_session = MagicMock()
        mock_db = MagicMock()
        mock_db.session = mock_session
        with patch("scripts.seed.db", mock_db):
            with patch("scripts.seed.SeedLoader") as mock_loader_cls:
                mock_loader_cls.return_value.load_directory.side_effect = (
                    RuntimeError("unexpected boom")
                )
                with pytest.raises(RuntimeError):
                    seed.main(["scripts/seed.py", str(tmp_path)])

    def test_seed_success(self, tmp_path: Path) -> None:
        """Verify successful seeding commits transaction."""
        mock_session = MagicMock()
        mock_db = MagicMock()
        mock_db.session = mock_session
        with patch("scripts.seed.db", mock_db):
            with patch("scripts.seed.SeedLoader") as mock_loader_cls:
                mock_loader_cls.return_value.load_directory.return_value = [
                    MagicMock()
                ]
                ret = seed.main(["scripts/seed.py", str(tmp_path)])
                assert ret == 0
                mock_session.commit.assert_called_once()
                mock_db.remove.assert_called_once()
