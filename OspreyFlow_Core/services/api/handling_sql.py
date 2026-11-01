"""The handling check as Postgres SQL, for a store that keeps handlings beside what it holds (a
report pack's items: `06_DECISIONS.md` ADR-134 decision 4, rule 3).

The same two axes `ontology.handling.principal_may_view` reads, and the analytics adapters' and the
graph adapter's access filters compile: the classification the reader is cleared for, and — for a
handling code whose scheme entry is `restricted` — a code the reader may receive, in their own unit
as its owner or originator. A classification or a code the scheme does not know is not viewable
(fail closed), as `packs.item_visible` has it; `test_pack_store_query.py` holds the two to the same
answers.
"""

from __future__ import annotations

from ontology.handling import HandlingScheme
from schemas.domain import Principal


def _cleared(principal: Principal, scheme: HandlingScheme) -> list[str]:
    order = list(scheme.classification)
    if principal.clearance not in order:
        return []
    return order[: order.index(principal.clearance) + 1]


def viewable_handlings_sql(
    array: str, principal: Principal, scheme: HandlingScheme, position: int
) -> tuple[str, list[object]]:
    """SQL true when the reader may view every handling in the JSONB array `array` (an empty or
    absent array rests on nothing, so it is viewable), with its parameters from `$position`. The
    check is "no handling the reader may not view", and `COALESCE(..., false)` keeps a `NULL` (a
    handling missing a field) from reading as viewable."""
    restricted = [c for c, d in scheme.handling_codes.items() if d.dissemination == "restricted"]
    open_codes = [c for c in scheme.handling_codes if c not in restricted]
    receivable = [c for c in principal.receivable_handling_codes if c in restricted]
    cleared, codes, received, unit = (f"${position + i}" for i in range(4))
    sql = (
        f"NOT EXISTS (SELECT 1 FROM jsonb_array_elements(COALESCE({array}, '[]'::jsonb)) AS h "
        f"WHERE NOT COALESCE((h->>'classification' = ANY({cleared}::text[]) AND "
        f"(h->>'handling_code' = ANY({codes}::text[]) OR (h->>'handling_code' = "
        f"ANY({received}::text[]) AND (h->>'owning_unit' = {unit} OR h->>'originator' = {unit})))"
        "), false))"
    )
    return sql, [_cleared(principal, scheme), open_codes, receivable, principal.org_unit]


__all__ = ["viewable_handlings_sql"]
