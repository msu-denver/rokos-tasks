"""
File: test_pong_in_container.py
Description: Grades ASCII Pong stage 3 through the real runner container
    (POST /grade) under production limits: the reference passes and a
    broken program fails with its rule, both well inside the 10-second
    run limit (US6 AC1).
Author(s): Richard Hall
"""

import json
import time
from pathlib import Path

from tests.runner.conftest import GradeInSandbox

ROOT = Path(__file__).resolve().parents[2]
PONG = json.loads(
    (ROOT / "content/campaigns/seed/medium/pong.json").read_text("utf-8")
)
STAGE_3 = PONG["stages"][2]
# Includes the docker exec round trip, so it is looser than the run limit.
GRADE_SECONDS = 10.0


def timed_grade(grade: GradeInSandbox, code: str) -> tuple[dict, float]:
    started = time.monotonic()
    verdict = grade(code, STAGE_3["check_script"])
    return verdict, time.monotonic() - started


def test_reference_passes_in_container(grade_in_sandbox: GradeInSandbox):
    verdict, seconds = timed_grade(
        grade_in_sandbox, STAGE_3["reference_solution"]
    )
    assert verdict["verdict"] == "pass"
    assert seconds < GRADE_SECONDS


def test_broken_program_fails_in_container(grade_in_sandbox: GradeInSandbox):
    broken = ROOT / "tests/fixtures/pong/stage3_ball_through_paddle.py"
    verdict, seconds = timed_grade(grade_in_sandbox, broken.read_text())
    assert verdict["reason"] == "rule"
    assert "bounce off the right paddle" in verdict["rule"]
    assert seconds < GRADE_SECONDS
