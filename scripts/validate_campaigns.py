"""
File: validate_campaigns.py
Description: Validates all seed campaign JSON files against schema and rules.
Author(s): Tyler Black
"""

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.business.campaigns.check_runner import (  # noqa: E402
    host_play_supported,
)
from src.business.campaigns.validator import CampaignValidator  # noqa: E402


def validate_all_campaigns(paths: list[Path]) -> int:
    """Validate all given campaign files and report errors.

    Args:
        paths: List of campaign JSON files to validate.

    Returns:
        0 if all campaigns are valid, 1 otherwise.
    """
    if not paths:
        print("No campaign files found to validate.")
        return 0

    all_errors: list[str] = []
    for file_path in paths:
        errors = CampaignValidator.validate_file(file_path)
        if errors:
            all_errors.extend(errors)

    if all_errors:
        print(f"Validation failed with {len(all_errors)} error(s):")
        for err in all_errors:
            print(f"  - {err}")
        return 1

    print(f"All {len(paths)} campaign file(s) valid.")
    if not host_play_supported():
        print(
            "Note: this machine can't play programs (Windows), so only the "
            "checks that don't play one ran. CI runs every check."
        )
    return 0


def main(argv: list[str]) -> int:
    """Entry point for the validate_campaigns CLI utility."""
    if len(argv) > 1:
        paths = [Path(arg) for arg in argv[1:]]
    else:
        seed_dir = Path("content/campaigns/seed")
        paths = sorted(seed_dir.rglob("*.json")) if seed_dir.exists() else []
    return validate_all_campaigns(paths)


if __name__ == "__main__":  # pragma: no cover - thin CLI entrypoint
    sys.exit(main(sys.argv))
