"""
File: test_runner_limits_and_slots.py
Description: Unit tests for the runner's production limits (pinned to
    the US6 values so nobody loosens them by accident) and the slot pool.
Author(s): Richard Hall, Tyler Black
"""

import json
import threading
from pathlib import Path
from unittest import mock

import pytest

from src.runner.limits import PRODUCTION_LIMITS, SandboxLimits
from src.runner.slots import (
    RunnerBusyError,
    Slot,
    SlotCompromisedError,
    SlotPool,
    production_slots,
)


def test_production_limits_match_us6():
    assert PRODUCTION_LIMITS.tick_seconds == 1.0
    assert PRODUCTION_LIMITS.run_seconds == 10.0
    assert PRODUCTION_LIMITS.output_bytes == 64 * 1024
    assert PRODUCTION_LIMITS.memory_bytes == 256 * 1024 * 1024
    assert PRODUCTION_LIMITS.cpu_seconds <= 10
    assert PRODUCTION_LIMITS.process_count <= 16
    assert PRODUCTION_LIMITS.open_files <= 64


def test_limits_serialize_for_the_launcher():
    decoded = json.loads(SandboxLimits(memory_bytes=None).to_json())
    assert decoded["memory_bytes"] is None
    assert decoded["code_bytes"] == 64 * 1024


def test_production_slots_match_compose_mounts():
    slots = production_slots()
    assert [slot.uid for slot in slots] == list(range(10001, 10009))
    assert [str(slot.directory) for slot in slots] == [
        f"/sandbox/{index}" for index in range(8)
    ]


def make_pool(tmp_path: Path, size: int) -> SlotPool:
    return SlotPool(
        [Slot(None, tmp_path / str(index)) for index in range(size)]
    )


def test_pool_lends_each_slot_to_one_run_at_a_time(tmp_path: Path):
    pool = make_pool(tmp_path, 1)
    with pool.acquire(timeout=0) as (slot,):
        with pytest.raises(RunnerBusyError):
            with pool.acquire(timeout=0):
                pass
    with pool.acquire(timeout=0) as (slot_again,):
        assert slot_again == slot


def test_pool_lends_several_slots_at_once(tmp_path: Path):
    pool = make_pool(tmp_path, 3)
    with pool.acquire(timeout=0, count=2) as pair:
        assert len(set(pair)) == 2
        with pytest.raises(RunnerBusyError):
            with pool.acquire(timeout=0, count=2):
                pass
        with pool.acquire(timeout=0) as (third,):
            assert third not in pair
    with pool.acquire(timeout=0, count=3) as everything:
        assert len(everything) == 3


def test_pool_waits_for_slots_to_free_up(tmp_path: Path):
    pool = make_pool(tmp_path, 2)
    held = threading.Event()
    release = threading.Event()

    def hold_one() -> None:
        with pool.acquire(timeout=0):
            held.set()
            release.wait(2)

    holder = threading.Thread(target=hold_one)
    holder.start()
    held.wait(2)
    threading.Timer(0.1, release.set).start()
    with pool.acquire(timeout=2, count=2) as pair:
        assert len(pair) == 2
    holder.join()


def test_two_grades_never_deadlock(tmp_path: Path):
    """Each grade takes its two slots together, so neither can starve."""
    pool = make_pool(tmp_path, 2)
    finished: list[int] = []

    def grade(number: int) -> None:
        with pool.acquire(timeout=5, count=2):
            finished.append(number)

    workers = [threading.Thread(target=grade, args=(n,)) for n in (1, 2)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join()
    assert sorted(finished) == [1, 2]


def test_compromised_slots_are_never_lent_again(tmp_path: Path):
    pool = make_pool(tmp_path, 2)
    with mock.patch("src.runner.slots.logger") as logger:
        with pytest.raises(SlotCompromisedError):
            with pool.acquire(timeout=0, count=2):
                raise SlotCompromisedError("left over")
    assert "retiring" in logger.error.call_args.args[0]
    assert pool.retired == 2
    with pytest.raises(RunnerBusyError):
        with pool.acquire(timeout=0):
            pass
