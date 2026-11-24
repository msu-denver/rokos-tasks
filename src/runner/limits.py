"""
File: limits.py
Description: Resource and time limits for one sandboxed player program,
    and the production values required by US6 (about 1 s per tick, about
    10 s per run, 64 KB of output).
Author(s): Richard Hall
"""

import json
from dataclasses import asdict, dataclass

KILOBYTE = 1024
MEGABYTE = 1024 * KILOBYTE
# One tick's input line, and how many ticks one run or grade may play.
MAX_INPUT_CHARS = 64
MAX_TICKS = 2000


@dataclass(frozen=True)
class SandboxLimits:
    """Limits applied to one player program.

    Attributes:
        tick_seconds: Wall-clock time the program gets to answer one tick.
        run_seconds: Wall-clock time for the whole run, startup included.
        cpu_seconds: CPU time before the kernel kills the program.
        memory_bytes: Address-space cap. ``None`` leaves it unset, which
            only the host-mode unit tests do (macOS rejects this limit).
        file_size_bytes: Largest file the program may write.
        process_count: Processes the sandbox user may own at once.
        output_bytes: Cap on stdout, and separately on stderr.
        code_bytes: Largest accepted source file.
    """

    tick_seconds: float = 1.0
    run_seconds: float = 10.0
    cpu_seconds: int = 10
    memory_bytes: int | None = 256 * MEGABYTE
    file_size_bytes: int = 1 * MEGABYTE
    process_count: int = 16
    output_bytes: int = 64 * KILOBYTE
    code_bytes: int = 64 * KILOBYTE

    def to_json(self) -> str:
        """Return the limits as JSON for the launcher's command line."""
        return json.dumps(asdict(self))


PRODUCTION_LIMITS = SandboxLimits()
