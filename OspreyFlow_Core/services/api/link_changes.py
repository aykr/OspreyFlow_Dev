"""Changing a link, and the history of the changes — `06_DECISIONS.md` ADR-080,
`01_DOMAIN_MODEL.md` §8.2 (supersede), `02_GLASS_FRONTEND.md` §3.1f (the link menu).

An analyst can correct a link: its type, its details (the properties its type declares, its validity
period, how many times it was seen), or any of them together. **A link is never edited in place.**
The change is `GraphPort.supersede_edge`: the old link is kept, marked as replaced by the new one
and left out of ordinary reads, and a new link carrying the change takes its place in the working
set. Every change asks for a reason and is written down — who, when, why, and the old and new
values — in two places for two jobs:

* `audit_log` (`audit.py`, written by the route, fail-closed): the compliance stream, like every
  other write.
* `link_changes` (here, Postgres): the readable history an analyst opens from the link menu. The
  audit stream has no read path by design, so the history cannot be read back from it.

**What is not changed here.** `SAME_AS` and `NOT_SAME_AS` links are the resolution engine's; an
analyst's judgement on one is *Confirm as the same* / *Mark as not the same*, which write new
scored links and let the clusters follow (`CLAUDE.md` rule 6). Changing one by hand would let a
cluster and its links disagree, so it is refused, in either direction (a link cannot be changed
*into* one either).

**Who may change a link or read its history: whoever can see it** — the same
`WorkingSetService.visible_edge` question link notes ask, with the same single refusal for "not
there" and "not yours to see" (`LinkNotFoundError`), on both paths (rules 3 and 4). The case-level
Editor/Viewer level is checked by the route before this runs. A change keeps the link's marking and
its ends; it cannot be used to re-mark a link.

**Notes follow the link.** A superseded link has a new id, and notes are kept against a link's
id, so a change moves the old link's notes to the new one in the same step.

**What stands behind the link (ADR-081 step B, Amendment 2).** A change may say the link's
`basis`. A link of a Direct type may be marked `probabilistic`; the reason given for the change is
the reason for the mark, and the history shows the basis before and after. A link is never
promoted to Direct by a person: `direct` is refused on a link of a Probabilistic type and on any
link that is already probabilistic, by its type or by a mark. A basis left out keeps what stood
behind the link, so a probabilistic link changed to a Direct type is written with the mark.

**Disclosed gaps.** The link's `weight` is a load-time figure computed by the store when it writes
the replacement, and the port does not hand it back; the working set's copy keeps the old figure
until the link is next read from the graph. The history is read back by following `previous_edge_id`
links, bounded at `MAX_HISTORY` steps, and says so when it stops there.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal, Protocol

import asyncpg
from pydantic import BaseModel, ConfigDict

from conduit_common.identity import new_edge_id, new_id
from ontology.errors import HandlingSchemeError, OntologyError
from ontology.handling import (
    HandlingScheme,
    merge_handling,
    principal_may_view,
    sources_in_full,
    withhold_sources,
)
from ontology.validation import validate_edge_endpoints, validate_properties
from ports.graph import GraphPort
from schemas.domain import (
    NOT_SAME_AS,
    SAME_AS,
    AuditStub,
    Edge,
    EdgeTypeDef,
    EdgeWrite,
    Handling,
    Interval,
    OntologySchema,
    Principal,
    Provenance,
    ProvenanceState,
    SourceRef,
    effective_basis,
)

from .change_provenance import CHANGE_MARKER, without_link_ids
from .link_notes import LinkNotFoundError
from .link_types import LinkTypeService
from .working_set.models import DeltaReplaceEdge, DeltaReplaceEdgeSent
from .working_set.service import WorkingSetService

#: A reason is a sentence or two. Shown to the analyst as it is approached.
MAX_REASON_CHARS = 1000

#: How far back one history read follows a link's changes before it stops and says so.
MAX_HISTORY = 100
#: How many revisions the history walk may step over, hidden ones included: a bound on the walk,
#: not on what is shown, so that a cycle in the store ends it.
MAX_WALK = 10 * MAX_HISTORY

_RESOLUTION_TYPES = frozenset({SAME_AS, NOT_SAME_AS})

_BOOTSTRAP_SQL = """
CREATE TABLE IF NOT EXISTS link_changes (
    id TEXT PRIMARY KEY,
    investigation_id TEXT NOT NULL,
    edge_id TEXT NOT NULL,
    previous_edge_id TEXT NOT NULL,
    changed_by TEXT NOT NULL,
    changed_at TIMESTAMPTZ NOT NULL,
    reason TEXT NOT NULL,
    before JSONB NOT NULL,
    after JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS link_changes_edge_idx ON link_changes (investigation_id, edge_id);
"""


class InvalidChangeError(Exception):
    """The reason is missing or too long, or the change is one the ontology refuses (an unknown
    type, a type that does not join these two kinds of entity, a property the type does not
    declare). Carries a sentence the Glass shows as given."""


class ChangeNotMadeError(Exception):
    """The request would leave the link exactly as it is."""


class ResolutionLinkError(Exception):
    """`SAME_AS` / `NOT_SAME_AS` links are changed by confirming or splitting, not edited."""


class LoweringNeedsAuthorError(PermissionError):
    """ADR-102: lowering a link's handling is an Author's change, not an Editor's."""


class LoweringNotConfirmedError(Exception):
    """ADR-102: a lower handling is written only once the analyst has said, in so many words, that
    they mean to lower it (`confirm_lower`)."""


class LinkChange(BaseModel):
    """One recorded change. `before` and `after` hold the type, properties, validity period and
    times seen, as they were and as they became."""

    id: str
    investigation_id: str
    edge_id: str  # the link this change produced
    previous_edge_id: str  # the link it replaced
    changed_by: str
    changed_at: datetime
    reason: str
    before: dict[str, Any]
    after: dict[str, Any]


class LinkChangeRequest(BaseModel):
    """What to change. A field left out is left alone; `interval` is the one a caller can set to
    `None` on purpose (to clear the validity period), told apart from "left out" by
    `model_fields_set`. `reason` is required."""

    model_config = ConfigDict(extra="forbid")

    reason: str
    type: str | None = None
    properties: dict[str, Any] | None = None
    interval: Interval | None = None
    occurrences: int | None = None
    #: What stands behind the link (ADR-081). Left out, the link keeps what stood behind it.
    basis: Literal["direct", "probabilistic"] | None = None
    #: ADR-102: the link's handling. Left out, it is kept. Raising it is an ordinary change;
    #: lowering any part of it needs an Author and `confirm_lower`.
    handling: Handling | None = None
    #: The analyst's own confirmation that a lower handling is meant (ADR-102).
    confirm_lower: bool = False


class LinkChangeResult(BaseModel):
    """What `LinkChangeService.change` returns to its caller: the stored form of the delta, which
    carries the record of the old link and is what the route publishes. It is not a response model;
    the route answers with `to_response()` (ADR-124 decision 4)."""

    edge: Edge
    delta: DeltaReplaceEdge
    change: LinkChange

    def to_response(self, reader: Principal) -> LinkChangeResponse:
        """What the analyst who made the change is sent: the new link and its step with their
        sources only where `reader`'s case reads every dataset of the link (ADR-130 Amendment 2)."""
        return LinkChangeResponse(
            edge=withhold_sources(self.edge, reader),
            delta=self.delta.to_sent(reader),
            change=self.change,
        )


class LinkChangeResponse(BaseModel):
    """What `POST .../links/{edge}/change` answers: the new link, the step in its sent form (no
    record of the old link), and the change."""

    edge: Edge
    delta: DeltaReplaceEdgeSent
    change: LinkChange


class LinkHistoryResponse(BaseModel):
    changes: list[LinkChange]
    #: `True` when the history was cut at `MAX_HISTORY` steps — said, never silently shortened.
    truncated: bool = False


class _Rekey(Protocol):
    """The one thing the change needs of the notes store: move a link's notes to its replacement."""

    async def rekey(self, investigation_id: str, old_edge_id: str, new_edge_id: str) -> int: ...


class LinkChangeStorage(Protocol):
    async def add(self, change: LinkChange) -> None: ...

    async def produced(self, investigation_id: str, edge_id: str) -> LinkChange | None:
        """The change that produced this link, or `None` for a link nobody has changed."""
        ...


def _row(row: asyncpg.Record) -> LinkChange:
    import json

    def _json(value: Any) -> dict[str, Any]:
        return value if isinstance(value, dict) else json.loads(value)

    return LinkChange(
        id=row["id"],
        investigation_id=row["investigation_id"],
        edge_id=row["edge_id"],
        previous_edge_id=row["previous_edge_id"],
        changed_by=row["changed_by"],
        changed_at=row["changed_at"],
        reason=row["reason"],
        before=_json(row["before"]),
        after=_json(row["after"]),
    )


class LinkChangeStore:
    """Postgres. Append-only by use: nothing here updates or deletes a row."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    @classmethod
    async def connect(cls, dsn: str) -> LinkChangeStore:
        pool = await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=5)
        async with pool.acquire() as conn:
            await conn.execute(_BOOTSTRAP_SQL)
        return cls(pool)

    async def close(self) -> None:
        await self._pool.close()

    async def add(self, change: LinkChange) -> None:
        import json

        async with self._pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO link_changes (id, investigation_id, edge_id, previous_edge_id, "
                "changed_by, changed_at, reason, before, after) "
                "VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb, $9::jsonb)",
                change.id,
                change.investigation_id,
                change.edge_id,
                change.previous_edge_id,
                change.changed_by,
                change.changed_at,
                change.reason,
                json.dumps(change.before),
                json.dumps(change.after),
            )

    async def produced(self, investigation_id: str, edge_id: str) -> LinkChange | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM link_changes WHERE investigation_id = $1 AND edge_id = $2",
                investigation_id,
                edge_id,
            )
        return _row(row) if row else None


def _snapshot(edge: Edge, type_def: EdgeTypeDef | None) -> dict[str, Any]:
    return {
        "type": edge.type,
        "properties": dict(edge.properties),
        "interval": edge.interval.model_dump(mode="json") if edge.interval else None,
        "occurrences": edge.occurrences,
        "basis": effective_basis(edge.basis, type_def, written_at=edge.audit.created_at),
        "handling": edge.handling.model_dump(mode="json"),
    }


class LinkChangeService:
    def __init__(
        self,
        store: LinkChangeStorage,
        working_set: WorkingSetService,
        graph: GraphPort,
        ontology: OntologySchema,
        notes: _Rekey,
        types: LinkTypeService | None = None,
        *,
        scheme: HandlingScheme | None = None,
    ) -> None:
        self._scheme = scheme
        self._store = store
        self._working_set = working_set
        self._graph = graph
        self._ontology = ontology
        self._notes = notes
        self._types = types

    def _type_of(self, name: str) -> EdgeTypeDef | None:
        """The type an existing link reads as, offered in the case or not (ADR-090)."""
        if self._types is not None:
            found = self._types.type_named(name)
            return found.definition if found is not None else None
        return self._ontology.edge_type(name)

    async def _wanted_type(
        self, investigation_id: str, principal: Principal, name: str, old_type: str
    ) -> tuple[EdgeTypeDef, str] | None:
        """The type a link is changed to and the label it is written under: one the case is
        offered (a pending proposal's own label, ADR-090 Amendment 1), or the type it already
        has."""
        if self._types is None:
            found = self._ontology.edge_type(name)
            return (found, name) if found is not None else None
        entry = (await self._types.case_types(investigation_id, principal)).get(name)
        if entry is None and name == old_type:
            entry = self._types.type_named(name)
        return (entry.definition, entry.storage_name) if entry is not None else None

    async def _visible(self, investigation_id: str, edge_id: str, principal: Principal) -> Edge:
        edge = await self._working_set.visible_edge(investigation_id, edge_id, principal)
        if edge is None:
            raise LinkNotFoundError(edge_id)
        return edge

    async def _in_full(self, investigation_id: str, edge_id: str, principal: Principal) -> Edge:
        """The link as it is to be changed: `_visible`, with its sources in full (ADR-130
        Amendment 2, "a read that is written back"). The change is written from this record, and a
        withheld list would replace the stored sources with none. Still judged for `principal`, so
        a link they may not read answers as one that does not exist. A body the working set stored
        withheld (it reads the Vault with the case's principal) is read again from the Vault."""
        with sources_in_full():
            edge = await self._visible(investigation_id, edge_id, principal)
            if not edge.provenance.sources_withheld:
                return edge
            found = await self._graph.get_edges([edge_id], principal)
        held = found[0] if found else None
        if held is None or held.provenance.sources_withheld:
            raise LinkNotFoundError(edge_id)
        return edge.model_copy(update={"provenance": held.provenance})

    async def change(
        self,
        investigation_id: str,
        edge_id: str,
        principal: Principal,
        request: LinkChangeRequest,
        *,
        is_author: bool = False,
    ) -> LinkChangeResult:
        old = await self._in_full(investigation_id, edge_id, principal)
        reason = request.reason.strip()
        if not reason:
            raise InvalidChangeError("Say why the link is being changed: a reason is required.")
        if len(reason) > MAX_REASON_CHARS:
            raise InvalidChangeError(f"A reason can be at most {MAX_REASON_CHARS} characters.")
        if old.type in _RESOLUTION_TYPES or request.type in _RESOLUTION_TYPES:
            raise ResolutionLinkError(
                "Same-as links are confirmed or marked as not the same, not edited."
            )

        new_type = request.type if request.type is not None else old.type
        new_properties = request.properties if request.properties is not None else old.properties
        new_interval = request.interval if "interval" in request.model_fields_set else old.interval
        new_occurrences = (
            request.occurrences if request.occurrences is not None else old.occurrences
        )
        if new_occurrences < 1:
            raise InvalidChangeError("occurrences must be at least 1.")

        wanted_type = await self._wanted_type(investigation_id, principal, new_type, old.type)
        if wanted_type is None:
            raise InvalidChangeError(f"{new_type!r} is not a link type offered in this case.")
        type_def, write_type = wanted_type
        old_def = self._type_of(old.type)
        ends = await self._working_set.end_types(investigation_id, old)
        if ends is None:
            raise LinkNotFoundError(edge_id)
        try:
            validate_edge_endpoints(type_def, source_type=ends[0], target_type=ends[1])
            validate_properties(type_def, dict(new_properties))
        except OntologyError as exc:
            raise InvalidChangeError(str(exc)) from exc

        # What stands behind the link (ADR-081 step B). Asked for or kept, it is never Direct
        # over anything probabilistic: not over a Probabilistic type, and not over a link that
        # was already probabilistic, because a person never promotes a link to Direct.
        old_basis = effective_basis(old.basis, old_def, written_at=old.audit.created_at)
        # Kept rather than asked for, a basis follows the new type where that type is probabilistic.
        kept = "probabilistic" if type_def.basis == "probabilistic" else old_basis
        wanted = request.basis if request.basis is not None else kept
        if wanted == "direct":
            if type_def.basis == "probabilistic":
                raise InvalidChangeError(
                    f"A link of type {new_type} is probabilistic and cannot be marked Direct."
                )
            if old_basis == "probabilistic":
                raise InvalidChangeError(
                    "A probabilistic link is never returned to Direct: Direct means a loaded "
                    "record stands behind it."
                )
        # Stored only where it says something the type does not: a mark on a Direct type.
        new_basis: Literal["direct", "probabilistic"] | None = (
            "probabilistic" if wanted == "probabilistic" and type_def.basis == "direct" else None
        )

        new_handling = self._wanted_handling(old.handling, request, principal, is_author)

        candidate = old.model_copy(
            update={
                "handling": new_handling,
                "type": new_type,
                "properties": dict(new_properties),
                "interval": new_interval,
                "occurrences": new_occurrences,
                "basis": new_basis,
            }
        )
        if _snapshot(candidate, type_def) == _snapshot(old, old_def):
            raise ChangeNotMadeError("Nothing about the link would change.")

        now = datetime.now(UTC)
        replacement_id = new_edge_id()
        provenance = Provenance(
            state=ProvenanceState.ASSERTED,
            # The old link's document sources, and this change recorded with no id: nothing here
            # names the old link, whatever an earlier revision wrote (ADR-124 decision 11).
            sources=[
                *without_link_ids(old.provenance.sources),
                SourceRef(document_id=CHANGE_MARKER, locator=principal.id, excerpt_hash=""),
            ],
            first_seen=old.provenance.first_seen,
        )
        write = EdgeWrite(
            id=replacement_id,
            type=write_type,
            source=old.source,
            target=old.target,
            properties=dict(new_properties),
            interval=new_interval,
            occurrences=new_occurrences,
            basis=new_basis,
            provenance=provenance,
            handling=new_handling,
            created_by=principal.id,
            created_at=now,
        )

        tx = await self._graph.begin_transaction()
        try:
            await self._graph.supersede_edge(old.id, write, tx)
        except Exception:
            await self._graph.rollback_transaction(tx)
            raise
        await self._graph.commit_transaction(tx)

        new = old.model_copy(
            update={
                "handling": new_handling,
                "id": replacement_id,
                "type": new_type,
                "properties": dict(new_properties),
                "interval": new_interval,
                "occurrences": new_occurrences,
                "basis": new_basis,
                "provenance": provenance,
                "audit": AuditStub(
                    created_at=now, created_by=principal.id, revision=old.audit.revision + 1
                ),
            }
        )
        delta = await self._working_set.replace_edge(investigation_id, old, new)
        change = LinkChange(
            id=new_id(),
            investigation_id=investigation_id,
            edge_id=replacement_id,
            previous_edge_id=old.id,
            changed_by=principal.id,
            changed_at=now,
            reason=reason,
            before=_snapshot(old, old_def),
            after=_snapshot(new, type_def),
        )
        await self._store.add(change)
        await self._notes.rekey(investigation_id, old.id, replacement_id)
        return LinkChangeResult(edge=new, delta=delta, change=change)

    def _wanted_handling(
        self, old: Handling, request: LinkChangeRequest, principal: Principal, is_author: bool
    ) -> Handling:
        """ADR-102 decision 4. Left out, the handling is kept. A handling asked for must be in the
        scheme, keep the link's units (a change does not move it to another unit), and be one the
        analyst can see. Lower in any part than the link's (what `merge_handling` would raise
        back), it is an Author's change and needs `confirm_lower`; refused, nothing is written."""
        wanted = request.handling
        if wanted is None:
            return old
        if self._scheme is None:
            raise InvalidChangeError("This deployment does not change a link's handling here.")
        if (wanted.owning_unit, wanted.originator) != (old.owning_unit, old.originator):
            raise InvalidChangeError(
                "A link's owning unit and originator are not changed here, only its marking."
            )
        try:
            lower = merge_handling(wanted, old, self._scheme) != wanted
        except HandlingSchemeError as exc:
            raise InvalidChangeError(str(exc)) from exc
        if not principal_may_view(wanted, principal, self._scheme):
            raise InvalidChangeError(
                "A link cannot be marked above your own clearance or handling: you could not see "
                "it afterwards."
            )
        if lower and not is_author:
            raise LoweringNeedsAuthorError("Lowering a link's handling needs Author access.")
        if lower and not request.confirm_lower:
            raise LoweringNotConfirmedError(
                "This lowers the link's handling: confirm it to go ahead."
            )
        return wanted

    def _side_readable(self, side: dict[str, Any], principal: Principal) -> bool:
        """Whether `principal` may view the handling a revision recorded on one side (`before` or
        `after`), by handling alone: the store does not record datasets, and link history is reached
        only from a link in the reader's own case. A side with no scheme to judge it by, no
        recorded handling, or one the scheme no longer defines, is not readable."""
        if self._scheme is None:
            return False
        recorded = side.get("handling")
        if not isinstance(recorded, dict):
            return False
        try:
            return principal_may_view(Handling(**recorded), principal, self._scheme)
        except (HandlingSchemeError, ValueError):
            return False

    def _readable(self, change: LinkChange, principal: Principal) -> bool:
        return self._side_readable(change.before, principal) and self._side_readable(
            change.after, principal
        )

    async def history(
        self, investigation_id: str, edge_id: str, principal: Principal
    ) -> LinkHistoryResponse:
        """Every change that led to this link that the reader may view, newest first (ADR-124
        decision 11). A revision whose `before` or `after` the reader may not view is left out
        whole, and the walk goes on past it, so the response is exactly the response for a history
        without that revision: no placeholder, no gap, and a `truncated` flag that counts only what
        the reader may see. The cap bounds what is shown; the walk itself is bounded by
        `MAX_WALK`, so a cycle in the store ends it."""
        await self._visible(investigation_id, edge_id, principal)
        changes: list[LinkChange] = []
        current = edge_id
        for _ in range(MAX_WALK):
            produced = await self._store.produced(investigation_id, current)
            if produced is None:
                return LinkHistoryResponse(changes=changes)
            current = produced.previous_edge_id
            if not self._readable(produced, principal):
                continue
            if len(changes) == MAX_HISTORY:
                return LinkHistoryResponse(changes=changes, truncated=True)
            changes.append(produced)
        return LinkHistoryResponse(changes=changes, truncated=True)
