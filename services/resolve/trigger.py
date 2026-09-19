"""The corpus-wide resolution and alerting trigger — `06_DECISIONS.md` ADR-025. The real caller
`resolve_entity_type`/`write_same_as_edges`/`detect_conflicts`/`record_conflicts` never had:
every test in `tests/resolve/` calls them directly, and `07_BUILD_PLAN.md`'s Phase 6 gaps list
already discloses that nothing schedules or triggers a run against the live corpus.

**Population.** Paginates `GraphPort.list_nodes` (`06_DECISIONS.md` ADR-025, `01_DOMAIN_MODEL.md`
§8.2) to exhaustion — `next_cursor is None` is the only exhaustion signal this loop trusts, never
a short page (`ListNodesPage`'s own docstring). Restricted, per ADR-025's own "narrow, not
corpus-wide, on the first pass," to entity types the ontology actually declares a `resolution:`
block for (today, only `Person`) — the caller names one `entity_type` per job; a deployment with
several resolvable types submits one job per type, not one job that loops over all of them, so a
slow type never blocks a fast one and a failure in one is isolated.

**Principal.** ADR-025 proposes a deployment-level service principal, not the triggering analyst's
own — resolution is corpus-wide and cross-investigation. `service_principal` below is a deliberate,
disclosed scoping choice `docs/` does not settle: given `receivable_handling_codes`
(`01_DOMAIN_MODEL.md` §2.2) always compares the principal's own `org_unit` against a record's
`owning_unit`/`originator`, no single fixed `org_unit` can belong to every unit a corpus spans, so
a service principal with a *non-empty* `receivable_handling_codes` would need an org_unit that,
for at least some records, still fails the unit check — an inconsistent, partially-working
bypass, not a clean one. This module's service principal instead carries the scheme's highest
clearance and **no** receivable restricted codes at all: it resolves everything not marked
`dissemination: restricted`, and a restricted-handling-code `Person` record is — deliberately, and
disclosed here rather than silently — never corpus-wide-resolved by this trigger. A future
deployment that needs restricted records resolved too is a real, separate design question (per-unit
service identities, most plausibly), not assumed answered by this default.

**Overlap.** `resolve:running:{entity_type}` is a real Valkey lock (`valkey.asyncio.lock.Lock`),
held for the run's own duration and released on completion — not merely checked once before
submitting. This is deliberately stronger than ADR-025's own "checked before submitting, skipping a
redundant submission" wording: `write_same_as_edges` is safe under overlap (`GraphArcadeDBAdapter.
upsert_edges` already finds-and-merges by `(type, source, target)`, checked directly against the
adapter), but `record_conflicts`'s `GraphPort.supersede_edge` is not — it has no compare-and-swap
against a `NOT_SAME_AS` edge already superseded by a concurrent run, and closing that cheaply would
need a `GraphPort.get_edge` method that does not exist (Phase 6's own gaps list already declined to
add one for a related reason). Holding the lock for the run's duration, rather than only at
submission time, closes the common case without that new port method. **The residual gap, stated
precisely:** if a run genuinely outlives `LOCK_TTL_SECONDS` (no measurement of `resolve_entity_type`
at corpus scale exists anywhere in this repository — the only related figure,
`tests/resolve/test_projection_perf.py`'s 50,000-node/0.056s result, measures `compute_clusters`'
own reprojection path, a different operation bounded by a different cap, not this one), a second run
can still acquire the lock while the first is genuinely still writing, and the conflict-recording
race above is not closed for that residual window. `LOCK_TTL_SECONDS` is set conservatively long and
disclosed as a guess, not a measurement.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from valkey.asyncio import Valkey
from valkey.asyncio.lock import Lock
from valkey.exceptions import LockError

from ontology.handling import HandlingScheme
from ports.graph import GraphPort
from schemas.domain import (
    Edge,
    EntityTypeDef,
    ExpandRequest,
    Node,
    OntologySchema,
    Principal,
    TxId,
)

from .conflicts import detect_conflicts
from .resolver import resolve_entity_type
from .same_as_writer import record_conflicts, write_same_as_edges

JOB_TYPE_RESOLVE_ENTITY_TYPE = "resolve_entity_type"

#: A page well above what any interactive caller would ever ask for
#: (contrast the working set's own 500-node convenience default) — this
#: loop's only job is to reach `next_cursor is None`, and a bigger page
#: means fewer round trips for the same total population.
PAGE_SIZE = 2000

#: Conservative and disclosed as a guess, not a measurement — see this
#: module's own docstring for why no real figure exists to size this from.
LOCK_TTL_SECONDS = 2 * 60 * 60

_LOCK_KEY_PREFIX = "resolve:running:"

#: This trigger's own identity, attributed on every `SAME_AS`/conflict write
#: it makes — distinct from any analyst id, so "who resolved this" always
#: answers honestly.
SERVICE_PRINCIPAL_ID = "system:resolution-trigger"


def service_principal(scheme: HandlingScheme) -> Principal:
    """See this module's own docstring, "Principal," for the full reasoning
    behind the empty `receivable_handling_codes` — a deliberate, disclosed
    scoping choice, not an oversight."""
    return Principal(
        id=SERVICE_PRINCIPAL_ID,
        clearance=scheme.classification[-1],
        org_unit=SERVICE_PRINCIPAL_ID,
        receivable_handling_codes=[],
    )


@dataclass(frozen=True)
class ResolutionRunResult:
    skipped: bool
    reason: str | None = None
    nodes_processed: int = 0
    same_as_written: int = 0
    conflicts_recorded: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "skipped": self.skipped,
            "reason": self.reason,
            "nodes_processed": self.nodes_processed,
            "same_as_written": self.same_as_written,
            "conflicts_recorded": self.conflicts_recorded,
        }


async def _fetch_population(
    graph: GraphPort, entity_type_name: str, principal: Principal
) -> list[Node]:
    nodes: list[Node] = []
    cursor: str | None = None
    while True:
        page = await graph.list_nodes(
            entity_type_name, principal, cursor=cursor, limit=PAGE_SIZE
        )
        nodes.extend(page.nodes)
        if page.next_cursor is None:
            return nodes
        cursor = page.next_cursor


async def _fetch_not_same_as_edges(
    graph: GraphPort, node_ids: list[str], principal: Principal
) -> list[Edge]:
    if not node_ids:
        return []
    subgraph = await graph.expand(
        ExpandRequest(node_ids=node_ids, depth=1, edge_types=["NOT_SAME_AS"], direction="both"),
        principal,
    )
    return [e for e in subgraph.edges if e.type == "NOT_SAME_AS"]


async def run_resolution_for_entity_type(
    entity_type_name: str,
    *,
    graph: GraphPort,
    tx: TxId,
    ontology: OntologySchema,
    scheme: HandlingScheme,
) -> ResolutionRunResult:
    """The actual work, independent of the job-queue/worker plumbing —
    `run_resolve_entity_type_job` below is the thin adapter this presents
    to `JobWorker`'s fixed dispatch shape. Kept separate so a test (or the
    manual "resolve now" route, which has no job payload to unwrap) can
    call this directly."""
    entity_type: EntityTypeDef | None = ontology.entity_type(entity_type_name)
    if entity_type is None or entity_type.resolution is None:
        raise ValueError(
            f"{entity_type_name!r} has no resolution: block — this trigger only runs "
            "against a type the ontology declares one for"
        )

    principal = service_principal(scheme)
    nodes = await _fetch_population(graph, entity_type_name, principal)
    nodes_by_id = {n.id: n for n in nodes}

    candidates = resolve_entity_type(nodes, entity_type)

    # A candidate that conflicts with an existing manual split must never
    # also be written as SAME_AS — `01_DOMAIN_MODEL.md` §4: "a manual split
    # ... no future resolution run may override" — so conflicting and
    # mergeable candidates are disjoint sets, checked against the
    # established pattern (`tests/resolve/test_conflict_pipeline.py`,
    # `tests/scenarios/test_phase6_extraction_and_resolution.py`'s own
    # split clause), not assumed.
    not_same_as_edges = await _fetch_not_same_as_edges(graph, list(nodes_by_id), principal)
    conflicts = detect_conflicts(candidates, not_same_as_edges)
    conflicted_pairs = {frozenset((c.node_a, c.node_b)) for c in conflicts}
    mergeable_candidates = [
        c for c in candidates if frozenset((c.node_a, c.node_b)) not in conflicted_pairs
    ]

    same_as_ids = await write_same_as_edges(
        graph, mergeable_candidates, nodes_by_id, created_by=SERVICE_PRINCIPAL_ID, tx=tx,
        scheme=scheme,
    )
    not_same_as_by_id = {e.id: e for e in not_same_as_edges}
    conflict_ids = await record_conflicts(
        graph, conflicts, not_same_as_by_id, created_by=SERVICE_PRINCIPAL_ID, tx=tx
    )

    return ResolutionRunResult(
        skipped=False,
        nodes_processed=len(nodes),
        same_as_written=len(same_as_ids),
        conflicts_recorded=len(conflict_ids),
    )


async def try_run_resolution_with_overlap_guard(
    entity_type_name: str,
    *,
    graph: GraphPort,
    tx: TxId,
    ontology: OntologySchema,
    scheme: HandlingScheme,
    valkey: Valkey,
) -> ResolutionRunResult:
    """The overlap guard, wrapping `run_resolution_for_entity_type` — both
    the job handler below and the manual "resolve now" route go through
    this, never the unguarded function directly, so there is exactly one
    place the guard is applied rather than one caller reimplementing it."""
    lock: Lock = valkey.lock(
        f"{_LOCK_KEY_PREFIX}{entity_type_name}", timeout=LOCK_TTL_SECONDS, blocking=False
    )
    acquired = await lock.acquire()
    if not acquired:
        return ResolutionRunResult(skipped=True, reason="a resolution run is already in progress")
    try:
        return await run_resolution_for_entity_type(
            entity_type_name, graph=graph, tx=tx, ontology=ontology, scheme=scheme
        )
    finally:
        try:
            await lock.release()
        except LockError:
            # The lock's own TTL already expired and was reclaimed by
            # another run — the residual overlap window this module's own
            # docstring discloses, not a new failure to raise here.
            pass


async def run_resolve_entity_type_job(
    payload: dict[str, Any],
    *,
    graph: GraphPort,
    tx: TxId,
    ontology: OntologySchema,
    scheme: HandlingScheme,
    valkey: Valkey,
) -> dict[str, Any]:
    """`JobWorker`'s fixed dispatch shape is `(payload, *, graph, tx)` —
    `ontology`/`scheme`/`valkey` are bound at registration time
    (`functools.partial` or an equivalent closure over this deployment's
    loaded ontology, active handling scheme and Valkey client), not
    threaded through the queue payload, since all three are process-wide
    configuration, not per-job data. Goes through the overlap guard, not
    `run_resolution_for_entity_type` directly, so a job dispatched twice
    for the same entity type (the manual route racing the post-ingest
    hook, say) is exactly the case the guard exists for."""
    entity_type_name = str(payload["entity_type"])
    result = await try_run_resolution_with_overlap_guard(
        entity_type_name, graph=graph, tx=tx, ontology=ontology, scheme=scheme, valkey=valkey
    )
    return result.to_dict()
