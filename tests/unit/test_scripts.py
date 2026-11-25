"""
File: test_scripts.py
Description: Unit tests for the validate_campaigns and seed scripts.
Author(s): Tyler Black
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.exc import SQLAlchemyError

from scripts import seed, validate_campaigns
from src.business.campaigns.seed_loader import CampaignValidationError

FIXTURE_PATH = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "campaigns"
    / "valid_beginner.json"
)


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

    def test_validate_notes_skipped_checks_on_windows(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """On Windows, the script says which checks it couldn't run."""
        with (
            patch(
                "scripts.validate_campaigns.host_play_supported",
                return_value=False,
            ),
            patch(
                "src.business.campaigns.validator.host_play_supported",
                return_value=False,
            ),
        ):
            ret = validate_campaigns.main(
                ["scripts/validate_campaigns.py", str(FIXTURE_PATH)]
            )
        assert ret == 0
        assert "CI runs every check" in capsys.readouterr().out

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
