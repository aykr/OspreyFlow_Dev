"""Available memory against the profile floor — `05_DEPLOYMENT.md` §2.1's first Preflight check.

**The floor is arithmetic, not a specification, and this module says so out loud.**
`07_BUILD_PLAN.md`'s Stage 2a entry derives 10GiB for the Docker Desktop VM on a 16GiB host from its
own measurements and then states plainly: "neither number is a specification quoted from anywhere —
both are arithmetic from this pass's own measurements". `05_DEPLOYMENT.md` §1 and §3 are the
specification, and both say 16 GB for `local-lite`. This check uses §3's 16 GB as the floor it
enforces and quotes Stage 2a's VM figure as advice in the remedy, rather than silently promoting a
measurement to a requirement.

**Verdicts on the container runtime's own daemon, not this process's own host — round 10.** Before
this round, `context.memory_probe()` read `os.sysconf` — whatever process ran Preflight. Run
directly on a Docker-Desktop host (the shape `harness.apply`/the six-screen live exit test both
use), that is the host's own physical RAM, not the smaller, separate allocation the Docker Desktop
VM actually runs every container inside. Measured directly, this sandbox: 36GiB host, 9.7GiB
daemon — this check *passed* on a machine whose daemon cannot hold the twelve-container deployment
it exists to gate, the exact false pass `05_DEPLOYMENT.md` §2.1 forbids ("a check that cannot run
reports that it did not run — it never reports success"). `context.memory_probe()` now shells out
to the daemon itself (`docker info --format '{{.MemTotal}}'`, `context.py`'s own docstring has the
full account); the host's own figure (`context.host_memory_probe()`) is still read and still
reported, in `detail`, as context only — real information, never the verdict.
"""

from __future__ import annotations

import subprocess

from harness.preflight.context import PreflightContext
from harness.preflight.result import CheckResult, failed, passed, skipped

NAME = "memory"

#: `05_DEPLOYMENT.md` §1 ("One laptop, 16 GB") and §3 ("If Preflight finds less than 16 GB").
LOCAL_LITE_FLOOR_BYTES = 16 * 1024**3
PROFILE_FLOORS = {
    "local-lite": LOCAL_LITE_FLOOR_BYTES,
    "small": 16 * 1024**3,
    "cluster": 16 * 1024**3,
}


def _gib(value: int) -> str:
    return f"{value / 1024**3:.1f}GiB"


def check(context: PreflightContext) -> CheckResult:
    try:
        total = context.memory_probe()
    except (
        AttributeError,
        ValueError,
        OSError,
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
    ) as error:
        return skipped(
            NAME,
            reason=(
                f"the container runtime's own memory could not be read ({error}), so the "
                "profile floor was not checked at all — never a pass on a runtime that could "
                "not be reached"
            ),
        )

    host_total: int | None
    try:
        host_total = context.host_memory_probe()
        host_note = f"this host's own physical memory: {_gib(host_total)}"
    except (AttributeError, ValueError, OSError) as error:
        host_total = None
        host_note = f"host memory could not be read ({error})"

    floor = PROFILE_FLOORS[context.config.profile.value]
    detail = (
        f"container runtime memory: {_gib(total)}",
        f"profile floor: {_gib(floor)}",
        host_note,
    )
    if total >= floor:
        return passed(NAME, detail=detail)

    return failed(
        NAME,
        what_is_wrong=(
            f"the container runtime has {_gib(total)} of memory configured and the "
            f"{context.config.profile.value} profile's floor is {_gib(floor)}. The full stack is "
            "twelve containers at roughly 11GiB at rest, so it will not fit."
        ),
        what_to_do=(
            "Either run the reduced variant, which drops OpenSearch and falls back to PostgreSQL "
            "full-text — Preflight offers it below, and it is never applied for you — or raise "
            "the container runtime's own memory allocation. If you are on Docker Desktop, that "
            "is Settings → Resources → Memory, not more host RAM by itself"
            + (f" ({_gib(host_total)} of it, measured just now)" if host_total is not None else "")
            + "."
        ),
        detail=detail,
    )
