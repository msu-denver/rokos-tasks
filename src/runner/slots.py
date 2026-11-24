"""
File: slots.py
Description: Sandbox slots. Each slot is one unprivileged user with its
    own tmpfs folder, so concurrent runs can't see or touch each other.
    A run borrows a free slot from the pool and returns it when done.
Author(s): Tyler Black
"""

import queue
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

SLOT_COUNT = 4
FIRST_SLOT_UID = 10001
SANDBOX_ROOT = Path("/sandbox")


class RunnerBusyError(Exception):
    """Raised when every slot stays busy for the whole wait."""


@dataclass(frozen=True)
class Slot:
    """One sandbox user and folder.

    Attributes:
        uid: The slot user. ``None`` is host mode, used only by unit tests:
            the program runs as the current user and is killed by process
            group instead of by user.
        directory: The slot's scratch folder (a tmpfs in the container).
    """

    uid: int | None
    directory: Path


class SlotPool:
    """Hands out free slots, one run per slot at a time."""

    def __init__(self, slots: list[Slot]) -> None:
        """Create a pool holding ``slots``, all free."""
        self._free: queue.Queue[Slot] = queue.Queue()
        for slot in slots:
            self._free.put(slot)

    @contextmanager
    def acquire(self, timeout: float) -> Iterator[Slot]:
        """Borrow a free slot for the duration of the ``with`` block.

        Args:
            timeout: Seconds to wait for a slot to free up.

        Yields:
            The borrowed slot.

        Raises:
            RunnerBusyError: If no slot frees up in time.
        """
        try:
            slot = self._free.get(timeout=timeout)
        except queue.Empty as error:
            raise RunnerBusyError("every sandbox slot is busy") from error
        try:
            yield slot
        finally:
            self._free.put(slot)


def production_slots() -> list[Slot]:
    """Return the slots that match the tmpfs mounts in docker-compose.yml."""
    return [
        Slot(FIRST_SLOT_UID + index, SANDBOX_ROOT / str(index))
        for index in range(SLOT_COUNT)
    ]
