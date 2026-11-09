"""The contract of `promotion_ageing.WaitingPromotions.waiting_for_review` (`06_DECISIONS.md` ADR-145
Amendment 4 decision 11, Amendment 6 decision 5; rule 1: the suite before the store).

Operations lists a promotion waiting for review only to the people decision 11 names: the dataset's
Authors holding `review_promotions`, and the administrators of the dataset's unit; in either case
only someone cleared to the dataset's highest marking. Holding `operate_schedules`, which opens
Operations, lists none on its own. The store filters in its own read (rule 3), so this is the store's
test, not the route's.

**Case's L3.4 adds its store to `STORES`** (a factory taking the promotions and each dataset's
Authors, and setting them up in that store) and must pass every case here. Until then the suite runs
against `ReferenceWaiting`, the shape the contract describes, and is shown red with each check
dropped from it (`L2.6_RED_RECORD.md`, C1–C3).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

import pytest
from ontology.handling import HandlingScheme
from services.api.promotion_ageing import PendingPromotion, WaitingPromotions, may_review

from schemas.domain import Principal

SCHEME = HandlingScheme(name="contract", classification=["OFFICIAL", "SECRET", "TOP SECRET"],
                        handling_codes={}, action_codes={}, sanitisation_codes={})  # fmt: skip
SENT = datetime(2026, 11, 2, 9, 0, tzinfo=UTC)
PROMOTIONS = [
    PendingPromotion(promotion_id="p-secret", load_id="load-1", dataset_id="ds-s",
                     dataset_name="Synthetic custody", dataset_unit="unit-1",
                     proposed_by="ana-1", proposed_at=SENT, dataset_marking="SECRET"),
    PendingPromotion(promotion_id="p-plain", load_id="load-2", dataset_id="ds-p",
                     dataset_name="Synthetic visits", dataset_unit="unit-1",
                     proposed_by="ana-1", proposed_at=SENT),
]  # fmt: skip
AUTHORS: dict[str, list[str]] = {
    "ds-s": ["rev-1", "rev-low", "ana-2"],
    "ds-p": ["rev-1", "ana-2"],
}


@dataclass
class ReferenceWaiting:
    """The contract's shape over a list: a promotion is listed to a reader who `may_review` it."""

    promotions: Sequence[PendingPromotion]
    authors: Mapping[str, Sequence[str]]
    recorded: bool = True

    async def waiting_for_review(self, reader: Principal) -> list[PendingPromotion]:
        return [
            p for p in self.promotions
            if may_review(reader.id, reader.roles, reader.clearance, reader.org_unit, p,
                          self.authors.get(p.dataset_id, ()), None, SCHEME)
        ]  # fmt: skip

    async def all_waiting(self) -> list[PendingPromotion]:
        return list(self.promotions)


Factory = Callable[[Sequence[PendingPromotion], Mapping[str, Sequence[str]]], WaitingPromotions]
#: Every store that claims the seam. L3.4 adds its own here.
STORES: dict[str, Factory] = {"reference": ReferenceWaiting}


def _p(pid: str, roles: list[str], *, unit: str = "unit-1", clearance: str = "SECRET") -> Principal:
    return Principal(id=pid, clearance=clearance, org_unit=unit, roles=roles)


#: Each reader, and the promotions they are listed (of `PROMOTIONS`, by id).
READERS: list[tuple[str, Principal, set[str]]] = [
    ("an Author holding review_promotions, cleared", _p("rev-1", ["data_engineer"]),
     {"p-secret", "p-plain"}),
    ("an Author holding review_promotions, below the marking",
     _p("rev-low", ["data_engineer"], clearance="OFFICIAL"), set()),
    ("an Author without review_promotions", _p("ana-2", ["analyst"]), set()),
    ("review_promotions but no Author", _p("eng-9", ["data_engineer"]), set()),
    ("the dataset's unit's administrator, cleared", _p("adm-1", ["osprey-admin"]),
     {"p-secret", "p-plain"}),
    ("the dataset's unit's administrator, below the marking",
     _p("adm-low", ["osprey-admin"], clearance="OFFICIAL"), {"p-plain"}),
    ("another unit's administrator", _p("adm-9", ["osprey-admin"], unit="unit-9"), set()),
    ("operate_schedules alone, which opens Operations", _p("ops-1", ["right:operate_schedules"]),
     set()),
]  # fmt: skip


@pytest.mark.parametrize("store", sorted(STORES))
@pytest.mark.parametrize(("who", "reader", "listed"), READERS, ids=[r[0] for r in READERS])
async def test_a_waiting_promotion_is_listed_only_to_those_who_may_review_it(
    store: str, who: str, reader: Principal, listed: set[str]
) -> None:
    waiting = STORES[store](PROMOTIONS, AUTHORS)
    assert waiting.recorded is True
    got = {p.promotion_id for p in await waiting.waiting_for_review(reader)}
    assert got == listed, who
