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
from ontology.errors import OntologyError
from ontology.validation import validate_edge_endpoints, validate_properties
from ports.graph import GraphPort
from schemas.domain import (
    NOT_SAME_AS,
    SAME_AS,
    AuditStub,
    Edge,
    EdgeWrite,
    Interval,
    OntologySchema,
    Principal,
    Provenance,
    ProvenanceState,
    SourceRef,
    effective_basis,
)

from .link_notes import LinkNotFoundError
from .working_set.models import DeltaReplaceEdge
from .working_set.service import WorkingSetService

#: A reason is a sentence or two. Shown to the analyst as it is approached.
MAX_REASON_CHARS = 1000

#: How far back one history read follows a link's changes before it stops and says so.
MAX_HISTORY = 100

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


class LinkChangeResult(BaseModel):
    edge: Edge
    delta: DeltaReplaceEdge
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


def _snapshot(edge: Edge, ontology: OntologySchema) -> dict[str, Any]:
    return {
        "type": edge.type,
        "properties": dict(edge.properties),
        "interval": edge.interval.model_dump(mode="json") if edge.interval else None,
        "occurrences": edge.occurrences,
        "basis": effective_basis(edge.basis, ontology.edge_type(edge.type)),
    }


class LinkChangeService:
    def __init__(
        self,
        store: LinkChangeStorage,
        working_set: WorkingSetService,
        graph: GraphPort,
        ontology: OntologySchema,
        notes: _Rekey,
    ) -> None:
        self._store = store
        self._working_set = working_set
        self._graph = graph
        self._ontology = ontology
        self._notes = notes

    async def _visible(self, investigation_id: str, edge_id: str, principal: Principal) -> Edge:
        edge = await self._working_set.visible_edge(investigation_id, edge_id, principal)
        if edge is None:
            raise LinkNotFoundError(edge_id)
        return edge

    async def change(
        self,
        investigation_id: str,
        edge_id: str,
        principal: Principal,
        request: LinkChangeRequest,
    ) -> LinkChangeResult:
        old = await self._visible(investigation_id, edge_id, principal)
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

        type_def = self._ontology.edge_type(new_type)
        if type_def is None:
            raise InvalidChangeError(f"{new_type!r} is not a link type in this ontology.")
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
        old_basis = effective_basis(old.basis, self._ontology.edge_type(old.type))
        wanted = request.basis if request.basis is not None else old_basis
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

        candidate = old.model_copy(
            update={
                "type": new_type,
                "properties": dict(new_properties),
                "interval": new_interval,
                "occurrences": new_occurrences,
                "basis": new_basis,
            }
        )
        if _snapshot(candidate, self._ontology) == _snapshot(old, self._ontology):
            raise ChangeNotMadeError("Nothing about the link would change.")

        now = datetime.now(UTC)
        replacement_id = new_edge_id()
        provenance = Provenance(
            state=ProvenanceState.ASSERTED,
            sources=[
                *old.provenance.sources,
                SourceRef(
                    document_id=f"manual:change:{old.id}", locator=principal.id, excerpt_hash=""
                ),
            ],
            first_seen=old.provenance.first_seen,
        )
        write = EdgeWrite(
            id=replacement_id,
            type=new_type,
            source=old.source,
            target=old.target,
            properties=dict(new_properties),
            interval=new_interval,
            occurrences=new_occurrences,
            basis=new_basis,
            provenance=provenance,
            handling=old.handling,
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
        delta = await self._working_set.replace_edge(investigation_id, old.id, new)
        change = LinkChange(
            id=new_id(),
            investigation_id=investigation_id,
            edge_id=replacement_id,
            previous_edge_id=old.id,
            changed_by=principal.id,
            changed_at=now,
            reason=reason,
            before=_snapshot(old, self._ontology),
            after=_snapshot(new, self._ontology),
        )
        await self._store.add(change)
        await self._notes.rekey(investigation_id, old.id, replacement_id)
        return LinkChangeResult(edge=new, delta=delta, change=change)

    async def history(
        self, investigation_id: str, edge_id: str, principal: Principal
    ) -> LinkHistoryResponse:
        """Every change that led to this link, newest first."""
        await self._visible(investigation_id, edge_id, principal)
        changes: list[LinkChange] = []
        current = edge_id
        while len(changes) < MAX_HISTORY:
            produced = await self._store.produced(investigation_id, current)
            if produced is None:
                return LinkHistoryResponse(changes=changes)
            changes.append(produced)
            current = produced.previous_edge_id
        return LinkHistoryResponse(
            changes=changes,
            truncated=await self._store.produced(investigation_id, current) is not None,
        )
