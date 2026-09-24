"""What every check reads: the deployment as rendered, plus the probes that reach the machine.

**Preflight checks the rendered deployment, not `osprey.yaml` directly.** The ports a check must
find free are the ports the *compose file* declares, not the ports someone believes the profile
implies — `06_DECISIONS.md` ADR-049's Stage 2 §2 is explicit that this reads
`deploy/generated/<profile>/` from Stage 2 §1. That is also what makes the port check's planted
failure honest: the test binds a socket on a port read out of a real rendered compose file.

**The probes are a seam, and a narrow one.** Total system memory, free disk, whether a TCP port
accepts a bind — none of those can be planted on a real machine by a test, so each is reached
through a small injectable callable whose return shape is exactly what the real one returns (an
integer of bytes, a `shutil.disk_usage` triple). Everything a test *can* plant for real — a bound
port, a `file://` tile URL in a rendered config, a system-Python interpreter path, a process holding
the DuckDB file — is planted for real, with no seam at all. The line is drawn at "can this machine
actually be put into that state", not at "is a fake more convenient".
"""

from __future__ import annotations

import shutil
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from schemas.deployment import OspreyConfig

REPO_ROOT = Path(__file__).resolve().parents[2]

#: Bytes of physical RAM on this machine.
MemoryProbe = Callable[[], int]
#: `(total, used, free)` in bytes, for a path — `shutil.disk_usage`'s own shape.
DiskProbe = Callable[[Path], tuple[int, int, int]]


def default_memory_probe() -> int:
    """Physical RAM, via `os.sysconf`. Raises on a platform without those keys rather than guessing
    a number — the memory check turns that into a `skip` with a reason, which is honest, where a
    guessed default would be a `pass` nobody could trust."""
    import os

    return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")


def default_disk_probe(path: Path) -> tuple[int, int, int]:
    usage = shutil.disk_usage(path)
    return (usage.total, usage.used, usage.free)


@dataclass
class PreflightContext:
    """Everything the checks read, assembled once so a `--only` run and a full run see the same
    world."""

    config: OspreyConfig
    #: `deploy/generated/<profile>/` — Stage 2 §1's output for this profile.
    out_dir: Path
    #: True when the operator is about to seed; the DuckDB lock check is about seeding specifically.
    seeding: bool = False
    #: Where the Conduit's analytics store lives (`services/api/config.py`'s own default).
    analytics_db_path: Path = field(default_factory=lambda: REPO_ROOT / "data" / "analytics.duckdb")
    interpreter: Path = field(default_factory=lambda: Path(sys.executable))
    container_runtime: str = "docker"
    memory_probe: MemoryProbe = default_memory_probe
    disk_probe: DiskProbe = default_disk_probe
    #: Bytes of staging volume the deployment is projected to need. A placeholder default, named as
    #: one: nothing in the specification projects this yet, and the check says so rather than
    #: implying the number is derived.
    projected_staging_bytes: int = 20 * 1024**3

    def rendered_compose(self) -> dict:
        """The compose file Stage 2 §1 wrote for this profile. Raises `RenderedOutputMissing` when
        it is absent, which the runner turns into a single clear failure rather than letting five
        checks each fail with their own `FileNotFoundError`."""
        path = self.out_dir / "compose.yaml"
        if not path.is_file():
            raise RenderedOutputMissing(path)
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


class RenderedOutputMissing(FileNotFoundError):
    """Nothing has been rendered for this profile yet. A distinct type because the remedy is one
    command, and repeating it in five checks' own `what_to_do` would be five chances to word it
    differently."""

    def __init__(self, path: Path) -> None:
        self.path = path
        super().__init__(
            f"{path} does not exist — run `python -m harness.render` for this profile first"
        )
