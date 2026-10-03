"""Analyst notes on links — `06_DECISIONS.md` ADR-075, `02_GLASS_FRONTEND.md` §2 (Inspector).

A note is plain text an analyst attaches to one link in one investigation. Several per link, each
with its author and time, newest first. Control-plane metadata like `assessments.py`: small,
relational, Postgres, idempotent bootstrap SQL — not graph content, and never written to the graph.

**Who may read or write a note: whoever can see its link, and only its author changes or removes
it.** "Can see the link" is not a second rule invented here; it is
`WorkingSetService.visible_edge`, the same handling filter (`_project`) every list read already
applies — the link's own marking and both of its ends must clear the principal's clearance, and
the link must be in this investigation's working set. A link the principal cannot see answers
exactly as a link that does not exist (`LinkNotFoundError`), on every path — list, add, edit,
remove — so a refusal cannot be used to learn that a hidden link exists, and a note's text is
never reachable except through the link it hangs on (`CLAUDE.md` rules 3 and 4). The case-level
Viewer/Editor level (`03_CONDUIT_MIDDLEWARE.md` §2) is checked by the route before this runs.

**Why working-set membership and not the graph.** `GraphPort` has no `get_edge` (the disclosed gap
`assessments.py` already names), so the graph cannot be asked whether one link is visible. The
working set holds every link an analyst can have on screen and is what the Glass draws, so "in the
working set and clearing the filter" is exactly "the analyst can see and select it". Consequence,
disclosed: a note on a link is unreachable while the link is outside the working set (the nodes
were tidied away); it is still stored and comes back when the link does.

**Notes inherit the link's handling by construction, not by copying it.** The note carries no
marking of its own; it is shown only to someone the link is shown to. If the link is later
re-marked above a reader, that reader loses the notes at the same moment. What this does not do is
raise the marking of a note whose *text* quotes something more sensitive than its link; the Glass
says so beside the box.

**Author-only change.** `edit`/`remove` name the author in the query's own `WHERE` clause, so a
note that is not the caller's matches nothing, and the service then tells "not there" (404) from
"not yours" (403) with a second read. The author is already shown beside every note, so 403 leaks
nothing the list did not.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol

import asyncpg
from pydantic import BaseModel

from conduit_common.identity import new_id
from schemas.domain import LinkNote, Principal

from .working_set.service import WorkingSetService

#: A note is a line or two of working-out, not a document. The limit is a sentence's worth of
#: generosity (about a page) and is shown to the analyst as it is approached.
MAX_NOTE_CHARS = 4000

_BOOTSTRAP_SQL = """
CREATE TABLE IF NOT EXISTS link_notes (
    id TEXT PRIMARY KEY,
    investigation_id TEXT NOT NULL,
    edge_id TEXT NOT NULL,
    author TEXT NOT NULL,
    body TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    edited_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS link_notes_link_idx ON link_notes (investigation_id, edge_id);
"""


class LinkNotFoundError(Exception):
    """The link is not in this investigation's working set, or this principal may not see it —
    deliberately one error for both, the same existence-leak discipline `JudgementNotFoundError`
    follows."""

    def __init__(self, edge_id: str) -> None:
        self.edge_id = edge_id
        super().__init__(f"link {edge_id} not found")


class NoteNotFoundError(Exception):
    """The link is visible but holds no note with this id."""


class NoteNotYoursError(Exception):
    """Another analyst wrote this note; only its author changes or removes it."""


class InvalidNoteError(Exception):
    """An empty note, or one over `MAX_NOTE_CHARS`. Carries a sentence the Glass shows as given."""


class LinkNoteBody(BaseModel):
    """The request body for adding or changing a note. Length is judged by the service, which
    answers in a sentence the Glass shows as given, so no `max_length` here."""

    body: str


class LinkNoteListResponse(BaseModel):
    notes: list[LinkNote]


class StoredNote(BaseModel):
    id: str
    investigation_id: str
    edge_id: str
    author: str
    body: str
    created_at: datetime
    edited_at: datetime | None = None


class LinkNoteStorage(Protocol):
    async def add(
        self, investigation_id: str, edge_id: str, author: str, body: str
    ) -> StoredNote: ...

    async def list_for_link(self, investigation_id: str, edge_id: str) -> list[StoredNote]:
        """Newest first."""
        ...

    async def get(self, investigation_id: str, edge_id: str, note_id: str) -> StoredNote | None: ...

    async def edit(
        self, investigation_id: str, edge_id: str, note_id: str, author: str, body: str
    ) -> StoredNote | None:
        """`None` when no note matches *all four* of case, link, id and author."""
        ...

    async def remove(self, investigation_id: str, edge_id: str, note_id: str, author: str) -> bool:
        """`False` when no note matches all four."""
        ...


def _row(row: asyncpg.Record) -> StoredNote:
    return StoredNote(
        id=row["id"],
        investigation_id=row["investigation_id"],
        edge_id=row["edge_id"],
        author=row["author"],
        body=row["body"],
        created_at=row["created_at"],
        edited_at=row["edited_at"],
    )


class LinkNoteStore:
    """Postgres. Every statement names the case and the link; a change or removal also names the
    author, so the database itself refuses a note that is not the caller's."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    @classmethod
    async def connect(cls, dsn: str) -> LinkNoteStore:
        pool = await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=5)
        async with pool.acquire() as conn:
            await conn.execute(_BOOTSTRAP_SQL)
        return cls(pool)

    async def close(self) -> None:
        await self._pool.close()

    async def add(self, investigation_id: str, edge_id: str, author: str, body: str) -> StoredNote:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "INSERT INTO link_notes (id, investigation_id, edge_id, author, body, created_at) "
                "VALUES ($1, $2, $3, $4, $5, $6) RETURNING *",
                new_id(),
                investigation_id,
                edge_id,
                author,
                body,
                datetime.now(UTC),
            )
        return _row(row)

    async def list_for_link(self, investigation_id: str, edge_id: str) -> list[StoredNote]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM link_notes WHERE investigation_id = $1 AND edge_id = $2 "
                "ORDER BY created_at DESC, id DESC",
                investigation_id,
                edge_id,
            )
        return [_row(r) for r in rows]

    async def get(self, investigation_id: str, edge_id: str, note_id: str) -> StoredNote | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM link_notes WHERE id = $1 AND investigation_id = $2 AND edge_id = $3",
                note_id,
                investigation_id,
                edge_id,
            )
        return _row(row) if row else None

    async def edit(
        self, investigation_id: str, edge_id: str, note_id: str, author: str, body: str
    ) -> StoredNote | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "UPDATE link_notes SET body = $5, edited_at = $6 WHERE id = $1 "
                "AND investigation_id = $2 AND edge_id = $3 AND author = $4 RETURNING *",
                note_id,
                investigation_id,
                edge_id,
                author,
                body,
                datetime.now(UTC),
            )
        return _row(row) if row else None

    async def remove(self, investigation_id: str, edge_id: str, note_id: str, author: str) -> bool:
        async with self._pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM link_notes WHERE id = $1 AND investigation_id = $2 "
                "AND edge_id = $3 AND author = $4",
                note_id,
                investigation_id,
                edge_id,
                author,
            )
        return str(result).endswith(" 1")


def _clean(body: str) -> str:
    text = body.strip()
    if not text:
        raise InvalidNoteError("A note cannot be empty.")
    if len(text) > MAX_NOTE_CHARS:
        raise InvalidNoteError(f"A note can be at most {MAX_NOTE_CHARS} characters.")
    return text


def _view(note: StoredNote, principal: Principal) -> LinkNote:
    return LinkNote(
        id=note.id,
        investigation_id=note.investigation_id,
        edge_id=note.edge_id,
        author=note.author,
        body=note.body,
        created_at=note.created_at,
        edited_at=note.edited_at,
        mine=note.author == principal.id,
    )


class LinkNoteService:
    def __init__(self, store: LinkNoteStorage, working_set: WorkingSetService) -> None:
        self._store = store
        self._working_set = working_set

    async def _require_visible(
        self, investigation_id: str, edge_id: str, principal: Principal
    ) -> None:
        if await self._working_set.visible_edge(investigation_id, edge_id, principal) is None:
            raise LinkNotFoundError(edge_id)

    async def list(
        self, investigation_id: str, edge_id: str, principal: Principal
    ) -> list[LinkNote]:
        await self._require_visible(investigation_id, edge_id, principal)
        notes = await self._store.list_for_link(investigation_id, edge_id)
        return [_view(n, principal) for n in notes]

    async def add(
        self, investigation_id: str, edge_id: str, principal: Principal, body: str
    ) -> LinkNote:
        await self._require_visible(investigation_id, edge_id, principal)
        text = _clean(body)
        stored = await self._store.add(investigation_id, edge_id, principal.id, text)
        return _view(stored, principal)

    async def edit(
        self,
        investigation_id: str,
        edge_id: str,
        note_id: str,
        principal: Principal,
        body: str,
    ) -> LinkNote:
        await self._require_visible(investigation_id, edge_id, principal)
        text = _clean(body)
        changed = await self._store.edit(investigation_id, edge_id, note_id, principal.id, text)
        if changed is None:
            await self._explain_refusal(investigation_id, edge_id, note_id)
            raise AssertionError("unreachable")  # pragma: no cover
        return _view(changed, principal)

    async def remove(
        self, investigation_id: str, edge_id: str, note_id: str, principal: Principal
    ) -> None:
        await self._require_visible(investigation_id, edge_id, principal)
        if not await self._store.remove(investigation_id, edge_id, note_id, principal.id):
            await self._explain_refusal(investigation_id, edge_id, note_id)

    async def _explain_refusal(self, investigation_id: str, edge_id: str, note_id: str) -> None:
        """The author-scoped write matched nothing. Either the note is not there or it is someone
        else's; the link is already known visible, so saying which leaks nothing."""
        if await self._store.get(investigation_id, edge_id, note_id) is None:
            raise NoteNotFoundError(note_id)
        raise NoteNotYoursError(note_id)
