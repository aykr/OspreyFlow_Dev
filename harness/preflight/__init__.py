"""Preflight, headless — `06_DECISIONS.md` ADR-049's Stage 2 §2, accepted 24 September 2026.

`05_DEPLOYMENT.md` §2.1: "Preflight runs live. Each check appears as it completes… A failure
explains what is wrong and what to do about it, with a **Re-check** button rather than a loop of
edit-and-rerun. Preflight must pass before Launch is enabled." §2.3 requires the headless
equivalent of every screen, and this is Preflight's: `python -m harness.preflight`, with `--only`
as Re-check for a single check and `--gate` as the thing Launch consults.

**The engine is headless first and the screen is a view over it** (ADR-049's own principle). Stage
2 §6's Preflight screen calls into this module; it does not reimplement any of these checks.

## What is deliberately NOT here

**ADR-043's two-sided token-exchange check does not belong in Preflight, and must not be added.**
The owner ruled on 24 September 2026 that it runs at the post-launch `verify` step, as the final
step of Stage 2 §3's golden-path deploy, with Stage 2 §7 keeping the Re-check surface. Two reasons,
both binding: performing a real RFC 8693 exchange means *using* the Conduit's confidential-client
secret rather than referencing it, which §2.5 forbids the harness outright ("It never sees a
secret… The harness records where to look, never what it found"); and pre-Launch there is no
Keycloak running to exchange against, since it is one of the twelve containers Launch itself brings
up. A future reader finding no token-exchange check here is looking at a decision, not an omission.

## The checks

Environment checks, from §2.1's own list: `memory`, `disk`, `gpu`, `ports`, `container-runtime`,
`cluster-connectivity`. Then the four the 23 September 2026 demo rehearsal produced, each of which
cost real time before it was understood: `interpreter`, `bind-address`, `basemap`, `duckdb-lock`.

Each is its own module, each returns the same `CheckResult`, and each is independently runnable —
which is what makes Re-check a real operation rather than a full re-run with the output filtered.
"""

from __future__ import annotations

from harness.preflight import (
    basemap,
    bind_address,
    cluster,
    disk,
    duckdb_lock,
    gpu,
    interpreter,
    memory,
    ports,
    runtime,
)
from harness.preflight.context import PreflightContext, RenderedOutputMissing
from harness.preflight.result import CheckResult, Status, failed, passed, skipped

#: In the order §2.1 lists them, then the four rehearsal-derived ones. Order is the running order
#: and the reporting order both: the cheap environment facts first, so an operator on a machine
#: with too little memory is told that before a thirty-second cluster probe.
ALL_CHECKS = (
    memory,
    disk,
    gpu,
    ports,
    runtime,
    cluster,
    interpreter,
    bind_address,
    basemap,
    duckdb_lock,
)

CHECKS_BY_NAME = {module.NAME: module for module in ALL_CHECKS}

__all__ = [
    "ALL_CHECKS",
    "CHECKS_BY_NAME",
    "CheckResult",
    "PreflightContext",
    "RenderedOutputMissing",
    "Status",
    "failed",
    "passed",
    "skipped",
]
