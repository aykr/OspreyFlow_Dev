"""The contract of `promotion_ageing.WaitingPromotions.waiting_for_review` (`06_DECISIONS.md` ADR-145
Amendment 4 decision 11, Amendment 6 decision 5; rule 1: the suite before the store).

Operations lists a promotion waiting for review only to the people decision 11 names: the dataset's
Authors holding `review_promotions`, and the administrators of the dataset's unit; in either case
only someone cleared to the dataset's highest marking and to the highest marking of the items the
promotion carries (`items_marking`, L2.7: an unmarked dataset's marked item, CARRIES row 46). Holding `operate_schedules`, which opens
Operations, lists none on its own. The store filters in its own read (rule 3), so this is the store's
test, not the route's.

**Case's L3.4 adds its store to `STORES`** (a factory taking the promotions and each dataset's
Authors, and setting them up in that store) and must pass every case here. Until then the suite runs
against `ReferenceWaiting`, the shape the contract describes, and is shown red with each check
dropped from it (`L2.6_RED_RECORD.md`, C1–C4; `L2.7_RED_RECORD.md`, C5–C6 for the items' marking).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest
from ontology.handling import HandlingScheme
from services.api.promotion_ageing import (
    PendingPromotion,
    WaitingPromotions,
    may_review,
)

from schemas.domain import Principal

SCHEME = HandlingScheme(name="contract", classification=["OFFICIAL", "SECRET", "TOP SECRET"],
                        handling_codes={}, action_codes={}, sanitisation_codes={})  # fmt: skip
SENT = datetime(2026, 11, 2, 9, 0, tzinfo=UTC)
PROMOTIONS = [
    PendingPromotion(items_marking="SECRET", promotion_id="p-secret", load_id="load-1", dataset_id="ds-s",
                     dataset_name="Synthetic custody", dataset_unit="unit-1",
                     proposed_by="ana-1", proposed_at=SENT, dataset_marking="SECRET"),
    PendingPromotion(items_marking="OFFICIAL", promotion_id="p-plain", load_id="load-2", dataset_id="ds-p",
                     dataset_name="Synthetic visits", dataset_unit="unit-1",
                     proposed_by="ana-1", proposed_at=SENT),
    # Its dataset has no highest marking, and its items are marked SECRET: the dataset's marking
    # does not bound them, so the items' own marking is asked (rule 3; case's round 2, item 3, and
    # CARRIES row 46, one case for both lanes'): the store must supply `items_marking`, the highest
    # current marking of the items it carries.
    PendingPromotion(promotion_id="p-item-high", load_id="load-3", dataset_id="ds-p",
                     dataset_name="Synthetic visits", dataset_unit="unit-1",
                     proposed_by="ana-1", proposed_at=SENT, items_marking="SECRET"),
]  # fmt: skip
AUTHORS: dict[str, list[str]] = {
    "ds-s": ["rev-1", "rev-low", "ana-2", "rev-9"],
    "ds-p": ["rev-1", "ana-2", "rev-9"],
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


def case_promotion_store(
    promotions: Sequence[PendingPromotion], authors: Mapping[str, Sequence[str]]
) -> WaitingPromotions:
    """L3.4's store (`promotion_store.WaitingFromStore` over `InMemoryPromotionStore`, whose
    `waiting` is the Postgres store's in shape; `test_promotion_store.py` holds the query). Each
    record keeps what was true at proposal: a unit since left and its items' own marking, below the
    dataset's. The datasets hold what is true now, which is what the contract asks."""
    from services.api.promotion_store import (
        InMemoryPromotionStore,
        PromotionRecord,
        WaitingFromStore,
    )

    store = InMemoryPromotionStore()
    datasets = {}
    for p in promotions:
        store.records[p.promotion_id] = PromotionRecord(
            id=p.promotion_id, load_id=p.load_id, trigger="analyst_promotion", case_id="c-1",
            board_id="b-1", dataset_id=p.dataset_id, layer_id="layer-c-1",
            proposed_by=p.proposed_by, proposed_at=p.proposed_at, status="awaiting_review",
            marking=p.items_marking or "OFFICIAL", unit="unit-at-proposal",
            item_ids=(f"{p.promotion_id}-item",),
        )  # fmt: skip
        datasets[p.dataset_id] = SimpleNamespace(
            name=p.dataset_name, owning_unit=p.dataset_unit, highest_marking=p.dataset_marking
        )

    class _Datasets:
        async def egress_of(self, ids: Sequence[str]) -> dict[str, Any]:
            return {d: datasets[d] for d in ids if d in datasets}

    async def authors_of(dataset_id: str) -> Sequence[str]:
        return authors.get(dataset_id, ())

    return WaitingFromStore(
        store=store, datasets=_Datasets(), pending=PendingPromotion, may_review=may_review,
        authors_of=authors_of, scheme=SCHEME,
    )  # fmt: skip


#: Every store that claims the seam. L3.4 adds its own here.
STORES: dict[str, Factory] = {"reference": ReferenceWaiting, "case": case_promotion_store}


def _p(pid: str, roles: list[str], *, unit: str = "unit-1", clearance: str = "SECRET") -> Principal:
    return Principal(id=pid, clearance=clearance, org_unit=unit, roles=roles)


#: Each reader, and the promotions they are listed (of `PROMOTIONS`, by id).
READERS: list[tuple[str, Principal, set[str]]] = [
    ("an Author holding review_promotions, cleared", _p("rev-1", ["data_engineer"]),
     {"p-secret", "p-plain", "p-item-high"}),
    ("an Author holding review_promotions, below the marking",
     _p("rev-low", ["data_engineer"], clearance="OFFICIAL"), set()),
    ("an Author without review_promotions", _p("ana-2", ["analyst"]), set()),
    # A grant outlives a move, but the case recognises it only in its own unit (`get_authorized`).
    ("an Author of another unit holding review_promotions",
     _p("rev-9", ["data_engineer"], unit="unit-9"), set()),
    ("review_promotions but no Author", _p("eng-9", ["data_engineer"]), set()),
    ("the dataset's unit's administrator, cleared", _p("adm-1", ["osprey-admin"]),
     {"p-secret", "p-plain", "p-item-high"}),
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


@pytest.mark.parametrize("store", sorted(STORES))
async def test_every_waiting_promotion_carries_its_items_marking(store: str) -> None:
    """L2.7 (CARRIES row 46): the sweep and *Needs you* read each promotion from `all_waiting()`,
    and `may_review` asks its `items_marking`; `None` clears everyone. So the store must hand back
    the items' marking it holds, for every promotion, here and not only in its own filtered read.
    Red with a store that leaves the field out of `all_waiting()` (it would alert and serve an
    uncleared reviewer)."""
    waiting = STORES[store](PROMOTIONS, AUTHORS)
    got = {p.promotion_id: p.items_marking for p in await waiting.all_waiting()}
    assert got == {p.promotion_id: p.items_marking for p in PROMOTIONS}
    assert got["p-item-high"] == "SECRET"


def test_the_items_marking_is_required() -> None:
    """A store cannot build a promotion and forget the items' marking: `PendingPromotion` takes no
    default for it, since `None` clears everyone. Red with a default given."""
    with pytest.raises(TypeError, match="items_marking"):
        PendingPromotion(promotion_id="p", load_id="l", dataset_id="d", dataset_name="n",  # type: ignore[call-arg]
                         dataset_unit="u", proposed_by="a", proposed_at=SENT)  # fmt: skip


async def test_the_case_stores_items_marking_follows_an_item_re_marked_while_it_waits() -> None:
    """L2.7 with L3.4: `items_marking` is the highest **current** marking of the items a promotion
    carries. An item re-marked SECRET while its promotion waits raises it (`raise_marking`, which
    an item's edit calls), so the sweep and *Needs you* read the new marking at once. Red with
    `_as_pending` passing the dataset's marking, or none."""
    plain = PROMOTIONS[1]  # p-plain: an unmarked dataset, its items OFFICIAL
    waiting = case_promotion_store([plain], {"ds-p": ["rev-1", "rev-low"]})
    low = _p("rev-low", ["data_engineer"], clearance="OFFICIAL")
    [before] = await waiting.all_waiting()
    assert before.items_marking == "OFFICIAL"
    assert [p.promotion_id for p in await waiting.waiting_for_review(low)] == ["p-plain"]
    await waiting.store.raise_marking(  # type: ignore[attr-defined]
        "c-1", "p-plain-item", "SECRET", SCHEME.classification
    )
    [after] = await waiting.all_waiting()
    assert after.items_marking == "SECRET"
    assert await waiting.waiting_for_review(low) == []  # the OFFICIAL Author no longer listed
    assert [p.promotion_id for p in await waiting.waiting_for_review(_p("rev-1", ["data_engineer"]))] == ["p-plain"]
