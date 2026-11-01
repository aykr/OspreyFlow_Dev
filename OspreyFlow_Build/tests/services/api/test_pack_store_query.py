"""Rule 3 for report packs (`spec/06_DECISIONS.md` ADR-134 decision 4): which items a reader gets is
decided in the pack store's query, as the reader — never by reading every item into the Conduit and
dropping the ones they may not view. The Python rule (`packs.item_visible`) stays as a second line,
and the two must agree, or one of them is wrong.

What a mistake would do, and the case that catches it:
- the SQL and the Python rule disagreeing on some handling — a restricted code outside its unit, a
  classification or a code the scheme does not know, an item resting on two handlings of which one
  is hidden — `test_the_query_and_the_python_rule_agree_on_every_handling`;
- a hidden item's body, or its id, handed to the Conduit at all —
  `test_the_store_returns_no_hidden_item_only_a_yes_or_no`;
- the same in a published version and in the history — `test_a_version_and_the_history_are_filtered_in_the_query_too`;
- a reorder that names, moves or loses a hidden item — `test_a_reorder_keeps_hidden_items_in_their_places_inside_the_store`.
"""

from __future__ import annotations

import itertools
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
from services.api.config import PostgresConfig
from services.api.packs import PackStore, StoredPackItem, item_visible

from conduit_common.identity import new_id
from ontology.handling import load_uk_le_scheme
from schemas.domain import Handling, Principal

SCHEME = load_uk_le_scheme()
NOW = datetime(2026, 11, 1, tzinfo=UTC)
AUTHOR = Principal(id="author", clearance="SECRET", org_unit="unit-1", receivable_handling_codes=["R"])


@pytest.fixture
async def store() -> AsyncIterator[PackStore]:
    found = await PackStore.connect(PostgresConfig.from_env().dsn)
    yield found
    await found.close()


def _item(*handlings: Handling, note: str = "n") -> StoredPackItem:
    return StoredPackItem(id=new_id(), kind="note", marking="OFFICIAL", added_by="author", added_at=NOW,
                          note=note, handlings=list(handlings))  # fmt: skip


def _h(classification: str = "OFFICIAL", code: str = "P", unit: str = "unit-1", originator: str = "unit-1") -> Handling:
    return Handling(classification=classification, handling_code=code, owning_unit=unit, originator=originator)


#: Handlings in the shapes items carry: each axis on its own, a restricted code inside and outside
#: the reader's unit (by owner and by originator), and a classification and a code this scheme does
#: not know (an item kept from before the scheme changed: fail closed).
HANDLINGS = [
    _h(), _h("SECRET"), _h("TOP SECRET"), _h(code="R"), _h(code="R", unit="unit-2", originator="unit-2"),
    _h(code="R", unit="unit-2", originator="unit-1"), _h("SECRET", "R", "unit-9", "unit-1"),
    _h("NOT A CLASSIFICATION"), _h(code="NOT-A-CODE"),
]  # fmt: skip
READERS = [
    Principal(id="o", clearance="OFFICIAL", org_unit="unit-1"),
    Principal(id="s", clearance="SECRET", org_unit="unit-1"),
    Principal(id="s-r", clearance="SECRET", org_unit="unit-1", receivable_handling_codes=["R"]),
    Principal(id="s-r2", clearance="SECRET", org_unit="unit-2", receivable_handling_codes=["R"]),
    Principal(id="ts-r9", clearance="TOP SECRET", org_unit="unit-9", receivable_handling_codes=["R"]),
    Principal(id="unknown", clearance="NOT A CLEARANCE", org_unit="unit-1"),
]


async def test_the_query_and_the_python_rule_agree_on_every_handling(store: PackStore) -> None:
    pack = await store.create("case-q", "parity", AUTHOR)
    combos = [(h,) for h in HANDLINGS] + list(itertools.combinations(HANDLINGS, 2)) + [()]
    items = {}
    for combo in combos:
        item = _item(*combo)
        items[item.id] = combo
        await store.add_item(pack.id, item)
    for reader in READERS:
        shown, withheld = await store.readable_items(pack.id, reader, SCHEME)
        expected = {i for i, combo in items.items() if item_visible(list(combo), reader, SCHEME)}
        assert {i.id for i in shown} == expected, reader.id
        assert withheld is (len(expected) < len(items)), reader.id


async def test_the_store_returns_no_hidden_item_only_a_yes_or_no(store: PackStore) -> None:
    pack = await store.create("case-q", "hidden", AUTHOR)
    seen, hidden = _item(_h(), note="seen"), _item(_h(), _h("SECRET"), note="hidden")
    for item in (seen, hidden):
        await store.add_item(pack.id, item)
    reader = READERS[0]
    shown, withheld = await store.readable_items(pack.id, reader, SCHEME)
    assert [i.note for i in shown] == ["seen"] and withheld is True
    assert hidden.id not in repr(shown)
    alone = await store.create("case-q", "nothing hidden", AUTHOR)
    await store.add_item(alone.id, _item(_h(), note="seen"))
    assert (await store.readable_items(alone.id, reader, SCHEME))[1] is False


async def test_a_version_and_the_history_are_filtered_in_the_query_too(store: PackStore) -> None:
    pack = await store.create("case-q", "versions", AUTHOR)
    seen, hidden = _item(_h(), note="seen"), _item(_h("SECRET"), note="hidden")
    for item in (seen, hidden):
        await store.add_item(pack.id, item)
    version = await store.publish(pack.id, AUTHOR)
    reader = READERS[0]
    found = await store.readable_version(pack.id, reader, SCHEME, version=version.version)
    assert found is not None
    meta, shown, withheld = found
    assert (meta.version, [i.note for i in shown], withheld) == (version.version, ["seen"], True)
    latest = await store.readable_version(pack.id, reader, SCHEME)
    assert latest is not None and [i.note for i in latest[1]] == ["seen"]
    await store.replace_item(pack.id, hidden.id, _item(_h(), note="refreshed"))
    earlier, earlier_withheld = await store.readable_earlier(pack.id, reader, SCHEME)
    assert (earlier, earlier_withheld) == ([], True)
    earlier, earlier_withheld = await store.readable_earlier(pack.id, READERS[1], SCHEME)
    assert ([i.note for i in earlier], earlier_withheld) == (["hidden"], False)


async def test_a_reorder_keeps_hidden_items_in_their_places_inside_the_store(store: PackStore) -> None:
    pack = await store.create("case-q", "order", AUTHOR)
    a, hidden, b, c = (_item(_h(), note="a"), _item(_h("SECRET"), note="hidden"),
                       _item(_h(), note="b"), _item(_h(), note="c"))  # fmt: skip
    for item in (a, hidden, b, c):
        await store.add_item(pack.id, item)
    reader = READERS[0]
    await store.reorder_visible(pack.id, reader, SCHEME, [c.id, a.id, b.id])
    assert [i.note for i in await store.items(pack.id)] == ["c", "hidden", "a", "b"]
    for wrong in ([a.id, b.id], [a.id, b.id, c.id, hidden.id], [a.id, a.id, b.id, c.id]):
        with pytest.raises(ValueError):
            await store.reorder_visible(pack.id, reader, SCHEME, wrong)
