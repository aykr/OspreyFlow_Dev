"""The case brief — `06_DECISIONS.md` ADR-128 decision 3, script chapter 1.

A case's brief is the question the case is meant to answer: one **priority information requirement**
(a text) and up to twenty **information requirements**, each with a text, a status (open or
answered) and attachments to what answers it: a saved trend, a saved pattern, an assessment, or a
canvas view (a tab: a case the reader may open). Control-plane metadata like `link_notes.py`: small,
relational, Postgres, idempotent bootstrap SQL, stored with the case and never written to the graph.

**Who reads and who edits.** Anyone who may read the case reads its brief; only its Author edits.
Both levels are the *route's* (`InvestigationViewerDep`, `InvestigationAuthorDep`), checked before
anything here runs, as the link notes' are. Nothing in this module judges a case level.

**Rule 3: an attachment the reader may not read is left out entirely.** An attachment is a stored
reference, `(kind, id)`, and the brief shows it only with the title the reference's own store gives
to *this reader* (`TitleResolver`): a trend of this case, a saved pattern the reader owns, an
assessment ADR-046's hide rule leaves visible to the reader, a case the reader holds a level on.
Where the answer is None the attachment is not drawn at all: no title, no placeholder, no count (the
wire form has no count field), so the reader's response equals the response for a brief that never
had it. The check is made on every read, not once at attach time, so an attachment whose target
changed hands or was removed drops out at once. The same words refuse an attach whose target does
not exist and one the Author may not read (`AttachmentNotFoundError`), so the refusal cannot be used
to learn that a hidden thing exists. **No last-edited time is on the wire** for the same reason: an
attach the reader cannot see must not move anything the reader can.

**Rule 5: no model path sets a status.** `CaseBriefService.set_status` is reached from exactly one
route, the person's own (`PUT .../brief/requirements/{id}/status`), and from nothing under
`services/` that talks to a model; `tests/services/api/test_case_brief_status.py` walks the source
and fails if either stops being true. The add and edit routes' bodies refuse a `status` field.

**Rule 2: nothing is cut silently.** More than twenty requirements, more than ten attachments on one
requirement, or a text over its limit is refused, naming the limit, and what was there stays. The
ten counts only the attachments the person asking can read (rule 3): a refusal that counted the
rest would tell them those exist.

**One transition, two stores.** Each change is a pure function from the stored brief to the next
(`with_*`), applied by `CaseBriefStorage.update` under a row lock in Postgres
(`CaseBriefStore`) and by the in-memory stand-in the tests use, so a cap or a refusal cannot differ
between the two (`CLAUDE.md` rule 15: the fake refuses what the real one refuses).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from datetime import UTC, datetime
from typing import Literal, Protocol

import asyncpg
from pydantic import BaseModel, ConfigDict, Field

from conduit_common.identity import new_id
from schemas.domain import Principal

#: ADR-128: "up to twenty information requirements".
MAX_REQUIREMENTS = 20
#: Not in the ADR: a brief's requirement is answered by a handful of things. Ten is generous, and is
#: refused by name like the twenty, never cut. Disclosed to the coordinator in the build report.
MAX_ATTACHMENTS = 10
#: A requirement is a sentence or two. The limit is a page's worth, shown to the Author as it is
#: approached.
MAX_TEXT_CHARS = 2000

AttachmentKind = Literal["trend", "pattern", "assessment", "view"]
RequirementStatus = Literal["open", "answered"]

_BOOTSTRAP_SQL = """
CREATE TABLE IF NOT EXISTS case_briefs (
    investigation_id TEXT PRIMARY KEY,
    brief JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);
"""


# --- refusals -------------------------------------------------------------------------------


class CaseBriefError(Exception):
    """A refusal `app.py` answers with `status_code` and `{"error": error, "detail": <sentence>}`.
    The sentence is shown as given."""

    status_code = 422
    error = "case_brief_refused"


class InvalidBriefTextError(CaseBriefError):
    status_code = 422
    error = "invalid_brief_text"


class RequirementNotFoundError(CaseBriefError):
    """This case's brief holds no requirement with that id (another case's included)."""

    status_code = 404
    error = "requirement_not_found"

    def __init__(self) -> None:
        super().__init__("That requirement is not in this brief.")


class TooManyRequirementsError(CaseBriefError):
    status_code = 409
    error = "too_many_requirements"

    def __init__(self) -> None:
        super().__init__(f"A brief can hold at most {MAX_REQUIREMENTS} requirements.")


class TooManyAttachmentsError(CaseBriefError):
    status_code = 409
    error = "too_many_attachments"

    def __init__(self) -> None:
        super().__init__(f"A requirement can have at most {MAX_ATTACHMENTS} attachments.")


class AttachmentNotFoundError(CaseBriefError):
    """The thing to attach does not exist, or this person may not read it: one answer for both, in
    the same words, as `JudgementNotFoundError` and `LinkNotFoundError` give (rules 3 and 4)."""

    status_code = 404
    error = "attachment_not_found"

    def __init__(self) -> None:
        super().__init__("That cannot be attached to this brief.")


# --- the stored form ------------------------------------------------------------------------


class StoredAttachment(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: AttachmentKind
    id: str


class StoredRequirement(BaseModel):
    id: str
    text: str
    status: RequirementStatus = "open"
    #: Who marked it answered and when: kept, not sent (the wire form carries the time only).
    answered_by: str | None = None
    answered_at: datetime | None = None
    attachments: list[StoredAttachment] = Field(default_factory=list)


class StoredBrief(BaseModel):
    investigation_id: str
    priority: str = ""
    requirements: list[StoredRequirement] = Field(default_factory=list)
    updated_by: str | None = None
    updated_at: datetime | None = None


# --- the wire form --------------------------------------------------------------------------


class BriefAttachment(BaseModel):
    kind: AttachmentKind
    id: str
    title: str


class BriefRequirement(BaseModel):
    id: str
    text: str
    status: RequirementStatus
    answered_at: datetime | None = None
    attachments: list[BriefAttachment] = Field(default_factory=list)


class CaseBrief(BaseModel):
    """What the Glass reads. Deliberately no count, no last-edited time and no stored field beyond
    these: each is a way for a reader to notice what they may not read (module docstring)."""

    priority: str = ""
    requirements: list[BriefRequirement] = Field(default_factory=list)


class BriefTextBody(BaseModel):
    """Add a requirement, change its text, or set the priority. `extra="forbid"`: a `status`
    smuggled into any of them is refused (rule 5), not ignored."""

    model_config = ConfigDict(extra="forbid")

    text: str


class BriefStatusBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: RequirementStatus


class BriefAttachmentBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: AttachmentKind
    id: str = Field(min_length=1, max_length=200)


# --- the transitions ------------------------------------------------------------------------


def _clean(text: str, *, allow_empty: bool = False) -> str:
    cleaned = text.strip()
    if not cleaned and not allow_empty:
        raise InvalidBriefTextError("A requirement cannot be empty.")
    if len(cleaned) > MAX_TEXT_CHARS:
        raise InvalidBriefTextError(f"A brief's text can be at most {MAX_TEXT_CHARS} characters.")
    return cleaned


def _touched(brief: StoredBrief, by: str, now: datetime, **changes: object) -> StoredBrief:
    return brief.model_copy(update={"updated_by": by, "updated_at": now, **changes})


def _one(brief: StoredBrief, requirement_id: str) -> StoredRequirement:
    for requirement in brief.requirements:
        if requirement.id == requirement_id:
            return requirement
    raise RequirementNotFoundError


def _replaced(brief: StoredBrief, changed: StoredRequirement) -> list[StoredRequirement]:
    return [changed if r.id == changed.id else r for r in brief.requirements]


def with_priority(brief: StoredBrief, text: str, by: str, now: datetime) -> StoredBrief:
    return _touched(brief, by, now, priority=_clean(text, allow_empty=True))


def with_requirement_added(
    brief: StoredBrief, requirement_id: str, text: str, by: str, now: datetime
) -> StoredBrief:
    cleaned = _clean(text)
    if len(brief.requirements) >= MAX_REQUIREMENTS:
        raise TooManyRequirementsError
    added = StoredRequirement(id=requirement_id, text=cleaned)
    return _touched(brief, by, now, requirements=[*brief.requirements, added])


def with_requirement_edited(
    brief: StoredBrief, requirement_id: str, text: str, by: str, now: datetime
) -> StoredBrief:
    current = _one(brief, requirement_id)
    changed = current.model_copy(update={"text": _clean(text)})
    return _touched(brief, by, now, requirements=_replaced(brief, changed))


def with_status(
    brief: StoredBrief, requirement_id: str, status: RequirementStatus, by: str, now: datetime
) -> StoredBrief:
    current = _one(brief, requirement_id)
    answered = status == "answered"
    changed = current.model_copy(
        update={
            "status": status,
            "answered_by": by if answered else None,
            "answered_at": now if answered else None,
        }
    )
    return _touched(brief, by, now, requirements=_replaced(brief, changed))


def without_requirement(
    brief: StoredBrief, requirement_id: str, by: str, now: datetime
) -> StoredBrief:
    _one(brief, requirement_id)
    kept = [r for r in brief.requirements if r.id != requirement_id]
    return _touched(brief, by, now, requirements=kept)


def with_attachment(
    brief: StoredBrief,
    requirement_id: str,
    attachment: StoredAttachment,
    by: str,
    now: datetime,
    hidden: frozenset[StoredAttachment] = frozenset(),
) -> StoredBrief:
    """`hidden` is what the caller may not read among the requirement's attachments. The cap counts
    the rest alone, so a refusal is decided by what the caller can see and cannot be used to learn
    that attachments they may not read exist (rule 3); the stored total may therefore exceed the
    cap, by what others attached out of this caller's sight."""
    current = _one(brief, requirement_id)
    if attachment in current.attachments:
        return brief
    if sum(1 for a in current.attachments if a not in hidden) >= MAX_ATTACHMENTS:
        raise TooManyAttachmentsError
    changed = current.model_copy(update={"attachments": [*current.attachments, attachment]})
    return _touched(brief, by, now, requirements=_replaced(brief, changed))


def without_attachment(
    brief: StoredBrief,
    requirement_id: str,
    attachment: StoredAttachment,
    by: str,
    now: datetime,
) -> StoredBrief:
    current = _one(brief, requirement_id)
    if attachment not in current.attachments:
        return brief
    kept = [a for a in current.attachments if a != attachment]
    changed = current.model_copy(update={"attachments": kept})
    return _touched(brief, by, now, requirements=_replaced(brief, changed))


# --- storage --------------------------------------------------------------------------------


class CaseBriefStorage(Protocol):
    async def get(self, investigation_id: str) -> StoredBrief:
        """The case's brief, an empty one for a case that has none."""
        ...

    async def update(
        self, investigation_id: str, change: Callable[[StoredBrief], StoredBrief]
    ) -> StoredBrief:
        """Applies `change` to the case's brief as one step nothing else interleaves with, stores
        what it returns and returns it. A refusal raised by `change` stores nothing."""
        ...


class CaseBriefStore:
    """Postgres. One row per case; `update` locks that row for the length of the change, so two
    requests adding a requirement at once cannot both pass the cap."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    @classmethod
    async def connect(cls, dsn: str) -> CaseBriefStore:
        pool = await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=5)
        async with pool.acquire() as conn:
            await conn.execute(_BOOTSTRAP_SQL)
        return cls(pool)

    async def close(self) -> None:
        await self._pool.close()

    async def get(self, investigation_id: str) -> StoredBrief:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT brief FROM case_briefs WHERE investigation_id = $1", investigation_id
            )
        if row is None:
            return StoredBrief(investigation_id=investigation_id)
        return StoredBrief.model_validate_json(row["brief"])

    async def update(
        self, investigation_id: str, change: Callable[[StoredBrief], StoredBrief]
    ) -> StoredBrief:
        empty = StoredBrief(investigation_id=investigation_id)
        async with self._pool.acquire() as conn, conn.transaction():
            await conn.execute(
                "INSERT INTO case_briefs (investigation_id, brief, updated_at) "
                "VALUES ($1, $2, $3) ON CONFLICT (investigation_id) DO NOTHING",
                investigation_id,
                empty.model_dump_json(),
                datetime.now(UTC),
            )
            row = await conn.fetchrow(
                "SELECT brief FROM case_briefs WHERE investigation_id = $1 FOR UPDATE",
                investigation_id,
            )
            assert row is not None
            changed = change(StoredBrief.model_validate_json(row["brief"]))
            await conn.execute(
                "UPDATE case_briefs SET brief = $2, updated_at = $3 WHERE investigation_id = $1",
                investigation_id,
                changed.model_dump_json(),
                datetime.now(UTC),
            )
        return changed


# --- the service ----------------------------------------------------------------------------

#: `(case id, the attachment's id, the reader) -> its title, or None when it does not exist or this
#: reader may not read it`. One per kind, built in `app.py` over that kind's own store and its own
#: access rule; the brief holds none of those rules itself.
TitleResolver = Callable[[str, str, Principal], Awaitable[str | None]]


class CaseBriefService:
    def __init__(
        self,
        store: CaseBriefStorage,
        resolvers: Mapping[str, TitleResolver],
        *,
        new_id: Callable[[], str] = new_id,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._store = store
        self._resolvers = resolvers
        self._new_id = new_id
        self._now = now

    async def _view(self, stored: StoredBrief, reader: Principal) -> CaseBrief:
        """The brief as `reader` may read it: an attachment with no title for this reader is not
        there. One look-up per distinct attachment, however often it is attached."""
        titles: dict[StoredAttachment, str | None] = {}
        requirements: list[BriefRequirement] = []
        for requirement in stored.requirements:
            shown: list[BriefAttachment] = []
            for attachment in requirement.attachments:
                if attachment not in titles:
                    titles[attachment] = await self._title(
                        stored.investigation_id, attachment, reader
                    )
                title = titles[attachment]
                if title is not None:
                    shown.append(
                        BriefAttachment(kind=attachment.kind, id=attachment.id, title=title)
                    )
            requirements.append(
                BriefRequirement(
                    id=requirement.id,
                    text=requirement.text,
                    status=requirement.status,
                    answered_at=requirement.answered_at,
                    attachments=shown,
                )
            )
        return CaseBrief(priority=stored.priority, requirements=requirements)

    async def _title(
        self, investigation_id: str, attachment: StoredAttachment, reader: Principal
    ) -> str | None:
        resolver = self._resolvers.get(attachment.kind)
        if resolver is None:
            return None
        return await resolver(investigation_id, attachment.id, reader)

    async def read(self, investigation_id: str, principal: Principal) -> CaseBrief:
        return await self._view(await self._store.get(investigation_id), principal)

    async def set_priority(
        self, investigation_id: str, principal: Principal, text: str
    ) -> CaseBrief:
        now = self._now()
        stored = await self._store.update(
            investigation_id, lambda b: with_priority(b, text, principal.id, now)
        )
        return await self._view(stored, principal)

    async def add_requirement(
        self, investigation_id: str, principal: Principal, text: str
    ) -> CaseBrief:
        requirement_id, now = self._new_id(), self._now()
        stored = await self._store.update(
            investigation_id,
            lambda b: with_requirement_added(b, requirement_id, text, principal.id, now),
        )
        return await self._view(stored, principal)

    async def edit_requirement(
        self, investigation_id: str, requirement_id: str, principal: Principal, text: str
    ) -> CaseBrief:
        now = self._now()
        stored = await self._store.update(
            investigation_id,
            lambda b: with_requirement_edited(b, requirement_id, text, principal.id, now),
        )
        return await self._view(stored, principal)

    async def set_status(
        self,
        investigation_id: str,
        requirement_id: str,
        principal: Principal,
        status: RequirementStatus,
    ) -> CaseBrief:
        """Rule 5: a person's, and only a person's, request to the status route reaches here
        (`test_case_brief_status.py`). The person is recorded as who marked it answered."""
        now = self._now()
        stored = await self._store.update(
            investigation_id,
            lambda b: with_status(b, requirement_id, status, principal.id, now),
        )
        return await self._view(stored, principal)

    async def seed_if_empty(
        self,
        investigation_id: str,
        principal: Principal,
        priority: str,
        requirements: list[str],
    ) -> bool:
        """The seed's write (ADR-128: the PID's brief is written as its case's author): the whole
        brief in one step when the case holds none, and nothing at all when it holds any (an
        analyst's own brief is never overwritten, and a second seed writes nothing). One step, so a
        seed that cannot write it whole (a limit, an invalid text) writes none of it. Every
        requirement is written open: this sets no status (rule 5). No route reaches it; it is the
        operator's command, and the caller has confirmed `principal` is the case's Author."""
        now = self._now()
        written = False

        def change(brief: StoredBrief) -> StoredBrief:
            nonlocal written
            if brief.priority or brief.requirements:
                return brief
            seeded = with_priority(brief, priority, principal.id, now)
            for text in requirements:
                seeded = with_requirement_added(seeded, self._new_id(), text, principal.id, now)
            written = True
            return seeded

        await self._store.update(investigation_id, change)
        return written

    async def remove_requirement(
        self, investigation_id: str, requirement_id: str, principal: Principal
    ) -> CaseBrief:
        now = self._now()
        stored = await self._store.update(
            investigation_id, lambda b: without_requirement(b, requirement_id, principal.id, now)
        )
        return await self._view(stored, principal)

    async def attach(
        self,
        investigation_id: str,
        requirement_id: str,
        principal: Principal,
        kind: AttachmentKind,
        attachment_id: str,
    ) -> CaseBrief:
        _one(await self._store.get(investigation_id), requirement_id)
        attachment = StoredAttachment(kind=kind, id=attachment_id)
        if await self._title(investigation_id, attachment, principal) is None:
            raise AttachmentNotFoundError
        now = self._now()
        hidden = await self._hidden_from(investigation_id, requirement_id, principal)
        stored = await self._store.update(
            investigation_id,
            lambda b: with_attachment(b, requirement_id, attachment, principal.id, now, hidden),
        )
        return await self._view(stored, principal)

    async def _hidden_from(
        self, investigation_id: str, requirement_id: str, reader: Principal
    ) -> frozenset[StoredAttachment]:
        """The requirement's attachments `reader` may not read, looked up once each."""
        current = _one(await self._store.get(investigation_id), requirement_id)
        hidden: set[StoredAttachment] = set()
        for attachment in current.attachments:
            if await self._title(investigation_id, attachment, reader) is None:
                hidden.add(attachment)
        return frozenset(hidden)

    async def detach(
        self,
        investigation_id: str,
        requirement_id: str,
        principal: Principal,
        kind: AttachmentKind,
        attachment_id: str,
    ) -> CaseBrief:
        """Takes an attachment off without reading it: an Author may drop what they can no longer
        read, and the answer is the same whether it was attached or not."""
        attachment = StoredAttachment(kind=kind, id=attachment_id)
        now = self._now()
        stored = await self._store.update(
            investigation_id,
            lambda b: without_attachment(b, requirement_id, attachment, principal.id, now),
        )
        return await self._view(stored, principal)
