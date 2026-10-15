"""The Set-up console for the keyboard suite, on a host of fixed size.

The keyboard walkthrough proves every Preflight action is reachable and that Launch enables once
the checks pass; whether this machine has the 16 GiB of memory and 20 GiB of disk `local-lite`
needs is Preflight's own tests' question, not this one's. A hosted CI runner has 7.8 GiB, so with
the real probes the walkthrough could never reach Launch there (CI, 15 October 2026). This starts
the real console with its memory and disk probes reporting a host comfortably above both floors;
every check still runs, and everything else the suite touches is real. Launch's own command is
already a stand-in (`playwright.config.ts`'s `--apply-command`), for the same reason.
"""

from __future__ import annotations

import functools
from pathlib import Path

from harness import webapp
from harness.preflight.context import PreflightContext

GIB = 1024**3
MEMORY = 32 * GIB
DISK_FREE = 200 * GIB


def _memory() -> int:
    return MEMORY


def _disk(_path: Path) -> tuple[int, int, int]:
    return (2 * DISK_FREE, DISK_FREE, DISK_FREE)


webapp.PreflightContext = functools.partial(  # type: ignore[misc]
    PreflightContext,
    memory_probe=_memory,
    disk_probe=_disk,
    host_memory_probe=_memory,
    host_disk_probe=_disk,
)

if __name__ == "__main__":
    raise SystemExit(webapp.main())
