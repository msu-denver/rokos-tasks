"""
File: test_game_service.py
Description: Tests campaign selection, run startup, and stage progression.
Author(s): Tyler Black
"""

import subprocess
import sys
from datetime import UTC, datetime, timedelta
from textwrap import dedent
from unittest.mock import Mock

import pytest

from src.business.campaign_selector import (
    CampaignSelector,
    NoCampaignAvailableError,
)
from src.business.difficulty import Difficulty
from src.business.game_service import (
    ActiveRunExistsError,
    GameService,
    ResultRow,
    ResultView,
    RunState,
    StageView,
    StaleSubmitError,
)
from src.business.grading_service import (
    GradingService,
    InvalidCodeError,
    StageNotGradableError,
    Verdict,
)
from src.business.runner_client import (
    CheckScriptBrokenError,
    RunnerUnavailableError,
)
from src.data.models.campaign import Campaign, Stage
from src.data.models.checkpoint import Checkpoint
from src.data.models.game_run import GameRun
from src.data.models.submission import Submission
from src.data.repositories.campaign_repository import CampaignRepository
from src.data.repositories.run_repository import RunRepository

NOW = datetime(2026, 11, 18, 15, 0, tzinfo=UTC)
EARLIER = NOW - timedelta(days=1)
PLAYER_ID = 7


@pytest.mark.parametrize(
    ("history", "selected_id"),
    [
        ({1: EARLIER}, 2),
        ({1: NOW, 2: EARLIER, 3: EARLIER}, 2),
        ({1: NOW, 2: NOW, 3: NOW}, 1),
    ],
)
def test_selector_uses_validated_tier_pool_and_player_history(
    history: dict[int, datetime], selected_id: int
) -> None:
    """Choose unplayed first, then least recently started, then lowest ID."""
    campaigns = Mock(spec=CampaignRepository)
    campaigns.validated_for.return_value = [
        Campaign(id=number) for number in (3, 1, 2)
    ]
    runs = Mock(spec=RunRepository)
    runs.last_started_by_user.return_value = history

    selected = CampaignSelector(campaigns, runs).choose(
        PLAYER_ID, Difficulty.BEGINNER
    )

    assert selected.id == selected_id
    campaigns.validated_for.assert_called_once_with(Difficulty.BEGINNER)
    runs.last_started_by_user.assert_called_once_with(PLAYER_ID)


def test_selector_raises_when_tier_has_no_validated_campaigns() -> None:
    """Fail an empty selection without querying unrelated player history."""
    campaigns = Mock(spec=CampaignRepository)
    campaigns.validated_for.return_value = []
    runs = Mock(spec=RunRepository)

    with pytest.raises(NoCampaignAvailableError):
        CampaignSelector(campaigns, runs).choose(PLAYER_ID, Difficulty.HARD)

    runs.last_started_by_user.assert_not_called()


def test_start_run_records_first_stage_and_abandons_previous_run() -> None:
    """Use the tier's lives and one UTC timestamp for the replacement."""
    old_run = GameRun(id=12, status="in_progress", score=50)
    selector = Mock(spec=CampaignSelector)
    selector.choose.return_value = Campaign(id=42)
    runs = Mock(spec=RunRepository)
    runs.active_for.return_value = runs.lock_for_user.return_value = old_run
    clock = Mock(return_value=NOW)

    run = GameService(selector, runs, clock).start_run(
        PLAYER_ID, Difficulty.EASY, replace_active=True, expected_active_id=12
    )

    assert (run.user_id, run.campaign_id, run.difficulty) == (7, 42, "easy")
    assert (run.status, run.current_stage, run.lives, run.score) == (
        "in_progress",
        1,
        3,
        0,
    )
    assert run.started_at == run.stage_started_at == NOW
    assert run.ended_at is None
    assert (old_run.status, old_run.score, old_run.ended_at) == (
        "abandoned",
        0,
        NOW,
    )
    selector.choose.assert_called_once_with(PLAYER_ID, Difficulty.EASY)
    runs.lock_for_user.assert_called_once_with(12, PLAYER_ID)
    runs.add.assert_called_once_with(run)
    runs.commit.assert_called_once_with()
    clock.assert_called_once_with()


@pytest.mark.parametrize(
    ("replace_active", "expected_active_id"),
    [(False, None), (True, 11)],
    ids=["unconfirmed", "stale-confirmation"],
)
def test_start_run_requires_confirmation_for_current_run(
    replace_active: bool, expected_active_id: int | None
) -> None:
    """Keep the active run intact until its replacement is confirmed."""
    active = GameRun(id=12, status="in_progress", score=50)
    runs = Mock(spec=RunRepository)
    runs.active_for.return_value = runs.lock_for_user.return_value = active
    clock = Mock()
    service = GameService(Mock(spec=CampaignSelector), runs, clock)

    with pytest.raises(ActiveRunExistsError) as error:
        service.start_run(
            PLAYER_ID,
            Difficulty.EASY,
            replace_active=replace_active,
            expected_active_id=expected_active_id,
        )

    assert error.value.run_id == 12
    assert (active.status, active.score, active.ended_at) == (
        "in_progress",
        50,
        None,
    )
    runs.lock_player.assert_called_once_with(PLAYER_ID)
    runs.add.assert_not_called()
    runs.commit.assert_not_called()
    clock.assert_not_called()


@pytest.mark.parametrize("status", ["won", "lost"])
def test_start_run_keeps_a_run_that_ended_while_locking(status: str) -> None:
    """Never abandon a run a final submit finished before the lock."""
    seen = GameRun(id=12, status="in_progress", score=50)
    finished = GameRun(id=12, status=status, score=300)
    selector = Mock(spec=CampaignSelector)
    selector.choose.return_value = Campaign(id=42)
    runs = Mock(spec=RunRepository)
    runs.active_for.return_value = seen
    runs.lock_for_user.return_value = finished

    run = GameService(selector, runs, Mock(return_value=NOW)).start_run(
        PLAYER_ID, Difficulty.EASY
    )

    assert run.status == "in_progress"
    assert (finished.status, finished.score) == (status, 300)
    runs.commit.assert_called_once_with()


def test_start_run_without_campaign_does_not_abandon_active_run() -> None:
    """Keep the current run when its replacement cannot be assigned."""
    selector = Mock(spec=CampaignSelector)
    selector.choose.side_effect = NoCampaignAvailableError
    runs = Mock(spec=RunRepository)

    with pytest.raises(NoCampaignAvailableError):
        GameService(selector, runs, Mock()).start_run(
            PLAYER_ID, Difficulty.HARD, replace_active=True
        )

    runs.active_for.assert_not_called()
    runs.add.assert_not_called()
    runs.commit.assert_not_called()


@pytest.mark.parametrize("number", [1, 2])
def test_stage_view_contains_only_the_current_prompt(number: int) -> None:
    """Expose the stage's prompt and progress, never its grading data."""
    runs = Mock(spec=RunRepository)
    run = GameRun(
        campaign_id=42,
        difficulty="beginner",
        status="in_progress",
        current_stage=number,
        lives=3,
    )
    runs.get_for_user.return_value = run
    runs.latest_checkpoint.return_value = (
        None if number == 1 else Checkpoint(code="previous program")
    )
    runs.current_stage_for.return_value = Stage(
        id=45,
        prompt="Print twice the input.",
        reference_program="secret reference",
        check_script="secret check",
    )

    service = GameService(Mock(spec=CampaignSelector), runs, Mock())
    view = service.get_stage_view(PLAYER_ID, 12)
    assert view == StageView(
        difficulty=Difficulty.BEGINNER,
        number=number,
        lives=3,
        prompt="Print twice the input.",
        checkpoint_code=None if number == 1 else "previous program",
    )
    assert "secret" not in repr(view)
    runs.get_for_user.assert_called_once_with(12, PLAYER_ID)
    runs.current_stage_for.assert_called_once_with(run)


def test_start_run_does_not_import_an_llm_client() -> None:
    """Reject LLM imports during module loading and run creation."""
    script = dedent(
        """\
        import sys
        from datetime import UTC, datetime
        from unittest.mock import Mock

        class RejectLLM:
            def find_spec(self, fullname, path=None, target=None):
                if fullname.split(".")[:3] == ["src", "business", "llm"]:
                    raise AssertionError(f"LLM module imported: {fullname}")
                if fullname.split(".")[0] == "openai":
                    raise AssertionError(f"LLM client imported: {fullname}")

        sys.meta_path.insert(0, RejectLLM())

        from src.business.campaign_selector import CampaignSelector
        from src.business.difficulty import Difficulty
        from src.business.game_service import GameService
        from src.data.models.campaign import Campaign
        from src.data.repositories import CampaignRepository, RunRepository

        campaigns = Mock(spec=CampaignRepository)
        campaigns.validated_for.return_value = [Campaign(id=42)]
        runs = Mock(spec=RunRepository)
        runs.last_started_by_user.return_value = {}
        runs.active_for.return_value = None
        selector = CampaignSelector(campaigns, runs)
        service = GameService(selector, runs, lambda: datetime.now(UTC))
        assert service.start_run(7, Difficulty.EASY).campaign_id == 42
        runs.commit.assert_called_once_with()
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, result.stderr


RUN_ID = 12
ARRIVED = NOW + timedelta(seconds=293)
APPLIED = NOW + timedelta(seconds=303)
CODE = "print('ready')"
PASS = Verdict(True, "PASS", None, None, 3, (), None, "")
FAIL = Verdict(False, "FAIL", "rule", "Print ready.", 2, (), None, "")


@pytest.fixture
def submit_game() -> tuple[GameService, Mock, Mock, GameRun]:
    """Provide an Easy run whose attempt arrives with seven seconds left."""
    run = GameRun(
        id=RUN_ID,
        current_stage=1,
        stage_started_at=NOW,
        difficulty="easy",
        status="in_progress",
        lives=3,
        score=0,
    )
    runs = Mock(spec=RunRepository)
    runs.get_for_user.return_value = runs.lock_for_user.return_value = run
    runs.stage_count.return_value = 3
    runs.latest_checkpoint.return_value = None
    runs.current_stage_for.return_value = Stage(prompt="Next prompt.")

    def save_checkpoint(checkpoint: Checkpoint) -> Checkpoint:
        runs.latest_checkpoint.return_value = checkpoint
        return checkpoint

    runs.save_checkpoint.side_effect = save_checkpoint
    grading = Mock(spec=GradingService)
    grading.grade.return_value = PASS
    service = GameService(
        Mock(spec=CampaignSelector),
        runs,
        Mock(side_effect=[ARRIVED, APPLIED]),
        grading=grading,
    )
    return service, runs, grading, run


def test_submit_pass_advances_using_arrival_time(
    submit_game: tuple[GameService, Mock, Mock, GameRun],
) -> None:
    """Advance, save code, and award points for time left at arrival."""
    service, runs, grading, run = submit_game
    result = service.submit_stage(PLAYER_ID, RUN_ID, CODE, run.current_stage)

    checkpoint = runs.save_checkpoint.call_args.args[0]
    assert (checkpoint.run_id, checkpoint.stage_number) == (RUN_ID, 1)
    assert (checkpoint.code, checkpoint.saved_at) == (CODE, APPLIED)
    sub = runs.add_submission.call_args.args[0]
    assert (sub.run_id, sub.stage_number, sub.code) == (RUN_ID, 1, CODE)
    assert sub.passed is True
    assert (sub.failure_kind, sub.failed_rule, sub.failed_turn) == (None,) * 3
    assert (sub.seconds_remaining, sub.submitted_at) == (7, ARRIVED)
    assert (run.current_stage, run.stage_started_at, run.score) == (
        2,
        APPLIED,
        142,
    )
    assert result.run == RunState("in_progress", 3, 2, 142, 142)
    assert result.next_stage == StageView(
        Difficulty.EASY, 2, 3, "Next prompt.", CODE
    )
    assert result.checkpoint_code == CODE
    assert result.to_dict() == {
        "verdict": PASS.to_dict(),
        "run": {
            "status": "in_progress",
            "lives": 3,
            "stage": 2,
            "score": 142,
            "stage_points": 142,
        },
        "stage": {"number": 2, "prompt": "Next prompt."},
        "checkpoint": CODE,
    }
    grading.grade.assert_called_once_with(PLAYER_ID, RUN_ID, CODE)
    runs.commit.assert_called_once_with()


def test_submit_pass_at_last_stage_wins(
    submit_game: tuple[GameService, Mock, Mock, GameRun],
) -> None:
    """Finish the run at its final stage, with nothing to restore."""
    service, runs, _, run = submit_game
    run.current_stage = 3
    run.score = 250

    result = service.submit_stage(PLAYER_ID, RUN_ID, CODE, run.current_stage)

    assert result.run == RunState("won", 3, 3, 392, 142)
    assert result.next_stage is None
    assert result.checkpoint_code is None
    runs.latest_checkpoint.assert_not_called()
    assert result.to_dict()["stage"] is None
    assert run.ended_at == APPLIED
    runs.current_stage_for.assert_not_called()
    runs.commit.assert_called_once_with()


def test_submit_failure_resets_time_and_exposes_checkpoint(
    submit_game: tuple[GameService, Mock, Mock, GameRun],
) -> None:
    """Record the failing rule and restore the previous stage's code."""
    service, runs, grading, run = submit_game
    run.current_stage = 2
    run.score = 250
    grading.grade.return_value = FAIL
    runs.latest_checkpoint.return_value = Checkpoint(code="previous code")

    result = service.submit_stage(PLAYER_ID, RUN_ID, CODE, run.current_stage)

    assert result.run == RunState("in_progress", 2, 2, 250, 0)
    assert result.next_stage is None
    assert result.checkpoint_code == "previous code"
    assert run.stage_started_at == APPLIED
    sub = runs.add_submission.call_args.args[0]
    assert sub.passed is False
    assert (sub.failure_kind, sub.failed_rule, sub.failed_turn) == (
        "rule",
        "Print ready.",
        2,
    )
    runs.save_checkpoint.assert_not_called()
    runs.commit.assert_called_once_with()


def test_last_life_failure_loses_and_zeros_score(
    submit_game: tuple[GameService, Mock, Mock, GameRun],
) -> None:
    """End the run with no points after the final life is spent."""
    service, runs, grading, run = submit_game
    run.lives = 1
    run.score = 300
    grading.grade.return_value = Verdict(
        False, "FAIL", "crashed", "Crashed.", 1, (), None, ""
    )

    result = service.submit_stage(PLAYER_ID, RUN_ID, CODE, run.current_stage)

    assert result.run == RunState("lost", 0, 1, 0, 0)
    assert result.next_stage is result.checkpoint_code is None
    assert (run.ended_at, run.stage_started_at) == (APPLIED, NOW)
    sub = runs.add_submission.call_args.args[0]
    assert (sub.failure_kind, sub.failed_rule, sub.failed_turn) == (
        "crashed",
        None,
        1,
    )
    runs.commit.assert_called_once_with()


@pytest.mark.parametrize(
    "error",
    [
        InvalidCodeError,
        RunnerUnavailableError,
        CheckScriptBrokenError,
        StageNotGradableError,
    ],
)
def test_grading_error_never_writes(
    submit_game: tuple[GameService, Mock, Mock, GameRun],
    error: type[Exception],
) -> None:
    """Propagate grader errors before acquiring a lock or writing data."""
    service, runs, grading, run = submit_game
    grading.grade.side_effect = error

    with pytest.raises(error):
        service.submit_stage(PLAYER_ID, RUN_ID, CODE, run.current_stage)

    assert (run.lives, run.current_stage, run.score) == (3, 1, 0)
    runs.lock_for_user.assert_not_called()
    runs.add_submission.assert_not_called()
    runs.save_checkpoint.assert_not_called()
    runs.commit.assert_not_called()


@pytest.mark.parametrize(
    "locked_run",
    [
        None,
        GameRun(status="lost"),
        GameRun(status="in_progress", current_stage=2, stage_started_at=NOW),
        GameRun(
            status="in_progress", current_stage=1, stage_started_at=APPLIED
        ),
    ],
    ids=["missing", "lost", "advanced", "reset"],
)
def test_stale_submit_rolls_back(
    submit_game: tuple[GameService, Mock, Mock, GameRun],
    locked_run: GameRun | None,
) -> None:
    """Discard the verdict if the locked run differs from the snapshot."""
    service, runs, _, _ = submit_game
    runs.lock_for_user.return_value = locked_run

    with pytest.raises(StaleSubmitError):
        service.submit_stage(PLAYER_ID, RUN_ID, CODE, 1)

    runs.rollback.assert_called_once_with()
    runs.add_submission.assert_not_called()
    runs.commit.assert_not_called()


@pytest.mark.parametrize(
    ("current", "shown"), [(2, 1), (1, 2)], ids=["behind", "ahead"]
)
def test_submit_for_another_stage_is_stale(
    submit_game: tuple[GameService, Mock, Mock, GameRun],
    current: int,
    shown: int,
) -> None:
    """An old page's submit is refused before grading costs a life."""
    service, runs, grading, run = submit_game
    run.current_stage = current

    with pytest.raises(StaleSubmitError):
        service.submit_stage(PLAYER_ID, RUN_ID, CODE, shown)

    assert (run.lives, run.current_stage) == (3, current)
    grading.grade.assert_not_called()
    runs.add_submission.assert_not_called()
    runs.commit.assert_not_called()


@pytest.mark.parametrize(("status", "total"), [("won", 267), ("lost", 0)])
def test_finished_result_view(
    submit_game: tuple[GameService, Mock, Mock, GameRun],
    status: str,
    total: int,
) -> None:
    """Recompute passing stage points while preserving the run total."""
    service, runs, _, run = submit_game
    run.status, run.score = status, total
    runs.passed_submissions.return_value = [
        Submission(stage_number=1, seconds_remaining=7),
        Submission(stage_number=2, seconds_remaining=0),
    ]

    assert service.get_result_view(PLAYER_ID, RUN_ID) == ResultView(
        Difficulty.EASY, status, (ResultRow(1, 142), ResultRow(2, 125)), total
    )


@pytest.mark.parametrize("status", ["in_progress", "abandoned"])
def test_result_view_requires_won_or_lost_run(
    submit_game: tuple[GameService, Mock, Mock, GameRun], status: str
) -> None:
    """Return no breakdown for an active or abandoned run."""
    service, runs, _, run = submit_game
    run.status = status

    assert service.get_result_view(PLAYER_ID, RUN_ID) is None
    runs.passed_submissions.assert_not_called()


def test_submit_requires_grader() -> None:
    """Reject submissions when configured for read and start actions only."""
    runs = Mock(spec=RunRepository)
    service = GameService(Mock(spec=CampaignSelector), runs, Mock())

    with pytest.raises(RuntimeError, match="no grading service configured"):
        service.submit_stage(PLAYER_ID, RUN_ID, CODE, 1)

    runs.get_for_user.assert_not_called()
