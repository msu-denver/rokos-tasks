"""
File: test_runner_limits_and_slots.py
Description: Unit tests for the runner's production limits (pinned to
    the US6 values so nobody loosens them by accident) and the slot pool.
Author(s): Tyler Black
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


def test_limits_serialize_for_the_launcher():
    decoded = json.loads(SandboxLimits(memory_bytes=None).to_json())
    assert decoded["memory_bytes"] is None
    assert decoded["code_bytes"] == 64 * 1024


def test_production_slots_match_compose_mounts():
    slots = production_slots()
    assert [slot.uid for slot in slots] == [10001, 10002, 10003, 10004]
    assert [str(slot.directory) for slot in slots] == [
        "/sandbox/0",
        "/sandbox/1",
        "/sandbox/2",
        "/sandbox/3",
    ]


def test_pool_lends_each_slot_to_one_run_at_a_time(tmp_path: Path):
    pool = SlotPool([Slot(None, tmp_path)])
    with pool.acquire(timeout=0) as slot:
        assert slot.directory == tmp_path
        with pytest.raises(RunnerBusyError):
            with pool.acquire(timeout=0):
                pass
    with pool.acquire(timeout=0) as slot_again:
        assert slot_again == slot


def test_pool_waits_for_a_slot_to_free_up(tmp_path: Path):
    pool = SlotPool([Slot(None, tmp_path)])
    released = threading.Event()

    def hold_then_release() -> None:
        with pool.acquire(timeout=0):
            released.wait(1)

    holder = threading.Thread(target=hold_then_release)
    holder.start()
    threading.Timer(0.1, released.set).start()
    with pool.acquire(timeout=2) as slot:
        assert slot.directory == tmp_path
    holder.join()


def test_compromised_slot_is_never_lent_again(tmp_path: Path):
    pool = SlotPool([Slot(None, tmp_path)])
    with mock.patch("src.runner.slots.logger") as logger:
        with pytest.raises(SlotCompromisedError):
            with pool.acquire(timeout=0):
                raise SlotCompromisedError("left over")
    assert "retiring" in logger.error.call_args.args[0]
    with pytest.raises(RunnerBusyError):
        with pool.acquire(timeout=0):
            pass
