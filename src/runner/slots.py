"""
File: slots.py
Description: Sandbox slots. Each slot is one unprivileged user with its
    own tmpfs folder, so concurrent runs can't see or touch each other.
    A run borrows free slots from the pool (a grade takes two at once:
    one for the player, one for the check script) and returns them.
Author(s): Richard Hall, Tyler Black
"""

import logging
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import PurePath, PurePosixPath

SLOT_COUNT = 8
FIRST_SLOT_UID = 10001
FIRST_REAPER_UID = 20001
SANDBOX_ROOT = PurePosixPath("/sandbox")

logger = logging.getLogger(__name__)


class RunnerBusyError(Exception):
    """Raised when every slot stays busy for the whole wait."""


class SlotCompromisedError(Exception):
    """Raised when a slot couldn't be cleaned after a run.

    Processes from the last run might still be alive under the slot's
    user, so the pool never lends that slot out again.
    """


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
    directory: PurePath


class SlotPool:
    """Hands out free slots, one run per slot at a time."""

    def __init__(self, slots: list[Slot]) -> None:
        """Create a pool holding ``slots``, all free."""
        self._free = list(slots)
        self._changed = threading.Condition()
        self._retired = 0

    @property
    def retired(self) -> int:
        """Return the number of slots retired after cleanup failed."""
        with self._changed:
            return self._retired

    @contextmanager
    def acquire(self, timeout: float, count: int = 1) -> Iterator[list[Slot]]:
        """Borrow ``count`` free slots for the ``with`` block.

        All of them are taken at once, so two grades that each need two
        slots can never deadlock holding one each.

        Args:
            timeout: Seconds to wait for enough slots to free up.
            count: How many slots to borrow.

        Yields:
            The borrowed slots.

        Raises:
            RunnerBusyError: If not enough slots free up in time.
            SlotCompromisedError: Passed through from the block. The slots
                are retired instead of returned.
        """
        with self._changed:
            if not self._changed.wait_for(
                lambda: len(self._free) >= count, timeout
            ):
                raise RunnerBusyError("every sandbox slot is busy")
            taken = [self._free.pop(0) for _ in range(count)]
        retired = False
        try:
            yield taken
        except SlotCompromisedError:
            retired = True
            with self._changed:
                self._retired += len(taken)
            logger.error("retiring %s: they could not be cleaned", taken)
            raise
        finally:
            if not retired:
                with self._changed:
                    self._free.extend(taken)
                    self._changed.notify_all()


def production_slots() -> list[Slot]:
    """Return the slots that match the tmpfs mounts in docker-compose.yml."""
    return [
        Slot(FIRST_SLOT_UID + index, SANDBOX_ROOT / str(index))
        for index in range(SLOT_COUNT)
    ]
