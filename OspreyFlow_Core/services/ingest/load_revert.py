"""Reverting a load from its record (`06_DECISIONS.md` ADR-127 decision 6 and Amendments 5 and 6).

`revert` is the logic behind `python -m scripts.revert_load <load_id> --reverted-by <principal id>`,
kept apart from the script so it is tested without a command line or a store.

**What it reads.** The load's `LoadRecord`, in the run ledger, and nothing on the stored elements:
a merge rewrites an existing element's `load_id` to the merging load's, so the stored `load_id` does
not say what a load created. A pipeline run's id has no record of its own and means every branch,
found by the `<run>:` prefix; a branch's id means that branch alone.

**What it refuses, before changing anything.** A load with no record; a record without
`events_stamped` (its events cannot be retracted, and a revert that removed none would leave them
moving every trend); one with `merged_node_ids` or `merged_edge_ids` (reverting those would take
back another load's data, and a merged link's occurrences cannot be split); one marked
`uncovered_writes`; one already reverted; one whose created node or link an analyst's correction
has superseded (the successor is in no record and would keep the load's data; one superseded and
already reverted is out of every read and not judged). Three more guard what lies outside the
revert: **a later load merged into** a node or link the revert would take back (an unreverted
record elsewhere lists it as merged), **a live link outside the revert touches** a node it created
(a later load only referenced the node, which its record keeps as a count), and, on a first
attempt, **a created node was written again by another writer** (its stored load is not one of the
plan's own: a load outside it, or none, as for a Files-tab upload). A merge or a touch by a record
in the same plan is no reason: that element is being reverted too. Every record to be reverted is
judged first, so a refusal anywhere, a release included, leaves every store as it was.

**What a refusal says (rule 3).** Its words name the reason, the load and a count, never an id. The
ids of what a load merged into are held on the `Refusal` for an operator who asks to see them,
because a link's id told to someone who may not read that link says it exists. Whoever calls
`revert` and shows a refusal to anyone else uses `words()`.

**The cascade.** Before the load itself, every unreverted release of its held rows (a ledger run of
its own whose record names `released_from` = the load, and releases of those in turn) is reverted,
newest first, with the same `reverted_by`. A release that was reverted already is named in
`already_reverted` and not done again.

**What one revert does, in this order:**

1. the graph: the record's created nodes and links marked reverted, by id
   (`GraphPort.revert_elements`), in one transaction. A node is reverted when its stored load is one
   of the plan's own (a release's merge into a parent's node included); on a rerun, after an earlier
   attempt reverted some node, one whose stored load is not (a later load's fresh create over the
   reverted node, an upload's merge) is left and named in the result;
2. the working sets: the nodes and links just reverted (and the links at those nodes) removed from
   every case that holds them, whoever may read them, each case sent a removal that every connected
   reader's projection reduces to what that reader may read, the stored history scrubbed
   (`WorkingSetRemoval`, `services/api/working_set_revert.py`; repeated as step 10);
3. its events removed (`AnalyticsPort.retract_load`), after the alerts that cite one of them are
   closed: asked of the ids the alerts name, never of the load's events (`events_of_load_among`);
4. its geometry points removed (`AnalyticsPort.retract_geometries`, at the version a load writes),
   except a point a live node outside the plan still names;
5. its held rows still pending discarded;
6. the alert queue rows closed of every alert that is one of the load's own (its `Alert` node is a
   created node) or that cites a node or a link the load created: the queue's read leaves out an
   alert citing a reverted node by itself, but not one citing only a reverted link;
7. the Conduit's kept results cleared (`invalidate_caches`: keys in the shared Valkey, so every
   instance at once), after everything that changes what they were counted over;
8. its row keys released (decision 5: `RevertLedger.release_row_keys`, by its load id), so a rerun
   of its rows loads them again;
9. the audit entry (counts only, no element id);
10. the working-set removal again (`working_sets_again`), last before the mark: a Conduit left
    running can add back an element it read before the graph step, and this finds only that;
11. the ledger record marked reverted, with `reverted_by` and the time.

**Failure and rerun.** Every step is idempotent (setting a flag again, removing what is already
gone, discarding rows no longer pending), and the ledger is marked last, so a load that failed part
way is not yet reverted as far as the ledger says. A step that fails raises
`RevertIncomplete`, which
names the load, the step, the loads already finished (each marked) and the cause; running the same
command again finishes it, skipping the releases already done. A duplicate audit entry from a rerun
after a failure at the mark is accepted: the trail says the operator ran it twice, which is true.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal, Protocol

from conduit_common.transactions import rollback_keeping_failure
from ports.analytics import AnalyticsPort
from ports.graph import GraphPort
from schemas.domain import Principal
from schemas.ingest import LoadRecord

from .geometries import POINT_GEOMETRY_VERSION

#: The audit action a revert records, one entry per load reverted.
LOAD_REVERTED_ACTION = "load_reverted"

RefusalReason = Literal[
    "no_record",
    "events_not_stamped",
    "merged_nodes",
    "merged_links",
    "uncovered_writes",
    "already_reverted",
    "merged_into_by_later_load",
    "rests_on_by_live_links",
    "rewritten_by_another_writer",
    "superseded_by_a_correction",
]


@dataclass(frozen=True)
class Refusal:
    """One reason a revert is refused, for one load. `ids` are the elements the reason concerns (the
    nodes or links a load merged into): for the operator who asks for them, never in `words()`."""

    load_id: str
    reason: RefusalReason
    count: int = 0
    ids: tuple[str, ...] = ()

    def words(self) -> str:
        what = {
            "no_record": "the ledger holds no record of it",
            "events_not_stamped": (
                "it was written before its events carried its id, so they cannot be removed"
            ),
            "merged_nodes": f"it wrote to {self.count} node(s) that already existed",
            "merged_links": f"it merged into {self.count} link(s) that already existed",
            "uncovered_writes": (
                "an extract or enrich stage fed by it wrote elements that no record covers"
            ),
            "already_reverted": "it was already reverted",
            "merged_into_by_later_load": (
                f"a later load merged into {self.count} element(s) it created; revert that "
                "load first"
            ),
            "rests_on_by_live_links": (
                f"{self.count} live link(s) outside it rest on nodes it created"
            ),
            "superseded_by_a_correction": (
                f"{self.count} node(s) or link(s) it created were replaced by an analyst's "
                "correction, whose replacement is in no record and would keep the load's data"
            ),
            "rewritten_by_another_writer": (
                f"{self.count} node(s) it created were written again by a load outside this "
                "revert or by an upload, which reverting them would take back"
            ),
        }[self.reason]
        return f"load {self.load_id!r} cannot be reverted: {what}"


class RevertRefused(Exception):
    """The revert was refused, and nothing was changed. `refusals` says why, per load."""

    def __init__(self, refusals: Sequence[Refusal]) -> None:
        self.refusals = list(refusals)
        super().__init__("; ".join(r.words() for r in self.refusals))


@dataclass(frozen=True)
class LoadReverted:
    """What reverting one load did, in counts."""

    load_id: str
    nodes: int
    links: int
    events: int
    geometries: int
    held_rows: int
    alerts: int
    #: Alerts closed because they cite an event the load wrote (retracted with it).
    alerts_citing_events: int = 0
    #: Cases whose working set held an element the revert took back, and so were sent a removal.
    cases: int = 0
    #: Points a live node outside the revert still names, which were left in the partition.
    geometries_kept: int = 0
    #: Nodes the load created that a later load wrote again (a fresh create over a reverted node
    #: stamps its own load), left as they are; their ids, for the operator who asks.
    nodes_left_alone: int = 0
    left_alone_node_ids: tuple[str, ...] = ()


@dataclass
class RevertResult:
    """Every load reverted by this call, in the order it was done (releases first), and the releases
    an earlier attempt had already reverted."""

    reverted: list[LoadReverted] = field(default_factory=list)
    already_reverted: list[str] = field(default_factory=list)


class RevertIncomplete(Exception):
    """A step failed. `done` are the loads finished (and marked) before it; `failed_load_id` is the
    one in hand, and `failed_step` the step that raised. Running the revert again completes it."""

    def __init__(
        self,
        *,
        done: Sequence[LoadReverted],
        failed_load_id: str,
        failed_step: str,
        cause: Exception,
    ) -> None:
        self.done = list(done)
        self.failed_load_id = failed_load_id
        self.failed_step = failed_step
        self.cause = cause
        finished = ", ".join(d.load_id for d in self.done) or "none"
        super().__init__(
            f"the revert of load {failed_load_id!r} stopped at its {failed_step} step "
            f"({type(cause).__name__}: {cause}); loads finished: {finished}. "
            "Run the same revert again to complete it."
        )


class RevertLedger(Protocol):
    """The run ledger, as `RecipeRunStore` answers it."""

    async def load_record(self, load_id: str) -> LoadRecord | None: ...

    async def records_with_prefix(self, prefix: str) -> list[LoadRecord]: ...

    async def releases_of(self, load_id: str) -> list[LoadRecord]: ...

    async def records_merging(
        self, node_ids: Sequence[str], edge_ids: Sequence[str]
    ) -> list[LoadRecord]:
        """The unreverted records that list one of these nodes or links as merged into."""
        ...

    async def release_row_keys(self, load_ids: Sequence[str]) -> int:
        """Releases the row keys these loads kept (ADR-127 decision 5), so a rerun of their rows
        loads them again. Idempotent: a second call releases none."""
        ...

    async def mark_reverted(self, load_id: str, *, reverted_by: str, at: datetime) -> None: ...


class HeldRowDiscard(Protocol):
    async def discard_for_load(self, load_id: str, *, discarded_by: str, at: datetime) -> int: ...


class AlertQueueClose(Protocol):
    async def close_for_elements(
        self,
        node_ids: Sequence[str],
        edge_ids: Sequence[str],
        *,
        closed_by: str,
        at: datetime,
        reason: str,
    ) -> int: ...

    async def alerts_citing_events(self) -> dict[str, list[str]]:
        """The alerts not yet closed that name events, by id, each with the event ids it names."""
        ...

    async def close_by_ids(
        self, alert_ids: Sequence[str], *, closed_by: str, at: datetime, reason: str
    ) -> int: ...


class WorkingSetRemoval(Protocol):
    """The working-set stores, as the revert reaches them from its own process
    (`services/api/working_set_revert.py`): the load's elements out of every case holding them, a
    removal published to each, the stored history scrubbed. Returns the cases that held any."""

    async def remove(
        self, node_ids: Sequence[str], edge_ids: Sequence[str], *, final_pass: bool = False
    ) -> int:
        """`final_pass` is the second run, last before the ledger mark: a Conduit left running can
        add back an element it read before the graph step, and this finds only that."""
        ...


class RevertAudit(Protocol):
    async def record(
        self,
        *,
        principal: Principal,
        action: str,
        resolved_query: dict[str, Any],
        result_cardinality: int,
        investigation_id: str | None = None,
        justification: str | None = None,
    ) -> None: ...


@dataclass
class RevertDeps:
    ledger: RevertLedger
    graph: GraphPort
    analytics: AnalyticsPort
    held_rows: HeldRowDiscard
    alerts: AlertQueueClose
    audit: RevertAudit
    working_sets: WorkingSetRemoval
    #: Clears every kept result the Conduit holds (`invalidate_every_cache` in
    #: `services/api/cache.py`): they are in the shared Valkey, so a process outside the Conduit
    #: clears them for all of it.
    invalidate_caches: Callable[[], Awaitable[None]]


def _is_reverted(record: LoadRecord) -> bool:
    return record.reverted_at is not None


def _newest_first(records: Sequence[LoadRecord]) -> list[LoadRecord]:
    return sorted(records, key=lambda r: (r.started_at, r.load_id), reverse=True)


def _refusals_for(
    record: LoadRecord, plan_nodes: frozenset[str], plan_links: frozenset[str]
) -> list[Refusal]:
    """Why `record` cannot be reverted. A merge into an element another record of the same plan
    created is no reason: that element is being reverted too (a release that merged into its
    parent's link, in the cascade)."""
    refusals: list[Refusal] = []
    if not record.events_stamped:
        refusals.append(Refusal(record.load_id, "events_not_stamped"))
    merged_nodes = tuple(n for n in record.merged_node_ids if n not in plan_nodes)
    if merged_nodes:
        refusals.append(Refusal(record.load_id, "merged_nodes", len(merged_nodes), merged_nodes))
    merged_links = tuple(e for e in record.merged_edge_ids if e not in plan_links)
    if merged_links:
        refusals.append(Refusal(record.load_id, "merged_links", len(merged_links), merged_links))
    if record.uncovered_writes:
        refusals.append(Refusal(record.load_id, "uncovered_writes"))
    return refusals


async def _targets(load_id: str, ledger: RevertLedger) -> list[LoadRecord]:
    """The records the id names: the load's own, or else every branch of a pipeline run."""
    exact = await ledger.load_record(load_id)
    if exact is not None:
        return [exact]
    branches = await ledger.records_with_prefix(f"{load_id}:")
    if not branches:
        raise RevertRefused([Refusal(load_id, "no_record")])
    return branches


async def _releases(
    record: LoadRecord, ledger: RevertLedger, seen: set[str]
) -> tuple[list[LoadRecord], list[str]]:
    """Every unreverted release of `record`'s held rows, and of those in turn; and the ones an
    earlier attempt reverted."""
    found: list[LoadRecord] = []
    already: list[str] = []
    for release in await ledger.releases_of(record.load_id):
        if release.load_id in seen:
            continue
        seen.add(release.load_id)
        if _is_reverted(release):
            already.append(release.load_id)
            continue
        found.append(release)
        deeper, deeper_already = await _releases(release, ledger, seen)
        found.extend(deeper)
        already.extend(deeper_already)
    return found, already


async def revert(
    load_id: str, *, reverted_by: str, deps: RevertDeps, now: datetime
) -> RevertResult:
    """Reverts `load_id` (a load, a branch, or a pipeline run), releases first. Raises
    `RevertRefused` having changed nothing, or `RevertIncomplete` having changed what it says."""
    targets = await _targets(load_id, deps.ledger)
    live = [t for t in targets if not _is_reverted(t)]
    result = RevertResult()
    if not live:
        raise RevertRefused([Refusal(t.load_id, "already_reverted") for t in targets])
    result.already_reverted.extend(t.load_id for t in targets if _is_reverted(t))

    seen = {t.load_id for t in targets}
    releases: list[LoadRecord] = []
    for target in live:
        found, already = await _releases(target, deps.ledger, seen)
        releases.extend(found)
        result.already_reverted.extend(already)
    plan = [*_newest_first(releases), *_newest_first(live)]

    plan_nodes = frozenset(n for record in plan for n in record.created_node_ids)
    plan_links = frozenset(e for record in plan for e in record.created_edge_ids)
    refusals = [
        refusal for record in plan for refusal in _refusals_for(record, plan_nodes, plan_links)
    ]
    # The loads that are this revert's own: every record in the plan, and the releases (or branches)
    # an earlier attempt already reverted, whose writes onto the plan's nodes are the plan's too.
    own_loads = frozenset({r.load_id for r in plan} | set(result.already_reverted))
    refusals.extend(await _later_refusals(load_id, plan, plan_nodes, plan_links, own_loads, deps))
    if refusals:
        raise RevertRefused(refusals)

    for record in plan:
        try:
            summary = await _revert_one(record, reverted_by, deps, now, plan_nodes, own_loads)
        except _StepFailed as failed:
            raise RevertIncomplete(
                done=result.reverted,
                failed_load_id=record.load_id,
                failed_step=failed.step,
                cause=failed.cause,
            ) from failed.cause
        result.reverted.append(summary)
    return result


async def _later_refusals(
    load_id: str,
    plan: Sequence[LoadRecord],
    plan_nodes: frozenset[str],
    plan_links: frozenset[str],
    own_loads: frozenset[str],
    deps: RevertDeps,
) -> list[Refusal]:
    """What the plan would take from loads outside it (ADR-127 Amendment 6), by count.

    - **A later load merged into what the plan created**: an unreverted record outside the plan
      lists one of the plan's created nodes or links as merged into. Reverting it would take back
      that load's data too (a link's occurrences cannot be split; a node it wrote to is its own).
    - **A live link outside the plan touches a node the plan created**: a later load only
      *referenced* the node, which its record keeps as a count, but its link to the node would be
      left hanging. Asked of the graph unfiltered, as the port says, and answered here as a count.
    - **A node the plan created was written again by someone else** (first attempt only): a merge
      rewrites a node's stored load, so a created node whose stored load is not one of the plan's
      own (a load outside it, or none: a Files-tab upload) has been written by another writer, and
      reverting it would take that back. Neither check above can see a standalone upload. On a
      rerun, when an earlier attempt has already reverted some created node, such a node is
      instead left alone and named (`_revert_one`): the earlier attempt passed the graph step, so
      what was written since is a later load's, not a merge the plan should have refused.
    """
    in_plan = {r.load_id for r in plan}
    merged_into: set[str] = set()
    for record in await deps.ledger.records_merging(sorted(plan_nodes), sorted(plan_links)):
        if record.load_id in in_plan:
            continue
        merged_into |= (set(record.merged_node_ids) & plan_nodes) | (
            set(record.merged_edge_ids) & plan_links
        )
    refusals: list[Refusal] = []
    if merged_into:
        refusals.append(Refusal(load_id, "merged_into_by_later_load", len(merged_into)))
    touching = await deps.graph.live_edges_touching(sorted(plan_nodes))
    resting = touching - plan_links
    if resting:
        refusals.append(Refusal(load_id, "rests_on_by_live_links", len(resting)))
    stored = await deps.graph.stored_writes(sorted(plan_nodes))
    # A node corrected, or a link changed, since the load wrote it: the successor is in no record,
    # so reverting the original would leave the load's data standing in its place. One superseded
    # and reverted already (Amendment 8) is out of every read and not the plan's to judge.
    link_states = await deps.graph.stored_link_states(sorted(plan_links))
    corrected = sum(1 for w in stored.values() if w.superseded and not w.reverted) + sum(
        1 for w in link_states.values() if w.superseded and not w.reverted
    )
    if corrected:
        refusals.append(Refusal(load_id, "superseded_by_a_correction", corrected))
    first_attempt = not any(w.reverted for w in stored.values())
    if first_attempt:
        rewritten = [n for n, w in stored.items() if w.load_id not in own_loads]
        if rewritten:
            refusals.append(Refusal(load_id, "rewritten_by_another_writer", len(rewritten)))
    return refusals


class _StepFailed(Exception):
    def __init__(self, step: str, cause: Exception) -> None:
        self.step = step
        self.cause = cause
        super().__init__(step)


async def _revert_one(
    record: LoadRecord,
    reverted_by: str,
    deps: RevertDeps,
    now: datetime,
    plan_nodes: frozenset[str],
    own_loads: frozenset[str],
) -> LoadReverted:
    counts = {
        "events": 0,
        "geometries": 0,
        "held_rows": 0,
        "alerts": 0,
        "geometries_kept": 0,
        "alerts_citing_events": 0,
        "cases": 0,
    }
    reverting_nodes = list(record.created_node_ids)
    left_alone: list[str] = []

    async def graph() -> None:
        # A created node is reverted only when its stored load is one of the plan's own: a merge by
        # a release in the plan rewrites it to the release's (still ours), but a write by anyone
        # else rewrites it to theirs. A first attempt with such a node was refused at planning;
        # what is left here is a rerun, after an earlier attempt reverted some node, so a node
        # written since (a fresh create over the reverted one stamps its own load, an upload none)
        # is left and named. A node the store does not hold is reverted as listed.
        stored = await deps.graph.stored_writes(record.created_node_ids)
        left_alone[:] = [
            n for n in record.created_node_ids if n in stored and stored[n].load_id not in own_loads
        ]
        reverting_nodes[:] = [n for n in record.created_node_ids if n not in left_alone]
        nodes, links = reverting_nodes, list(record.created_edge_ids)
        if not nodes and not links:
            return
        tx = await deps.graph.begin_transaction()
        try:
            await deps.graph.revert_elements(nodes, links, tx)
        except BaseException:
            await rollback_keeping_failure(deps.graph, tx)
            raise
        await deps.graph.commit_transaction(tx)

    async def working_sets() -> None:
        # The load's own elements, out of every case that holds them, whoever may read them: a
        # canvas keeps nothing the revert took back. Idempotent, so a rerun repeats it.
        counts["cases"] = await deps.working_sets.remove(
            reverting_nodes, list(record.created_edge_ids)
        )

    async def events() -> None:
        # An alert names the events it rests on, and a retracted event cannot be read, so an alert
        # citing one of this load's is closed first, asking only about the ids the alerts name (the
        # load's events can be millions). A failure in the retract leaves them closed, and the
        # rerun asks again while the events are still there.
        cited = await deps.alerts.alerts_citing_events()
        named = sorted({e for ids in cited.values() for e in ids})
        if named:
            mine = await deps.analytics.events_of_load_among(record.load_id, named)
            citing = sorted(a for a, ids in cited.items() if mine.intersection(ids))
            if citing:
                counts["alerts_citing_events"] = await deps.alerts.close_by_ids(
                    citing,
                    closed_by=reverted_by,
                    at=now,
                    reason=f"load {record.load_id} was reverted and its events removed",
                )
        counts["events"] = await deps.analytics.retract_load(record.load_id)

    async def geometries() -> None:
        # A point a live node outside the plan still names stays: a later load's `Location` may
        # name a ref this load inserted (the record lists it only because it was absent then).
        named = await deps.graph.live_nodes_naming_geometry(record.created_geometry_refs)
        shared = {ref for ref, nodes in named.items() if nodes - plan_nodes}
        removable = [r for r in record.created_geometry_refs if r not in shared]
        counts["geometries_kept"] = len(set(record.created_geometry_refs) & shared)
        counts["geometries"] = await deps.analytics.retract_geometries(
            removable, version=POINT_GEOMETRY_VERSION
        )

    async def held() -> None:
        counts["held_rows"] = await deps.held_rows.discard_for_load(
            record.load_id, discarded_by=reverted_by, at=now
        )

    async def alerts() -> None:
        counts["alerts"] = await deps.alerts.close_for_elements(
            reverting_nodes,
            record.created_edge_ids,
            closed_by=reverted_by,
            at=now,
            reason=f"load {record.load_id} was reverted",
        )

    async def working_sets_again() -> None:
        # The race a Conduit left running can run: an expand that read the graph before the graph
        # step adds an element back after the first removal. Cheap when clean (nothing is held).
        counts["cases"] += await deps.working_sets.remove(
            reverting_nodes, list(record.created_edge_ids), final_pass=True
        )

    async def caches() -> None:
        await deps.invalidate_caches()

    async def row_keys() -> None:
        # The keys this load kept for its case: by load id, idempotent (a rerun releases none).
        await deps.ledger.release_row_keys([record.load_id])

    async def audit() -> None:
        await deps.audit.record(
            principal=Principal(id=reverted_by, clearance="OFFICIAL", org_unit="operator"),
            action=LOAD_REVERTED_ACTION,
            resolved_query={
                "load_id": record.load_id,
                "recipe_id": record.recipe_id,
                "recipe_version": record.recipe_version,
                "released_from": record.released_from,
                "nodes": len(reverting_nodes),
                "links": len(record.created_edge_ids),
                "nodes_left_alone": len(left_alone),
                **counts,
            },
            result_cardinality=len(reverting_nodes) + len(record.created_edge_ids),
            investigation_id=record.investigation_id,
        )

    async def mark() -> None:
        await deps.ledger.mark_reverted(record.load_id, reverted_by=reverted_by, at=now)

    steps: list[tuple[str, Callable[[], Awaitable[None]]]] = [
        ("graph", graph),
        ("working_sets", working_sets),
        ("events", events),
        ("geometries", geometries),
        ("held", held),
        ("alerts", alerts),
        ("caches", caches),
        ("row_keys", row_keys),
        ("audit", audit),
        ("working_sets_again", working_sets_again),
        ("mark", mark),
    ]
    for name, run in steps:
        try:
            await run()
        except Exception as exc:
            raise _StepFailed(name, exc) from exc
    return LoadReverted(
        load_id=record.load_id,
        nodes=len(reverting_nodes),
        links=len(record.created_edge_ids),
        nodes_left_alone=len(left_alone),
        left_alone_node_ids=tuple(left_alone),
        **counts,
    )
