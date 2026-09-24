"""Free disk against the projected staging volume — `05_DEPLOYMENT.md` §2.1's second check.

**The projection is a placeholder and is labelled as one.** Nothing in the specification derives a
staging volume from a deployment's own inputs yet: §2.1 says "disk against the projected staging
volume" without saying what projects it. This check compares free space at the configured staging
root against `PreflightContext.projected_staging_bytes`, whose default is a round 20GiB — and the
failure wording names it as an assumption rather than presenting it as a computed requirement.
Raised as a gap in `05_DEPLOYMENT.md` §2.1 rather than quietly invented here.
"""

from __future__ import annotations

from pathlib import Path

from harness.preflight.context import PreflightContext
from harness.preflight.result import CheckResult, failed, passed

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
    _total, _used, free = context.disk_probe(measured_at)
    required = context.projected_staging_bytes

    detail = (
        f"staging root: {staging}",
        f"free space measured at: {measured_at}",
        f"free: {_gib(free)}",
        f"projected staging volume: {_gib(required)} (an assumed default, not a derived figure)",
    )
    if free >= required:
        return passed(NAME, detail=detail)

    return failed(
        NAME,
        what_is_wrong=(
            f"the filesystem holding the staging root has {_gib(free)} free and this deployment "
            f"is projected to need {_gib(required)}. Staged Parquet is the layer every migration "
            "and every rebuild replays from, so running it out of space loses the recovery path, "
            "not just the next load."
        ),
        what_to_do=(
            "Free space on that filesystem, or point components.storage.staging at a larger one "
            "in osprey.yaml and re-render. If the projection itself is wrong for your data, it is "
            "an assumed 20GiB default rather than a figure derived from your sources — override it "
            "deliberately rather than working around it."
        ),
        detail=detail,
    )
