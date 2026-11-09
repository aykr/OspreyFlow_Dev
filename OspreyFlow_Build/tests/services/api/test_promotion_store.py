"""`PostgresPromotionStore` on real Postgres (ADR-143 decisions 8 and 10; Amendment 2 decision 1;
ADR-145 Amendment 6's seam; L3.4).

Every case runs over a schema of its own, dropped afterwards whatever the test did, so no
promotion or grant is ever left in a shared stack's tables (the stacks are shared: a row a branch's
schema allows and main's does not stops other lanes' runs).

- The seam's reader filter is in the query (rule 3): `waiting(dataset_ids=…)` returns only the
  promotions of the datasets the reader may review, red with the filter not passed (the same call
  unfiltered returns the others, so the data can tell); who may review is the contract's
  (`test_waiting_promotions_contract.py`).
- A decision is written only from the status it was read with: of two at once, one wins.
- A grant closes once and is never reopened.
- What is written reads back whole (the element ids, the left-out list with its words).
- A board's list is filtered by clearance in the query, as the Studio's is.
- An open promotion's marking rises with an item edited above it, never falls, and a decided one
  is left as it was decided.
- What still waits from a layer is found by the layer (its delete rejects it).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import asyncpg
import pytest
from conduit_common.identity import new_id
from services.api.config import PostgresConfig
from services.api.promotion_store import LayerGrant, PostgresPromotionStore, PromotionRecord

NOW = datetime(2026, 11, 9, 9, 0, tzinfo=UTC)


@pytest.fixture
async def store() -> AsyncIterator[PostgresPromotionStore]:
    base = PostgresConfig.from_env().dsn
    schema = f"promotions_{new_id().lower()}"
    admin = await asyncpg.connect(base)
    await admin.execute(f'CREATE SCHEMA "{schema}"')
    held = None
    try:
        held = await PostgresPromotionStore.connect(
            f"{base}{'&' if '?' in base else '?'}search_path={schema}"
        )
        yield held
    finally:
        if held is not None:
            await held.close()
        await admin.execute(f'DROP SCHEMA "{schema}" CASCADE')
        await admin.close()


def _record(**over: object) -> PromotionRecord:
    base = dict(
        id=new_id(), load_id=f"promotion-{new_id()}", trigger="analyst_promotion",
        case_id="case-k", board_id="board-1", dataset_id="src", layer_id="layer-k",
        proposed_by="alice", proposed_at=NOW, status="awaiting_review", marking="OFFICIAL",
        unit="unit-1", node_ids=("n1", "n2"), edge_ids=("e1",), item_ids=("i1", "i2", "i3"),
        left_out=(("i4", "Spare", "Not ticked."),),
    )  # fmt: skip
    base.update(over)
    return PromotionRecord(**base)  # type: ignore[arg-type]


async def test_a_promotion_reads_back_whole(store: PostgresPromotionStore) -> None:
    record = _record()
    await store.add(record)
    assert await store.get(record.id) == record
    assert await store.by_load(record.load_id) == record
    assert await store.of_board("case-k", "board-1") == [record]
    assert await store.of_board("case-b", "board-1") == []
    assert await store.into("src") == [record] and await store.into("other") == []


async def _three(store: PostgresPromotionStore) -> tuple[str, str, str]:
    mine = _record(proposed_at=NOW)
    other = _record(dataset_id="other", proposed_at=NOW + timedelta(minutes=1))
    decided = _record(status="committed", proposed_at=NOW + timedelta(minutes=2))
    for r in (mine, other, decided):
        await store.add(r)
    return mine.id, other.id, decided.id


async def test_the_waiting_read_is_filtered_by_the_readers_datasets_in_the_query(
    store: PostgresPromotionStore,
) -> None:
    """The seam passes the datasets the reader may review (`WaitingFromStore.reviewable_datasets`,
    admin's `may_review` asked of each dataset as it is now) into the WHERE clause (rule 3)."""
    mine, _, _ = await _three(store)
    assert await store.waiting_dataset_ids() == ["other", "src"]
    assert [r.id for r in await store.waiting(dataset_ids=["src"])] == [mine]
    assert await store.waiting(dataset_ids=[]) == []


async def test_the_filter_check_fails_with_the_filter_not_passed(
    store: PostgresPromotionStore,
) -> None:
    mine, other, _ = await _three(store)
    # The plant: the seam's read made without the reader's filter.
    assert [r.id for r in await store.waiting()] == [mine, other]


async def test_a_decision_is_written_only_from_the_status_it_was_read_with(
    store: PostgresPromotionStore,
) -> None:
    record = _record()
    await store.add(record)
    first = await store.decide(record.id, was="awaiting_review", now="committed", by="dana",
                               at=NOW)  # fmt: skip
    second = await store.decide(record.id, was="awaiting_review", now="rejected", by="sam",
                                at=NOW, reason="late")  # fmt: skip
    assert (first, second) == (True, False)
    held = await store.get(record.id)
    assert held is not None and (held.status, held.reviewed_by, held.reason) == (
        "committed", "dana", None
    )
    assert await store.waiting() == []
    assert await store.decide(record.id, was="committed", now="reverted", by=None, at=NOW)
    reverted = await store.get(record.id)
    assert reverted is not None and reverted.status == "reverted"
    assert reverted.reviewed_by == "dana"  # a revert keeps who reviewed it


async def test_a_grant_closes_once_and_is_never_reopened(store: PostgresPromotionStore) -> None:
    grant = LayerGrant(id=new_id(), layer_id="layer-k", case_id="case-k", dataset_id="src",
                       holder="dana", opened_at=NOW)  # fmt: skip
    await store.open_grant(grant)
    assert await store.grant(grant.id) == grant
    await store.close_grant(grant.id, NOW + timedelta(minutes=5))
    await store.close_grant(grant.id, NOW + timedelta(minutes=9))
    held = await store.grant(grant.id)
    assert held is not None and held.closed_at == NOW + timedelta(minutes=5)
    assert await store.grant("no-such") is None


async def test_the_studio_list_is_filtered_by_clearance_in_the_query(
    store: PostgresPromotionStore,
) -> None:
    mine, other_unit, above = await _three(store)
    seen = await store.into("src", markings=["OFFICIAL", "OFFICIAL-SENSITIVE"])
    assert {r.id for r in seen} == {mine, other_unit}
    assert {r.id for r in await store.into("src")} == {mine, other_unit, above}  # the plant


async def test_an_open_promotions_items_are_held_and_released_when_it_is_decided(
    store: PostgresPromotionStore,
) -> None:
    record = _record()
    await store.add(record)
    await store.add(_record(case_id="case-b", item_ids=("b1",)))
    assert await store.pending_item_ids("case-k") == {"i1", "i2", "i3"}
    await store.decide(record.id, was="awaiting_review", now="rejected", by="dana", at=NOW,
                       reason="no")  # fmt: skip
    assert await store.pending_item_ids("case-k") == set()


async def test_a_deleted_layer_is_recorded_and_its_grants_closed(
    store: PostgresPromotionStore,
) -> None:
    grant = LayerGrant(id=new_id(), layer_id="layer-k", case_id="case-k", dataset_id="src",
                       holder="dana", opened_at=NOW)  # fmt: skip
    other = LayerGrant(id=new_id(), layer_id="layer-b", case_id="case-b", dataset_id="src",
                       holder="dana", opened_at=NOW)  # fmt: skip
    await store.open_grant(grant)
    await store.open_grant(other)
    assert not await store.layer_deleted("layer-k")
    await store.close_grants_for_layer("layer-k", NOW)
    await store.mark_layer_deleted("layer-k", NOW)
    await store.mark_layer_deleted("layer-k", NOW + timedelta(hours=1))  # once
    assert await store.layer_deleted("layer-k") and not await store.layer_deleted("layer-b")
    closed, kept = await store.grant(grant.id), await store.grant(other.id)
    assert closed is not None and closed.closed_at == NOW
    assert kept is not None and kept.closed_at is None


async def test_a_boards_list_is_filtered_by_clearance_in_the_query(
    store: PostgresPromotionStore,
) -> None:
    mine, other_unit, above = await _three(store)
    seen = await store.of_board("case-k", "board-1", markings=["OFFICIAL", "OFFICIAL-SENSITIVE"])
    assert {r.id for r in seen} == {mine, other_unit}
    # The plant: the same read without the reader's markings returns the one above them.
    assert above in {r.id for r in await store.of_board("case-k", "board-1")}


RANKED = ["OFFICIAL", "OFFICIAL-SENSITIVE", "SECRET", "TOP SECRET"]


async def test_an_open_promotions_marking_rises_with_its_item_and_never_falls(
    store: PostgresPromotionStore,
) -> None:
    waiting = _record()
    decided = _record(item_ids=("i9",), status="committed")
    other_case = _record(case_id="case-b")
    for r in (waiting, decided, other_case):
        await store.add(r)
    await store.raise_marking("case-k", "i2", "OFFICIAL-SENSITIVE", RANKED)
    held = await store.get(waiting.id)
    assert held is not None and held.marking == "OFFICIAL-SENSITIVE"
    # Never lowered by a later, lower edit.
    await store.raise_marking("case-k", "i2", "OFFICIAL", RANKED)
    held = await store.get(waiting.id)
    assert held is not None and held.marking == "OFFICIAL-SENSITIVE"
    # Another case's promotion holding the same item id, and a decided one, are untouched.
    await store.raise_marking("case-k", "i9", "SECRET", RANKED)
    for untouched in (decided, other_case):
        again = await store.get(untouched.id)
        assert again is not None and again.marking == "OFFICIAL"
    # A marking the scheme does not hold changes nothing.
    await store.raise_marking("case-k", "i2", "NOT A MARKING", RANKED)
    held = await store.get(waiting.id)
    assert held is not None and held.marking == "OFFICIAL-SENSITIVE"


async def test_what_waits_from_a_layer_is_found_by_the_layer(store: PostgresPromotionStore) -> None:
    waiting = _record()
    decided = _record(status="rejected")
    elsewhere = _record(layer_id="layer-b")
    for r in (waiting, decided, elsewhere):
        await store.add(r)
    assert [r.id for r in await store.waiting_from_layer("layer-k")] == [waiting.id]
