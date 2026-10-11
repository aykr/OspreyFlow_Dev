"""The report pack store (`06_DECISIONS.md` ADR-113 decisions 3 to 5), against real Postgres: a pack
belongs to its case; a published version is a copy, never a view of the draft; a refresh keeps the
snapshot it replaced; a withdrawal is recorded once."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
from conduit_common.identity import new_id
from schemas.domain import Handling, Principal
from services.api.config import PostgresConfig
from services.api.packs import PackStore, StoredPackItem

BY = Principal(id="analyst-1", clearance="OFFICIAL", org_unit="unit-1")
HANDLING = Handling(classification="OFFICIAL", handling_code="P", owning_unit="unit-1", originator="unit-1")


def _note(text: str) -> StoredPackItem:
    return StoredPackItem(id=new_id(), kind="note", marking="OFFICIAL", added_by=BY.id,
                          added_at=datetime.now(UTC), note=text, handlings=[HANDLING])  # fmt: skip


@pytest.fixture
async def store() -> AsyncIterator[PackStore]:
    found = await PackStore.connect(PostgresConfig.from_env().dsn)
    yield found
    await found.close()


async def test_a_pack_stays_in_its_own_case(store: PackStore) -> None:
    case, other = f"case-{new_id()}", f"case-{new_id()}"
    pack = await store.create(case, "Review", BY)
    assert [p.id for p in await store.list_for_case(case)] == [pack.id]
    assert await store.list_for_case(other) == []
    assert await store.get(other, pack.id) is None
    assert (await store.get(case, pack.id)) is not None


async def test_a_version_is_a_copy_of_the_draft_not_a_view_of_it(store: PackStore) -> None:
    case = f"case-{new_id()}"
    pack = await store.create(case, "Review", BY)
    first, second = await store.add_item(pack.id, _note("one")), await store.add_item(pack.id, _note("two"))
    version = await store.publish(pack.id, BY)
    await store.set_order(pack.id, [second.id, first.id])
    assert await store.remove_item(pack.id, first.id)
    await store.add_item(pack.id, _note("three"))
    kept = await store.version(pack.id, version.version)
    assert kept is not None and [i.note for i in kept.items] == ["one", "two"]
    assert [i.note for i in await store.items(pack.id)] == ["two", "three"]
    assert (await store.publish(pack.id, BY)).version == 2


async def test_a_refresh_keeps_the_snapshot_it_replaced(store: PackStore) -> None:
    pack = await store.create(f"case-{new_id()}", "Review", BY)
    old = await store.add_item(pack.id, _note("before"))
    after = await store.add_item(pack.id, _note("after"))
    new = _note("refreshed")
    assert await store.replace_item(pack.id, old.id, new)
    assert [i.note for i in await store.items(pack.id)] == ["refreshed", "after"], "in the old one's place"
    (earlier,) = await store.earlier_snapshots(pack.id)
    assert (earlier.id, earlier.replaced_by) == (old.id, new.id) and earlier.replaced_at is not None
    assert not await store.replace_item(pack.id, old.id, _note("twice")), "a replaced snapshot is history"
    assert not await store.remove_item(pack.id, old.id)
    assert after.id in [i.id for i in await store.items(pack.id)]


async def test_a_withdrawal_is_recorded_once(store: PackStore) -> None:
    pack = await store.create(f"case-{new_id()}", "Review", BY)
    await store.add_item(pack.id, _note("one"))
    await store.publish(pack.id, BY)
    assert await store.withdraw(pack.id, 1, BY, "wrong figures")
    assert not await store.withdraw(pack.id, 1, BY, "again")
    (summary,) = await store.versions(pack.id)
    assert (summary.withdrawn_by, summary.withdrawal_reason) == ("analyst-1", "wrong figures")
    assert await store.latest_published(pack.id) is None
