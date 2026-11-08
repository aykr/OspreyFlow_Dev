"""Rules and Monitoring's gate (`06_DECISIONS.md` ADR-146 decision 2; ADR-145 Amendment 4).

The place is opened by `triage_alerts` or `author_rules` (ADR-112 Amendment 5 decision 1), with
the queue's read its entry needs (`read_alert_queue`), and by nothing else. Hiding it from the
switcher is never the control (rule 3): every route of the place asks for the gate as well as the
right its own action takes, so a person holding one of those action rights (the Data Engineer's
`deploy_rules`, the Administrator's `read_rule_audit`) but not the place is refused there too. The
routes of the place without it are those used outside it too (`tests/services/api/
test_place_routes.py`, `SHARED_READS`): the queue's list (Home, the switcher's count), whose rows go
only to whom the place is offered and to the Reports Viewer, and its counts, for any other reader of
the queue (ADR-146 Amendment 2 point 3); and the held rows' list, rejection and release (Home, and
the Studio's Runs, ADR-140).
"""

from __future__ import annotations

import asyncio
import math
import time
from collections.abc import Iterable

from schemas.rights import Right, rights_for

PLACE = "rules"

#: The rights that open Rules and Monitoring (ADR-146 decision 2), any one of them.
OPENING_RIGHTS: frozenset[Right] = frozenset({Right.TRIAGE_ALERTS, Right.AUTHOR_RULES})
#: What the place's entry read needs as well (`places.json`'s `needs`, ADR-145 Amendment 1): the
#: gate asks for it too, so the routes refuse exactly whom the place is not offered to (ADR-146
#: Amendment 2 point 1), never more widely than the switcher hides it.
NEEDS: frozenset[Right] = frozenset({Right.READ_ALERT_QUEUE})


def opens_rules_place(roles: Iterable[str]) -> bool:
    """Whether a principal with these token roles is offered the place: an opening right and
    every right it needs."""
    held = rights_for(roles)
    return bool(held & OPENING_RIGHTS) and NEEDS <= held


#: The role ADR-145 Amendment 4 decision 10 gives the queue's rows without the place: the Reports
#: Viewer's Home lists the alerts on the cases they can read (never their detail, which is the
#: place's). By the role, not a right: a custom role copied from it is given counts, the narrower.
ROWS_WITHOUT_THE_PLACE = frozenset({"reports_viewer"})


def reads_queue_rows(roles: Iterable[str]) -> bool:
    """Whether the queue's shared read gives this reader its rows (ADR-146 Amendment 2 point 3):
    whoever the place is offered to, and the Reports Viewer. Anyone else holding the queue's read
    reads its counts alone (`…/alert-queue/counts`)."""
    roles = list(roles)
    return opens_rules_place(roles) or bool(ROWS_WITHOUT_THE_PLACE & set(roles))


def rows_refusal() -> dict[str, object]:
    """The rows' 403: the place is not offered, and the counts are where the reader looks."""
    return {"error": "queue_rows_not_offered", "place": PLACE, "counts": "alert-queue/counts"}


def refusal() -> dict[str, object]:
    """The 403's body: the place, the rights any one of which opens it, and what it needs too."""
    return {
        "error": "place_required",
        "place": PLACE,
        "rights": sorted(r.value for r in OPENING_RIGHTS),
        "needs": sorted(r.value for r in NEEDS),
    }


#: An alert's address answers every refusal at the end of the quantum it falls in, counted from the
#: request's start (ADR-146 Amendment 2 point 6; the orchestrator's independent review of L2.9,
#: blocker 1): an id that never existed, an alert in a case the reader may not open, and one whose
#: evidence is hidden from them are told apart by neither status, body nor when the answer comes,
#: while the hidden alert's reads fit in one quantum (measured under the rules lease,
#: `process/lanes/rules/l2.9/address-timing.txt`). Successes are not held: they say the alert is
#: there anyway.
ADDRESS_REFUSAL_QUANTUM = 0.25
#: The clock and the wait the address reads, here so a test can stand a clock in for them.
monotonic = time.monotonic
sleep = asyncio.sleep


def refusal_wait(started: float, now: float, quantum: float | None = None) -> float:
    """How long a refusal waits so it is answered at the end of the quantum it falls in: at one
    quantum from the start, or the next whole one past it."""
    quantum = ADDRESS_REFUSAL_QUANTUM if quantum is None else quantum
    elapsed = max(0.0, now - started)
    return max(1, math.ceil(elapsed / quantum)) * quantum - elapsed
