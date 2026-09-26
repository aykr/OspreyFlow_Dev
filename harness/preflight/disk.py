"""Free disk against the projected staging volume — `05_DEPLOYMENT.md` §2.1's second check.

**The projection is a placeholder and is labelled as one.** Nothing in the specification derives a
staging volume from a deployment's own inputs yet: §2.1 says "disk against the projected staging
volume" without saying what projects it. This check compares free space at the configured staging
root against `PreflightContext.projected_staging_bytes`, whose default is a round 20GiB — and the
failure wording names it as an assumption rather than presenting it as a computed requirement.
Raised as a gap in `05_DEPLOYMENT.md` §2.1 rather than quietly invented here.

**Verdicts on the container runtime's own filesystem, not this process's own host — round 10, the
same finding `memory.py`'s own docstring has the full account of.** `harness/render.py`'s own
rendered `compose.yaml` backs `osprey-data`/`osprey-staging` as named volumes (`driver: local`) —
Docker's `local` driver stores a named volume's own data inside the daemon's data root, never at
the literal host path `osprey.yaml`'s `components.storage.*` names (that string is only the
in-container mount point). So free space at the *host* path this check used to measure was never
the figure the staged data would actually run out of. `context.disk_probe()` now reads the
runtime's own filesystem, via a one-shot container's `df` (`context.py`'s own docstring has why,
over `docker system df`/`docker info`); the host path's own free space
(`context.host_disk_probe()`) is still read and still reported, in `detail`, as context only.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from harness.preflight.context import PreflightContext
from harness.preflight.result import CheckResult, failed, passed, skipped

NAME = "disk"


def _gib(value: int) -> str:
    return f"{value / 1024**3:.1f}GiB"


def _nearest_existing(path: Path) -> Path:
    """Free space is a property of the filesystem, not of a directory that does not exist yet. A
    staging root the deployment has not created is normal at Preflight time, so walk up to the
    nearest parent that does exist rather than failing on a missing directory — that would report a
    disk problem for what is actually a not-yet-created path."""
    candidate = path
    while not candidate.exists() and candidate != candidate.parent:
        candidate = candidate.parent
    return candidate


def check(context: PreflightContext) -> CheckResult:
    staging = Path(context.config.components.storage.staging)
    measured_at = _nearest_existing(staging)
    required = context.projected_staging_bytes

    try:
        _total, _used, free = context.disk_probe(measured_at)
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        return skipped(
            NAME,
            reason=(
                f"the container runtime's own filesystem could not be read ({error}), so the "
                "staging-volume floor was not checked at all — never a pass on a runtime that "
                "could not be reached"
            ),
        )

    try:
        _host_total, _host_used, host_free = context.host_disk_probe(measured_at)
        host_note = f"this host's own free space at {measured_at}: {_gib(host_free)}"
    except OSError as error:
        host_note = f"host free space could not be read ({error})"

    detail = (
        f"staging root: {staging}",
        "free space measured at: the container runtime's own filesystem",
        f"free: {_gib(free)}",
        f"projected staging volume: {_gib(required)} (an assumed default, not a derived figure)",
        host_note,
    )
    if free >= required:
        return passed(NAME, detail=detail)

    return failed(
        NAME,
        what_is_wrong=(
            f"the container runtime's own filesystem has {_gib(free)} free and this deployment "
            f"is projected to need {_gib(required)}. Staged Parquet is the layer every migration "
            "and every rebuild replays from, so running it out of space loses the recovery path, "
            "not just the next load."
        ),
        what_to_do=(
            "Free space in the container runtime's own storage (on Docker Desktop: Settings → "
            "Resources → Disk usage, or `docker system prune`), or point components.storage."
            "staging at a larger volume in osprey.yaml and re-render. If the projection itself is "
            "wrong for your data, it is an assumed 20GiB default rather than a figure derived "
            "from your sources — override it deliberately rather than working around it."
        ),
        detail=detail,
    )
