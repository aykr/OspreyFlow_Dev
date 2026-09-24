"""Available memory against the profile floor — `05_DEPLOYMENT.md` §2.1's first Preflight check.

**The floor is arithmetic, not a specification, and this module says so out loud.**
`07_BUILD_PLAN.md`'s Stage 2a entry derives 10GiB for the Docker Desktop VM on a 16GiB host from its
own measurements and then states plainly: "neither number is a specification quoted from anywhere —
both are arithmetic from this pass's own measurements". `05_DEPLOYMENT.md` §1 and §3 are the
specification, and both say 16 GB for `local-lite`. This check uses §3's 16 GB as the floor it
enforces and quotes Stage 2a's VM figure as advice in the remedy, rather than silently promoting a
measurement to a requirement.
"""

from __future__ import annotations

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
    except (AttributeError, ValueError, OSError) as error:
        return skipped(
            NAME,
            reason=(
                f"physical memory could not be read on this platform ({error}), so the profile "
                "floor was not checked at all"
            ),
        )

    floor = PROFILE_FLOORS[context.config.profile.value]
    detail = (f"total system memory: {_gib(total)}", f"profile floor: {_gib(floor)}")
    if total >= floor:
        return passed(NAME, detail=detail)

    return failed(
        NAME,
        what_is_wrong=(
            f"this machine has {_gib(total)} of memory and the {context.config.profile.value} "
            f"profile's floor is {_gib(floor)}. The full stack is twelve containers at roughly "
            "11GiB at rest, so it will not fit."
        ),
        what_to_do=(
            "Either run the reduced variant, which drops OpenSearch and falls back to PostgreSQL "
            "full-text — Preflight offers it below, and it is never applied for you — or add "
            "memory. If you are on Docker Desktop, note separately that the VM's own allocation "
            "needs roughly 10GiB of whatever this machine has; that figure is measured, not "
            "specified."
        ),
        detail=detail,
    )
