"""`LinkNoteStore` against real Postgres (`make dev-up`) — the half `test_link_notes.py`'s
in-memory stand-in cannot prove: that the database itself refuses a change or removal when the
author, the link or the case differs, as the stand-in was written to model."""

from __future__ import annotations

import pytest
from services.api.config import PostgresConfig
from services.api.link_notes import LinkNoteStore

from conduit_common.identity import new_id


@pytest.fixture
async def store():
    s = await LinkNoteStore.connect(PostgresConfig.from_env().dsn)
    yield s
    await s.close()


async def test_a_note_round_trips_and_lists_newest_first(store) -> None:
    inv, edge = new_id(), new_id()
    first = await store.add(inv, edge, "analyst-1", "first")
    second = await store.add(inv, edge, "analyst-2", "second")
    listed = await store.list_for_link(inv, edge)
    assert [n.id for n in listed] == [second.id, first.id]
    assert listed[0].edited_at is None


async def test_notes_are_kept_per_case_and_per_link(store) -> None:
    inv, edge = new_id(), new_id()
    await store.add(inv, edge, "analyst-1", "here")
    assert await store.list_for_link(new_id(), edge) == []
    assert await store.list_for_link(inv, new_id()) == []


async def test_only_the_author_changes_a_note(store) -> None:
    inv, edge = new_id(), new_id()
    note = await store.add(inv, edge, "analyst-1", "original")
    assert await store.edit(inv, edge, note.id, "analyst-2", "tampered") is None
    assert (await store.get(inv, edge, note.id)).body == "original"
    changed = await store.edit(inv, edge, note.id, "analyst-1", "revised")
    assert changed is not None and changed.body == "revised" and changed.edited_at is not None


async def test_a_note_cannot_be_changed_or_removed_under_another_link_or_case(store) -> None:
    inv, edge = new_id(), new_id()
    note = await store.add(inv, edge, "analyst-1", "original")
    assert await store.edit(inv, new_id(), note.id, "analyst-1", "x") is None
    assert await store.edit(new_id(), edge, note.id, "analyst-1", "x") is None
    assert await store.remove(inv, new_id(), note.id, "analyst-1") is False
    assert await store.remove(new_id(), edge, note.id, "analyst-1") is False
    assert await store.get(inv, edge, note.id) is not None


async def test_only_the_author_removes_a_note(store) -> None:
    inv, edge = new_id(), new_id()
    note = await store.add(inv, edge, "analyst-1", "keep")
    assert await store.remove(inv, edge, note.id, "analyst-2") is False
    assert await store.remove(inv, edge, note.id, "analyst-1") is True
    assert await store.get(inv, edge, note.id) is None
    assert await store.remove(inv, edge, note.id, "analyst-1") is False
