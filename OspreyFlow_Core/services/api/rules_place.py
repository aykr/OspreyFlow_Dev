"""Rules and Monitoring's gate (`06_DECISIONS.md` ADR-146 decision 2; ADR-145 Amendment 4).

The place is opened by `triage_alerts` or `author_rules` (ADR-112 Amendment 5 decision 1) and by
nothing else. Hiding it from the switcher is never the control (rule 3): every route of the place
asks for the gate as well as the right its own action takes, so a person holding one of those
action rights (the Data Engineer's `deploy_rules`, the Administrator's `read_rule_audit`) but
neither opening right is refused there too. The routes of the place without it are those used
outside it too (`tests/services/api/test_place_routes.py`, `SHARED`): the queue's list (Home, the
switcher's count, a report pack's alert items) and the held rows' list, rejection and release (Home,
and the Studio's Runs, ADR-140).
"""

from __future__ import annotations

from collections.abc import Iterable

from schemas.rights import Right, rights_for

PLACE = "rules"

#: The rights that open Rules and Monitoring (ADR-146 decision 2), any one of them.
OPENING_RIGHTS: frozenset[Right] = frozenset({Right.TRIAGE_ALERTS, Right.AUTHOR_RULES})


def opens_rules_place(roles: Iterable[str]) -> bool:
    """Whether a principal with these token roles holds a right that opens the place."""
    return bool(rights_for(roles) & OPENING_RIGHTS)


def refusal() -> dict[str, object]:
    """The 403's body: the place, and the rights any one of which would open it."""
    return {
        "error": "place_required",
        "place": PLACE,
        "rights": sorted(r.value for r in OPENING_RIGHTS),
    }
