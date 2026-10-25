"""Link notes — `06_DECISIONS.md` ADR-075. The service's own rules, against an in-memory note
store and `FakeWorkingSetStore`; the real Postgres store has its own file
(`test_link_notes_store.py`, owner-run like the other store tests).

The rule under test is one sentence: a note is readable and writable by exactly the people who can
see its link, and only its author changes or removes it. Each case below is a way that sentence
could be broken, and names the refusal the real store and the real working set also give
(`CLAUDE.md` rule 15: the stand-ins refuse what the real ones refuse)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from services.api.link_notes import (
    MAX_NOTE_CHARS,
    InvalidNoteError,
    LinkNoteService,
    LinkNoteStorage,
    LinkNotFoundError,
    NoteNotFoundError,
    NoteNotYoursError,
    StoredNote,
)
from services.api.working_set.service import WorkingSetService

from schemas.domain import Principal, Subgraph

from .working_set.fakes import FakeGraphPort, FakeWorkingSetStore
from .working_set.test_visible_link import SCHEME, edge, node

ANALYST = Principal(id="analyst-1", clearance="OFFICIAL", org_unit="unit-1")
COLLEAGUE = Principal(id="analyst-2", clearance="OFFICIAL", org_unit="unit-1")
CLEARED = Principal(id="analyst-3", clearance="SECRET", org_unit="unit-1")


class InMemoryNotes:
    """Refuses what the Postgres store refuses: a change or removal names the investigation, the
    link *and* the author, and finds nothing when any of the three differs."""

    def __init__(self) -> None:
        self.rows: list[StoredNote] = []
        self._next = 0
        self.clock = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)

    def tick(self, minutes: int = 1) -> datetime:
        from datetime import timedelta

        self.clock = self.clock + timedelta(minutes=minutes)
        return self.clock

    async def add(self, investigation_id: str, edge_id: str, author: str, body: str) -> StoredNote:
        self._next += 1
        row = StoredNote(
            id=f"note-{self._next}",
            investigation_id=investigation_id,
            edge_id=edge_id,
            author=author,
            body=body,
            created_at=self.tick(),
            edited_at=None,
        )
        self.rows.append(row)
        return row

    async def list_for_link(self, investigation_id: str, edge_id: str) -> list[StoredNote]:
        found = [
            r for r in self.rows if r.investigation_id == investigation_id and r.edge_id == edge_id
        ]
        return sorted(found, key=lambda r: (r.created_at, r.id), reverse=True)

    async def get(self, investigation_id: str, edge_id: str, note_id: str) -> StoredNote | None:
        for r in self.rows:
            if (r.investigation_id, r.edge_id, r.id) == (investigation_id, edge_id, note_id):
                return r
        return None

    async def edit(
        self, investigation_id: str, edge_id: str, note_id: str, author: str, body: str
    ) -> StoredNote | None:
        for i, r in enumerate(self.rows):
            if (r.investigation_id, r.edge_id, r.id, r.author) == (
                investigation_id,
                edge_id,
                note_id,
                author,
            ):
                self.rows[i] = r.model_copy(update={"body": body, "edited_at": self.tick()})
                return self.rows[i]
        return None

    async def remove(self, investigation_id: str, edge_id: str, note_id: str, author: str) -> bool:
        before = len(self.rows)
        self.rows = [
            r
            for r in self.rows
            if (r.investigation_id, r.edge_id, r.id, r.author)
            != (investigation_id, edge_id, note_id, author)
        ]
        return len(self.rows) < before

    async def rekey(self, investigation_id: str, old_edge_id: str, new_edge_id: str) -> int:
        moved = 0
        for i, r in enumerate(self.rows):
            if (r.investigation_id, r.edge_id) == (investigation_id, old_edge_id):
                self.rows[i] = r.model_copy(update={"edge_id": new_edge_id})
                moved += 1
        return moved


async def _service() -> tuple[LinkNoteService, InMemoryNotes, FakeWorkingSetStore]:
    working = FakeWorkingSetStore()
    await working.add_nodes("inv-1", [node("a"), node("b"), node("c", "SECRET")])
    await working.add_edges(
        "inv-1",
        [
            edge("open", "a", "b"),
            edge("secret-link", "a", "b", "SECRET"),
            edge("secret-end", "a", "c"),
        ],
    )
    graph = FakeGraphPort(Subgraph(nodes=[], edges=[]))
    notes = InMemoryNotes()
    storage: LinkNoteStorage = notes
    return LinkNoteService(storage, WorkingSetService(graph, working, SCHEME)), notes, working


async def test_a_note_is_added_and_read_back_with_its_author_and_time() -> None:
    service, _, _ = await _service()
    added = await service.add("inv-1", "open", ANALYST, "Seen at the same address twice.")
    listed = await service.list("inv-1", "open", ANALYST)
    assert [n.id for n in listed] == [added.id]
    assert listed[0].author == "analyst-1"
    assert listed[0].body == "Seen at the same address twice."
    assert listed[0].created_at.tzinfo is not None
    assert listed[0].edited_at is None


async def test_several_notes_come_back_newest_first() -> None:
    service, _, _ = await _service()
    first = await service.add("inv-1", "open", ANALYST, "first")
    second = await service.add("inv-1", "open", COLLEAGUE, "second")
    third = await service.add("inv-1", "open", ANALYST, "third")
    assert [n.id for n in await service.list("inv-1", "open", ANALYST)] == [
        third.id,
        second.id,
        first.id,
    ]


async def test_a_link_with_no_notes_lists_empty() -> None:
    service, _, _ = await _service()
    assert await service.list("inv-1", "open", ANALYST) == []


async def test_each_reader_sees_which_notes_are_their_own() -> None:
    service, _, _ = await _service()
    await service.add("inv-1", "open", ANALYST, "mine")
    await service.add("inv-1", "open", COLLEAGUE, "theirs")
    mine = {n.body: n.mine for n in await service.list("inv-1", "open", ANALYST)}
    theirs = {n.body: n.mine for n in await service.list("inv-1", "open", COLLEAGUE)}
    assert mine == {"mine": True, "theirs": False}
    assert theirs == {"mine": False, "theirs": True}


async def test_a_colleague_who_can_see_the_link_reads_the_note() -> None:
    service, _, _ = await _service()
    await service.add("inv-1", "open", ANALYST, "visible to the team")
    assert [n.body for n in await service.list("inv-1", "open", COLLEAGUE)] == [
        "visible to the team"
    ]


# --- read paths: a link you cannot see has no notes you can read (rule 4) -----------------


async def test_reading_the_notes_of_a_link_above_your_clearance_is_refused_not_empty() -> None:
    service, _, _ = await _service()
    await service.add("inv-1", "secret-link", CLEARED, "cleared eyes only")
    with pytest.raises(LinkNotFoundError):
        await service.list("inv-1", "secret-link", ANALYST)


async def test_reading_the_notes_of_a_link_with_a_hidden_end_is_refused() -> None:
    service, _, _ = await _service()
    await service.add("inv-1", "secret-end", CLEARED, "about a hidden end")
    with pytest.raises(LinkNotFoundError):
        await service.list("inv-1", "secret-end", ANALYST)


async def test_a_hidden_link_and_a_link_that_does_not_exist_refuse_identically() -> None:
    service, _, _ = await _service()
    with pytest.raises(LinkNotFoundError) as hidden:
        await service.list("inv-1", "secret-link", ANALYST)
    with pytest.raises(LinkNotFoundError) as missing:
        await service.list("inv-1", "no-such-link", ANALYST)
    assert type(hidden.value) is type(missing.value)
    assert str(hidden.value) == str(missing.value).replace("no-such-link", "secret-link")


async def test_the_cleared_reader_does_read_the_hidden_links_notes() -> None:
    service, _, _ = await _service()
    await service.add("inv-1", "secret-link", CLEARED, "cleared eyes only")
    assert [n.body for n in await service.list("inv-1", "secret-link", CLEARED)] == [
        "cleared eyes only"
    ]


async def test_a_note_is_not_readable_through_another_investigation() -> None:
    service, _, working = await _service()
    await working.add_nodes("inv-2", [node("a"), node("b")])
    await working.add_edges("inv-2", [edge("open", "a", "b")])
    await service.add("inv-1", "open", ANALYST, "belongs to case one")
    assert await service.list("inv-2", "open", ANALYST) == []


# --- write paths --------------------------------------------------------------------------


async def test_adding_a_note_to_a_link_you_cannot_see_is_refused_and_stores_nothing() -> None:
    service, notes, _ = await _service()
    with pytest.raises(LinkNotFoundError):
        await service.add("inv-1", "secret-link", ANALYST, "should not land")
    with pytest.raises(LinkNotFoundError):
        await service.add("inv-1", "no-such-link", ANALYST, "should not land")
    assert notes.rows == []


@pytest.mark.parametrize("body", ["", "   ", "\n\t "])
async def test_an_empty_note_is_refused(body: str) -> None:
    service, notes, _ = await _service()
    with pytest.raises(InvalidNoteError):
        await service.add("inv-1", "open", ANALYST, body)
    assert notes.rows == []


async def test_a_note_over_the_length_limit_is_refused_and_one_at_the_limit_is_kept() -> None:
    service, _, _ = await _service()
    with pytest.raises(InvalidNoteError):
        await service.add("inv-1", "open", ANALYST, "x" * (MAX_NOTE_CHARS + 1))
    kept = await service.add("inv-1", "open", ANALYST, "x" * MAX_NOTE_CHARS)
    assert len(kept.body) == MAX_NOTE_CHARS


async def test_a_note_keeps_its_text_as_typed_apart_from_the_ends() -> None:
    service, _, _ = await _service()
    added = await service.add("inv-1", "open", ANALYST, "  <b>not markup</b>\nsecond line \n")
    assert added.body == "<b>not markup</b>\nsecond line"


async def test_the_author_edits_their_own_note_and_it_says_when() -> None:
    service, _, _ = await _service()
    added = await service.add("inv-1", "open", ANALYST, "draft")
    edited = await service.edit("inv-1", "open", added.id, ANALYST, "final wording")
    assert edited.body == "final wording"
    assert edited.edited_at is not None
    assert edited.created_at == added.created_at
    assert edited.mine is True


async def test_a_colleague_cannot_edit_a_note_that_is_not_theirs() -> None:
    service, notes, _ = await _service()
    added = await service.add("inv-1", "open", ANALYST, "original")
    with pytest.raises(NoteNotYoursError):
        await service.edit("inv-1", "open", added.id, COLLEAGUE, "tampered")
    assert notes.rows[0].body == "original"


async def test_a_colleague_cannot_remove_a_note_that_is_not_theirs() -> None:
    service, notes, _ = await _service()
    added = await service.add("inv-1", "open", ANALYST, "keep me")
    with pytest.raises(NoteNotYoursError):
        await service.remove("inv-1", "open", added.id, COLLEAGUE)
    assert len(notes.rows) == 1


async def test_the_author_removes_their_own_note() -> None:
    service, notes, _ = await _service()
    added = await service.add("inv-1", "open", ANALYST, "remove me")
    await service.remove("inv-1", "open", added.id, ANALYST)
    assert notes.rows == []


async def test_editing_or_removing_a_note_that_is_not_there_is_not_found() -> None:
    service, _, _ = await _service()
    with pytest.raises(NoteNotFoundError):
        await service.edit("inv-1", "open", "no-such-note", ANALYST, "x")
    with pytest.raises(NoteNotFoundError):
        await service.remove("inv-1", "open", "no-such-note", ANALYST)


async def test_a_note_cannot_be_reached_by_naming_a_different_link() -> None:
    """The note id alone must not be enough: it is looked up under the link and case in the path."""
    service, notes, _ = await _service()
    added = await service.add("inv-1", "open", ANALYST, "on the open link")
    await service.add("inv-1", "secret-link", CLEARED, "on the other link")
    with pytest.raises(LinkNotFoundError):
        await service.edit("inv-1", "secret-link", added.id, ANALYST, "x")
    assert notes.rows[0].body == "on the open link"


async def test_a_note_is_not_editable_once_its_link_is_no_longer_visible_to_its_author() -> None:
    service, notes, working = await _service()
    added = await service.add("inv-1", "open", ANALYST, "mine")
    await working.remove_nodes("inv-1", ["a"])
    with pytest.raises(LinkNotFoundError):
        await service.edit("inv-1", "open", added.id, ANALYST, "x")
    with pytest.raises(LinkNotFoundError):
        await service.remove("inv-1", "open", added.id, ANALYST)
    assert notes.rows[0].body == "mine"
