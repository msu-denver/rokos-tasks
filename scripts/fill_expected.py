"""
File: fill_expected.py
Description: Fills expected_output fields in a campaign JSON file by running
    its reference solutions.
Author(s): Tyler Black
"""

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.business.campaigns.reference_runner import (  # noqa: E402
    ReferenceTimeoutError,
    run_reference,
)
from src.business.campaigns.validator import normalize_output  # noqa: E402


def fill_campaign_expected_outputs(file_path: Path) -> int:
    """Populate expected outputs for all tests in a campaign file.

    Args:
        file_path: Path to the target campaign JSON file.

    Returns:
        Exit code: 0 on success, 1 on failure.
    """
    if not file_path.exists():
        print(f"Error: file not found: {file_path}", file=sys.stderr)
        return 1

    try:
        data = json.loads(file_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"Error parsing JSON in {file_path}: {exc}", file=sys.stderr)
        return 1

    stages = data.get("stages", [])
    for stage in stages:
        stage_num = stage.get("stage", "?")
        ref_code = stage.get("reference_solution", "")
        if not ref_code:
            print(
                f"Error: Stage {stage_num} has no reference_solution.",
                file=sys.stderr,
            )
            return 1

        for s_idx, sample in enumerate(stage.get("samples", []), start=1):
            inp = sample.get("input", "")
            try:
                res = run_reference(ref_code, inp)
                if not res.success:
                    print(
                        f"Error: Stage {stage_num} sample {s_idx} failed "
                        f"(code {res.returncode}): {res.stderr.strip()}",
                        file=sys.stderr,
                    )
                    return 1
                sample["expected_output"] = normalize_output(res.stdout)
            except ReferenceTimeoutError:
                print(
                    f"Error: Stage {stage_num} sample {s_idx} timed out.",
                    file=sys.stderr,
                )
                return 1

        for h_idx, hidden in enumerate(stage.get("hidden_tests", []), start=1):
            inp = hidden.get("input", "")
            try:
                res = run_reference(ref_code, inp)
                if not res.success:
                    print(
                        f"Error: Stage {stage_num} hidden {h_idx} failed "
                        f"(code {res.returncode}): {res.stderr.strip()}",
                        file=sys.stderr,
                    )
                    return 1
                hidden["expected_output"] = normalize_output(res.stdout)
            except ReferenceTimeoutError:
                print(
                    f"Error: Stage {stage_num} hidden {h_idx} timed out.",
                    file=sys.stderr,
                )
                return 1

    formatted_json = json.dumps(data, indent=2) + "\n"
    file_path.write_text(formatted_json, encoding="utf-8")
    print(f"Successfully updated expected outputs in {file_path}")
    return 0


def main(argv: list[str]) -> int:
    """Entry point for the fill_expected CLI utility."""
    if len(argv) < 2:
        print("Usage: python scripts/fill_expected.py <path-to-campaign.json>")
        return 1
    return fill_campaign_expected_outputs(Path(argv[1]))


if __name__ == "__main__":  # pragma: no cover - thin CLI entrypoint
    sys.exit(main(sys.argv))
