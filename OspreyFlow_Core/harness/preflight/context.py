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
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from schemas.deployment import OspreyConfig

REPO_ROOT = Path(__file__).resolve().parents[2]

#: Bytes of physical RAM on this machine.
MemoryProbe = Callable[[], int]
#: `(total, used, free)` in bytes, for a path — `shutil.disk_usage`'s own shape.
DiskProbe = Callable[[Path], tuple[int, int, int]]


def default_host_memory_probe() -> int:
    """Physical RAM of whatever process runs this check, via `os.sysconf`. **Not what `memory.py`'s
    own check verdicts on** (round 10 — see that module's own docstring for the false-pass this
    probe alone produced): reported alongside the daemon's own figure as context only, since it is
    real information (how much headroom the host itself has to raise the daemon's own allocation),
    just not the number the twelve containers Launch starts are actually constrained by. Raises on
    a platform without those keys rather than guessing a number."""
    import os

    return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")


def default_host_disk_probe(path: Path) -> tuple[int, int, int]:
    """Free space of whatever filesystem holds `path`, via `shutil.disk_usage` — the host's own
    view, kept for the same "context, not verdict" reason `default_host_memory_probe` states."""
    usage = shutil.disk_usage(path)
    return (usage.total, usage.used, usage.free)


def default_memory_probe(*, runtime: str = "docker") -> int:
    """Bytes of memory the container runtime's own daemon reports itself configured with —
    `docker info --format '{{.MemTotal}}'`, a plain `subprocess` shell-out, the same client
    `harness/images.py`'s own `docker_digest_resolver` already uses (`docker image inspect`) —
    never the Python `docker` SDK, which this project has no dependency on at all.

    **Why this, not `os.sysconf`, round 10.** `default_host_memory_probe` above reads whatever
    process runs Preflight — this host's shell, when Preflight is run directly (`python -m
    harness.preflight`, the shape `harness.apply` and the six-screen live exit test both use). On
    Docker Desktop, every container the daemon starts runs inside one shared Linux VM with its own,
    smaller memory allocation — measured directly, this sandbox's own host reports 36GiB while the
    identical daemon's `MemTotal` reports 9.7GiB. Preflight's `memory` check verdicting on the host
    figure passed on a machine that cannot actually hold the twelve-container deployment it was
    meant to gate — the exact false pass `05_DEPLOYMENT.md` §2.1 forbids: "a check that cannot run
    reports that it did not run — it never reports success." Raises `subprocess.CalledProcessError`/
    `FileNotFoundError`/`subprocess.TimeoutExpired`/`ValueError` when the daemon cannot answer (not
    installed, not running, an unparseable reply) — the memory check turns every one of those into
    a `skip` with the real reason, never a guessed pass."""
    result = subprocess.run(
        [runtime, "info", "--format", "{{.MemTotal}}"],
        capture_output=True,
        text=True,
        timeout=10,
        check=True,
    )
    return int(result.stdout.strip())


def default_disk_probe(_path: Path, *, runtime: str = "docker") -> tuple[int, int, int]:
    """`(total, used, free)` in bytes for the container runtime's own daemon-visible filesystem —
    read via a one-shot container's own `df -k /`, not `docker system df` (reports reclaimable
    image/volume/build-cache usage, not raw filesystem free space) and not `docker info`'s own
    `DockerRootDir` (a path, not a free-space figure `docker info` itself reports anywhere).

    **Why a container's own `df`, not the host path `_path` names, round 10.** `harness/render.py`'s
    own rendered `compose.yaml` declares `osprey-data`/`osprey-staging` as named volumes
    (`driver: local`) — Docker's `local` driver backs a named volume from the daemon's own data
    root, inside the Docker Desktop VM, never from the literal host path `osprey.yaml`'s
    `components.storage.*` names (that string is only the in-container mount point). So the
    filesystem the staged data will actually consume space on is the daemon's own — the same one
    `docker run --rm alpine df -k /` reports from inside a container that daemon just started. This
    accepts `_path` (unused) only to keep `DiskProbe`'s own `Callable[[Path], tuple[int, int, int]]`
    shape, so the `disk` check's own call site needs no branch between the two probes."""
    result = subprocess.run(
        [runtime, "run", "--rm", "alpine", "df", "-k", "/"],
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    fields = result.stdout.strip().splitlines()[-1].split()
    total_kib, used_kib, free_kib = int(fields[1]), int(fields[2]), int(fields[3])
    return total_kib * 1024, used_kib * 1024, free_kib * 1024


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
    analytics_db_path: Path = field(
        default_factory=lambda: (
            REPO_ROOT.parent / "OspreyFlow_Data" / "_local-runtime" / "analytics.duckdb"
        )
    )
    interpreter: Path = field(default_factory=lambda: Path(sys.executable))
    container_runtime: str = "docker"
    memory_probe: MemoryProbe = default_memory_probe
    disk_probe: DiskProbe = default_disk_probe
    #: Round 10 — reported alongside the daemon figure above as context only; never what either
    #: check verdicts on. See `default_host_memory_probe`/`default_host_disk_probe`'s own
    #: docstrings for why the two can genuinely disagree.
    host_memory_probe: MemoryProbe = default_host_memory_probe
    host_disk_probe: DiskProbe = default_host_disk_probe
    #: Bytes of staging volume the deployment is projected to need. A placeholder default, named as
    #: one: nothing in the specification projects this yet, and the check says so rather than
    #: implying the number is derived.
    projected_staging_bytes: int = 20 * 1024**3

    def rendered_compose(self) -> dict[str, Any]:
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
