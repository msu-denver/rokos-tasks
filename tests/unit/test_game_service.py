"""
File: test_game_service.py
Description: Tests campaign selection and run startup without infrastructure.
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
    StageView,
)
from src.data.models.campaign import Campaign, Stage, TestCase
from src.data.models.game_run import GameRun
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
    runs.active_for.return_value = old_run
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
    runs.active_for.return_value = active
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


@pytest.mark.parametrize(
    ("number", "starter"), [(1, "n = int(input())"), (2, None), (2, "# stub")]
)
def test_stage_view_contains_current_prompt_and_public_examples(
    number: int, starter: str | None
) -> None:
    """Expose the prompt and samples while omitting stored starter code."""
    runs = Mock(spec=RunRepository)
    run = GameRun(
        campaign_id=42,
        difficulty="beginner",
        status="in_progress",
        current_stage=number,
        lives=3,
    )
    runs.get_for_user.return_value = run
    runs.current_stage_for.return_value = Stage(
        id=45, prompt="Print twice the input.", starter_code=starter
    )
    runs.samples_for_stage.return_value = [
        TestCase(input="3", expected_output="6", kind="sample"),
    ]

    service = GameService(Mock(spec=CampaignSelector), runs, Mock())
    view = service.get_stage_view(PLAYER_ID, 12)
    assert not hasattr(view, "starter_code")
    assert view == StageView(
        difficulty=Difficulty.BEGINNER,
        number=number,
        lives=3,
        prompt="Print twice the input.",
        samples=({"input": "3", "expected_output": "6"},),
    )
    runs.get_for_user.assert_called_once_with(12, PLAYER_ID)
    runs.current_stage_for.assert_called_once_with(run)
    runs.samples_for_stage.assert_called_once_with(45)


@pytest.mark.parametrize(
    ("prompt", "expected_description"),
    [
        (
            "Double the input.\n\nExample 1 input:\n3\nExample 1 output:\n6",
            "Double the input.",
        ),
        (
            "Double the input.\n\nExample 1 input:\n3\nExample 1 output:\n6"
            "\n\nExample 2 input:\n4\nExample 2 output:\n8",
            "Double the input.",
        ),
        (
            "Double the input.\nPrint the result.",
            "Double the input.\nPrint the result.",
        ),
        (
            "Print the labels for example 1 input: x and Example 1 input: y.",
            "Print the labels for example 1 input: x and Example 1 input: y.",
        ),
    ],
    ids=["one-example", "two-examples", "no-examples", "inline-example"],
)
def test_stage_view_description(
    prompt: str, expected_description: str
) -> None:
    """Strip trailing example blocks while preserving the instructions."""
    stage = StageView(
        difficulty=Difficulty.BEGINNER,
        number=1,
        lives=4,
        prompt=prompt,
        samples=(),
    )

    assert stage.description == expected_description


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
