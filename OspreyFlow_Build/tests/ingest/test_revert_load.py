"""ADR-127 decision 6 and Amendments 5 and 6 (B2-4c1): reverting a load from its record.

`services/ingest/load_revert.py`'s `revert` takes a load id and does, for a load it may revert, what
decision 6 lists: it marks the load's created nodes and links reverted by the ids its record lists
(never by the `load_id` stored on an element, which a merge rewrites), retracts its events and its
geometry points, discards the held rows still pending, closes the alert rows of the alerts it
reverted, and marks the ledger record reverted with who did it and when. What a mistake would do,
and the case that catches it:

- a revert that also takes back another load's data: it refuses a load that merged into a link or
  node it did not create, one that wrote through an extract or enrich stage, one whose events carry
  no `load_id`, and one already reverted (`test_each_refusal_is_named_and_changes_nothing`), and a
  refused revert changes nothing (`test_a_refused_revert_changes_nothing`);
- a refusal that tells the operator something they may not read: its words name the reason and a
  count, never an id (`test_a_refusals_words_name_no_id`);
- a release of held rows left standing after its load is reverted, or reverted out of order
  (`test_a_release_is_reverted_before_the_load_it_was_released_from_newest_first`), and one release
  refusing leaving the rest to a half-done revert
  (`test_a_release_that_refuses_refuses_the_whole_revert`);
- a pipeline run's id reverting one branch, or a branch id reverting its siblings, or `run1`
  matching `run10`
  (`test_a_pipeline_runs_id_means_every_branch_and_a_branch_id_that_branch`);
- a step that fails leaving a revert nothing can finish: the ledger is marked last, every step is
  idempotent, and a rerun completes (`test_a_rerun_after_a_failure_at_any_step_completes`);
- the revert and rerun of a load holding content leaving the rerun's Document hidden or recorded as
  merged (`test_the_resets_revert_then_rerun_leaves_the_documents_readable_and_created`);
- a reverted load's events still in a trend or a cross-filter
  (`test_a_reverted_loads_events_are_gone_from_every_read`)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from services.ingest.load_ledger import load_record_from_report
from services.ingest.load_revert import (
    RevertDeps,
    RevertIncomplete,
    RevertRefused,
    revert,
)

from adapters.analytics_duckdb.testing import duckdb_adapter
from adapters.media_objectstore.testing import InMemoryMediaStore
from ontology.handling import load_uk_le_scheme
from ontology.loader import load_default_ontology
from ports.graph import StoredNode
from schemas.domain import Principal
from schemas.ingest import LoadRecord
from tests.conformance.analytics_port.test_suite import (
    CLEARED,
    LOAD_A,
    OFFICIAL,
    _a_and_b_and_unattributed,
    _everything_a_reader_can_ask,
)
from tests.ingest.recipe_test_support import (  # noqa: F401 (the autouse fixture)
    MergingGraph,
    local_staging,
)

ONTOLOGY = load_default_ontology()
SCHEME = load_uk_le_scheme()
T0 = datetime(2026, 10, 25, 9, 0, tzinfo=UTC)
NOW = T0 + timedelta(hours=3)
OPERATOR = "operator-1"
LOADER = Principal(id="loader-1", clearance="SECRET", org_unit="unit-1")


def _record(load_id: str, **fields: Any) -> LoadRecord:
    base: dict[str, Any] = {
        "load_id": load_id,
        "recipe_id": "recipe-1",
        "recipe_version": 1,
        "source": "pid.csv",
        "started_at": T0,
        "completed_at": T0,
        "created_by": "loader-1",
        "investigation_id": "case-1",
        "created_node_ids": [f"{load_id}-n1", f"{load_id}-n2"],
        "created_edge_ids": [f"{load_id}-e1"],
        "touched_edge_ids": [f"{load_id}-e1"],
        "created_geometry_refs": [f"{load_id}-geo"],
        "events_stamped": True,
    }
    return LoadRecord(**{**base, **fields})


class Ledger:
    """The ledger as `RecipeRunStore` answers it (proved live in `test_recipe_runs.py`): a record by
    its id, the records whose id starts with `<run>:`, the records released from a load, and the
    record marked reverted. Marking an id it holds no record of is an error, as an `UPDATE` that
    matched no row would be taken for one."""

    def __init__(self, *records: LoadRecord) -> None:
        self.records = {r.load_id: r for r in records}
        self.marked: list[tuple[str, str, datetime]] = []

    async def load_record(self, load_id: str) -> LoadRecord | None:
        return self.records.get(load_id)

    async def records_with_prefix(self, prefix: str) -> list[LoadRecord]:
        return [r for i, r in self.records.items() if i.startswith(prefix)]

    async def releases_of(self, load_id: str) -> list[LoadRecord]:
        return [r for r in self.records.values() if r.released_from == load_id]

    async def records_merging(self, node_ids: Any, edge_ids: Any) -> list[LoadRecord]:
        """The unreverted records that list one of these ids as merged into."""
        nodes, links = set(node_ids), set(edge_ids)
        return [
            r
            for r in self.records.values()
            if r.reverted_at is None
            and (nodes & set(r.merged_node_ids) or links & set(r.merged_edge_ids))
        ]

    async def mark_reverted(self, load_id: str, *, reverted_by: str, at: datetime) -> None:
        if load_id not in self.records:
            raise KeyError(load_id)
        self.marked.append((load_id, reverted_by, at))
        self.records[load_id] = self.records[load_id].model_copy(
            update={"reverted_at": at, "reverted_by": reverted_by}
        )


class Steps:
    """Every call a revert makes, in order, and a way to make one fail once."""

    def __init__(self) -> None:
        self.log: list[tuple[str, ...]] = []
        self.fail_at: str | None = None

    def hit(self, step: str, *detail: str) -> None:
        if self.fail_at == step:
            self.fail_at = None
            raise RuntimeError(f"{step} failed")
        self.log.append((step, *detail))

    def of(self, step: str) -> list[tuple[str, ...]]:
        return [entry for entry in self.log if entry[0] == step]


class Graph:
    """The graph port's revert, recording each call; idempotent, as setting the flag is. And the
    three internal lookups the revert asks, answered whatever a reader may read: the live links by
    their two ends (`live`), the live nodes naming each point (`named`), and the load each node was
    last written by (`load_ids`, absent for a node nothing says) and whether it is reverted."""

    def __init__(self, steps: Steps) -> None:
        self.steps = steps
        self.reverted: set[str] = set()
        self.live: dict[str, tuple[str, str]] = {}
        self.named: dict[str, set[str]] = {}
        self.load_ids: dict[str, str | None] = {}

    async def begin_transaction(self) -> str:
        return "tx"

    async def commit_transaction(self, tx: str) -> None:
        return None

    async def rollback_transaction(self, tx: str) -> None:
        return None

    async def revert_elements(self, node_ids: Any, edge_ids: Any, tx: str) -> None:
        self.steps.hit("graph", ",".join(node_ids), ",".join(edge_ids))
        self.reverted.update(node_ids)
        self.reverted.update(edge_ids)

    async def live_edges_touching(self, node_ids: Any) -> set[str]:
        wanted = set(node_ids)
        return {
            e
            for e, (source, target) in self.live.items()
            if e not in self.reverted and (source in wanted or target in wanted)
        }

    async def live_nodes_naming_geometry(self, refs: Any) -> dict[str, set[str]]:
        return {
            r: {n for n in nodes if n not in self.reverted}
            for r, nodes in self.named.items()
            if r in set(refs) and {n for n in nodes if n not in self.reverted}
        }

    async def stored_writes(self, node_ids: Any) -> dict[str, StoredNode]:
        return {
            n: StoredNode(load_id=self.load_ids[n], reverted=n in self.reverted)
            for n in node_ids
            if n in self.load_ids
        }


class Analytics:
    def __init__(self, steps: Steps) -> None:
        self.steps = steps
        self.events: dict[str, int] = {}
        self.geometries: set[tuple[str, int]] = set()

    async def retract_load(self, load_id: str) -> int:
        self.steps.hit("events", load_id)
        return self.events.pop(load_id, 0)

    async def retract_geometries(self, refs: Any, *, version: int) -> int:
        self.steps.hit("geometries", ",".join(refs), str(version))
        gone = {(r, version) for r in refs} & self.geometries
        self.geometries -= gone
        return len(gone)


class Held:
    def __init__(self, steps: Steps) -> None:
        self.steps = steps
        self.pending: dict[str, int] = {}

    async def discard_for_load(self, load_id: str, *, discarded_by: str, at: datetime) -> int:
        self.steps.hit("held", load_id, discarded_by)
        return self.pending.pop(load_id, 0)


class Alerts:
    def __init__(self, steps: Steps) -> None:
        self.steps = steps
        self.open: dict[str, str] = {}  # alert node id -> status

    async def close_for_elements(
        self,
        node_ids: Any,
        edge_ids: Any,
        *,
        closed_by: str,
        at: datetime,
        reason: str,
    ) -> int:
        self.steps.hit("alerts", ",".join(node_ids), ",".join(edge_ids), closed_by)
        closed = [n for n in node_ids if self.open.get(n) == "open"]
        for node in closed:
            self.open[node] = "closed"
        return len(closed)


class Audit:
    def __init__(self, steps: Steps) -> None:
        self.steps = steps
        self.entries: list[dict[str, Any]] = []

    async def record(
        self,
        *,
        principal: Principal,
        action: str,
        resolved_query: dict[str, Any],
        result_cardinality: int,
        investigation_id: str | None = None,
        justification: str | None = None,
    ) -> None:
        self.steps.hit("audit", resolved_query["load_id"])
        self.entries.append(
            {
                "principal": principal.id,
                "action": action,
                "query": resolved_query,
                "cardinality": result_cardinality,
                "case": investigation_id,
            }
        )


class World:
    def __init__(self, *records: LoadRecord) -> None:
        self.steps = Steps()
        self.ledger = Ledger(*records)
        self.graph = Graph(self.steps)
        self.analytics = Analytics(self.steps)
        self.held = Held(self.steps)
        self.alerts = Alerts(self.steps)
        self.audit = Audit(self.steps)
        self.row_keys: list[str] = []

        async def release_row_keys(record: LoadRecord) -> None:
            self.steps.hit("row_keys", record.load_id)
            self.row_keys.append(record.load_id)

        self.deps = RevertDeps(
            ledger=self.ledger,
            graph=self.graph,  # type: ignore[arg-type]
            analytics=self.analytics,  # type: ignore[arg-type]
            held_rows=self.held,
            alerts=self.alerts,
            audit=self.audit,
            release_row_keys=release_row_keys,
        )

    async def revert(self, load_id: str):  # type: ignore[no-untyped-def]
        return await revert(load_id, reverted_by=OPERATOR, deps=self.deps, now=NOW)


async def test_a_load_is_reverted_by_the_ids_its_record_lists_and_nothing_else() -> None:
    world = World(_record("load-1", touched_edge_ids=["load-1-e1", "someone-elses-edge"]))
    result = await world.revert("load-1")
    ((_, nodes, links),) = world.steps.of("graph")
    assert nodes == "load-1-n1,load-1-n2" and links == "load-1-e1"
    assert "someone-elses-edge" not in links
    assert [s.load_id for s in result.reverted] == ["load-1"]
    assert (result.reverted[0].nodes, result.reverted[0].links) == (2, 1)


async def test_a_revert_does_every_step_and_marks_the_ledger_last() -> None:
    record = _record("load-1", created_node_ids=["a1", "n2"], created_geometry_refs=["g1", "g2"])
    world = World(record)
    world.analytics.events["load-1"] = 7
    world.analytics.geometries = {("g1", 1), ("g2", 1), ("g-other", 1), ("g1", 2)}
    world.held.pending["load-1"] = 3
    world.alerts.open = {"a1": "open", "unrelated": "open"}
    result = await world.revert("load-1")

    assert [s[0] for s in world.steps.log] == [
        "graph", "events", "geometries", "held", "alerts", "row_keys", "audit",
    ]  # fmt: skip
    summary = result.reverted[0]
    assert (summary.events, summary.geometries, summary.held_rows, summary.alerts) == (7, 2, 3, 1)
    assert world.analytics.geometries == {("g-other", 1), ("g1", 2)}, "this version's refs only"
    assert world.alerts.open == {"a1": "closed", "unrelated": "open"}
    ((_, alert_nodes, alert_links, _),) = world.steps.of("alerts")
    assert (alert_nodes, alert_links) == ("a1,n2", "load-1-e1"), "its created nodes and links both"
    assert world.ledger.marked == [("load-1", OPERATOR, NOW)]
    (entry,) = world.audit.entries
    assert (entry["principal"], entry["action"], entry["case"]) == (
        OPERATOR, "load_reverted", "case-1",
    )  # fmt: skip
    assert entry["query"]["load_id"] == "load-1"
    assert entry["cardinality"] == 3  # two nodes and a link


async def test_the_audit_entry_names_no_element_id() -> None:
    """The audit trail is read by more people than may read the elements."""
    world = World(_record("load-1"))
    await world.revert("load-1")
    text = repr(world.audit.entries)
    for element in ("load-1-n1", "load-1-n2", "load-1-e1", "load-1-geo"):
        assert element not in text


_REFUSALS: list[tuple[str, dict[str, Any], str]] = [
    ("events_not_stamped", {"events_stamped": False}, "events_not_stamped"),
    ("merged_nodes", {"merged_node_ids": ["old-doc"]}, "merged_nodes"),
    ("merged_links", {"merged_edge_ids": ["old-link"]}, "merged_links"),
    ("uncovered_writes", {"uncovered_writes": True}, "uncovered_writes"),
    ("already_reverted", {"reverted_at": T0, "reverted_by": "someone"}, "already_reverted"),
]


@pytest.mark.parametrize(("name", "fields", "reason"), _REFUSALS, ids=[r[0] for r in _REFUSALS])
async def test_each_refusal_is_named_and_changes_nothing(
    name: str, fields: dict[str, Any], reason: str
) -> None:
    world = World(_record("load-1", **fields))
    with pytest.raises(RevertRefused) as raised:
        await world.revert("load-1")
    assert [r.reason for r in raised.value.refusals] == [reason]
    assert raised.value.refusals[0].load_id == "load-1"
    assert world.steps.log == [] and world.ledger.marked == [] and world.audit.entries == []


async def test_a_load_with_no_record_is_refused() -> None:
    world = World(_record("load-1"))
    with pytest.raises(RevertRefused) as raised:
        await world.revert("never-recorded")
    assert [r.reason for r in raised.value.refusals] == ["no_record"]
    assert world.steps.log == []


async def test_a_refused_revert_changes_nothing() -> None:
    """With a cascade and several records, one refusal anywhere leaves every store untouched."""
    parent = _record("load-1")
    ok_release = _record("rel-1", released_from="load-1", started_at=T0 + timedelta(minutes=5))
    bad_release = _record(
        "rel-2", released_from="load-1", started_at=T0 + timedelta(minutes=9), merged_edge_ids=["x"]
    )
    world = World(parent, ok_release, bad_release)
    with pytest.raises(RevertRefused) as raised:
        await world.revert("load-1")
    assert [(r.load_id, r.reason) for r in raised.value.refusals] == [("rel-2", "merged_links")]
    assert world.steps.log == [] and world.ledger.marked == [] and world.audit.entries == []
    assert world.graph.reverted == set()


async def test_a_refusals_words_name_no_id() -> None:
    """Rule 3: the ids of what a load merged into are held on the refusal for the operator who asks
    for them, and no sentence it gives names one; an id of a link someone may not read would
    otherwise be told to whoever ran the revert."""
    world = World(
        _record("load-1", merged_edge_ids=["secret-link"], merged_node_ids=["secret-doc"])
    )
    with pytest.raises(RevertRefused) as raised:
        await world.revert("load-1")
    text = str(raised.value) + " ".join(r.words() for r in raised.value.refusals)
    assert "secret-link" not in text and "secret-doc" not in text
    assert "1" in text  # the count is said
    by_reason = {r.reason: r for r in raised.value.refusals}
    assert by_reason["merged_links"].ids == ("secret-link",)
    assert by_reason["merged_nodes"].ids == ("secret-doc",)


async def test_a_release_is_reverted_before_the_load_it_was_released_from_newest_first() -> None:
    parent = _record("load-1")
    first = _record("rel-1", released_from="load-1", started_at=T0 + timedelta(minutes=5))
    second = _record("rel-2", released_from="load-1", started_at=T0 + timedelta(minutes=9))
    of_a_release = _record("rel-3", released_from="rel-1", started_at=T0 + timedelta(minutes=7))
    already = _record(
        "rel-0", released_from="load-1", started_at=T0 + timedelta(minutes=1),
        reverted_at=T0, reverted_by="earlier",
    )  # fmt: skip
    unrelated = _record("other", started_at=T0 + timedelta(minutes=2))
    world = World(parent, first, second, of_a_release, already, unrelated)
    result = await world.revert("load-1")
    assert [s.load_id for s in result.reverted] == ["rel-2", "rel-3", "rel-1", "load-1"]
    assert [m[0] for m in world.ledger.marked] == ["rel-2", "rel-3", "rel-1", "load-1"]
    assert {m[1] for m in world.ledger.marked} == {OPERATOR}, "the same reverted_by on each"
    assert [e["query"]["load_id"] for e in world.audit.entries] == [
        "rel-2",
        "rel-3",
        "rel-1",
        "load-1",
    ]
    assert world.ledger.records["other"].reverted_at is None, "a load that is no release stays"
    assert result.already_reverted == ["rel-0"], "an earlier revert's release is named, not redone"


async def test_a_release_that_refuses_refuses_the_whole_revert() -> None:
    parent = _record("load-1")
    release = _record("rel-1", released_from="load-1", uncovered_writes=True)
    world = World(parent, release)
    with pytest.raises(RevertRefused) as raised:
        await world.revert("load-1")
    assert [(r.load_id, r.reason) for r in raised.value.refusals] == [("rel-1", "uncovered_writes")]
    assert world.steps.log == []


async def test_a_pipeline_runs_id_means_every_branch_and_a_branch_id_that_branch() -> None:
    branches = [
        _record("run1:src-a", started_at=T0),
        _record("run1:src-b", started_at=T0 + timedelta(minutes=1)),
        _record("run10:src-a", started_at=T0 + timedelta(minutes=2)),
    ]
    one = World(*branches)
    result = await one.revert("run1:src-a")
    assert [s.load_id for s in result.reverted] == ["run1:src-a"]
    assert one.ledger.records["run1:src-b"].reverted_at is None

    every = World(*branches)
    result = await every.revert("run1")
    assert sorted(s.load_id for s in result.reverted) == ["run1:src-a", "run1:src-b"]
    assert every.ledger.records["run10:src-a"].reverted_at is None, "run1 is not run10"


async def test_a_pipeline_run_with_one_refusing_branch_is_refused_whole() -> None:
    world = World(_record("run1:a"), _record("run1:b", merged_edge_ids=["x"]))
    with pytest.raises(RevertRefused) as raised:
        await world.revert("run1")
    assert [(r.load_id, r.reason) for r in raised.value.refusals] == [("run1:b", "merged_links")]
    assert world.steps.log == []


async def test_a_pipeline_runs_branches_done_by_an_earlier_attempt_are_skipped_not_refused() -> (
    None
):
    done = _record("run1:a", reverted_at=T0, reverted_by=OPERATOR)
    world = World(done, _record("run1:b"))
    result = await world.revert("run1")
    assert [s.load_id for s in result.reverted] == ["run1:b"]
    assert result.already_reverted == ["run1:a"]
    # But a pipeline whose every branch is done is a refusal, as a single load already reverted is.
    finished = World(done, _record("run1:b", reverted_at=T0, reverted_by=OPERATOR))
    with pytest.raises(RevertRefused) as raised:
        await finished.revert("run1")
    assert {r.reason for r in raised.value.refusals} == {"already_reverted"}


_STEPS = ["graph", "events", "geometries", "held", "alerts", "row_keys", "audit"]


@pytest.mark.parametrize("failing", [*_STEPS, "mark"])
async def test_a_rerun_after_a_failure_at_any_step_completes(failing: str) -> None:
    release = _record("rel-1", released_from="load-1", started_at=T0 + timedelta(minutes=5))
    world = World(_record("load-1", created_node_ids=["a1", "n2"]), release)
    world.analytics.events.update({"load-1": 4, "rel-1": 2})
    world.analytics.geometries = {("load-1-geo", 1), ("rel-1-geo", 1)}
    world.held.pending.update({"load-1": 2})
    world.alerts.open = {"a1": "open"}

    if failing == "mark":
        real = world.ledger.mark_reverted

        async def failing_mark(load_id: str, *, reverted_by: str, at: datetime) -> None:
            if load_id == "load-1":
                world.ledger.mark_reverted = real  # type: ignore[method-assign]
                raise RuntimeError("mark failed")
            await real(load_id, reverted_by=reverted_by, at=at)

        world.ledger.mark_reverted = failing_mark  # type: ignore[method-assign]
    else:
        # The release is done before the load starts; the failure is the load's own step.
        original_hit = world.steps.hit
        calls = {"n": 0}

        def hit(step: str, *detail: str) -> None:
            if step == failing:
                calls["n"] += 1
                if calls["n"] == 2:  # the second revert (the load) hits it, not the release
                    raise RuntimeError(f"{step} failed")
            original_hit(step, *detail)

        world.steps.hit = hit  # type: ignore[method-assign]

    with pytest.raises(RevertIncomplete) as raised:
        await world.revert("load-1")
    incomplete = raised.value
    assert incomplete.failed_load_id == "load-1"
    assert incomplete.failed_step == failing
    assert [s.load_id for s in incomplete.done] == ["rel-1"], "the release was finished and marked"
    assert world.ledger.records["rel-1"].reverted_at == NOW
    assert world.ledger.records["load-1"].reverted_at is None, "never marked until all is done"
    assert "load-1" in str(incomplete) and failing in str(incomplete)

    again = await world.revert("load-1")  # the rerun
    assert [s.load_id for s in again.reverted] == ["load-1"], "the finished release is not redone"
    assert again.already_reverted == ["rel-1"]
    assert world.ledger.records["load-1"].reverted_at == NOW
    assert world.analytics.events == {} and world.analytics.geometries == set()
    assert world.held.pending == {} and world.alerts.open == {"a1": "closed"}
    assert {"load-1-e1", "a1", "n2"} <= world.graph.reverted


async def test_a_failure_in_the_graph_step_rolls_the_transaction_back_and_marks_nothing() -> None:
    world = World(_record("load-1"))
    world.steps.fail_at = "graph"
    rolled: list[str] = []

    async def rollback(tx: str) -> None:
        rolled.append(tx)

    world.graph.rollback_transaction = rollback  # type: ignore[method-assign]
    with pytest.raises(RevertIncomplete) as raised:
        await world.revert("load-1")
    assert rolled == ["tx"] and raised.value.failed_step == "graph"
    assert world.ledger.marked == [] and world.graph.reverted == set()
    assert raised.value.done == []


async def test_the_row_key_hook_is_called_after_the_stores_and_before_the_ledger_is_marked() -> (
    None
):
    """B2-5 (decision 5) supplies it; until then the call site is a hook that does nothing."""
    world = World(_record("load-1"))
    await world.revert("load-1")
    assert world.row_keys == ["load-1"]
    steps = [s[0] for s in world.steps.log]
    assert steps.index("row_keys") > steps.index("alerts")
    bare = World(_record("load-1"))
    bare.deps = RevertDeps(
        ledger=bare.ledger, graph=bare.graph, analytics=bare.analytics,  # type: ignore[arg-type]
        held_rows=bare.held, alerts=bare.alerts, audit=bare.audit,
    )  # fmt: skip
    await revert("load-1", reverted_by=OPERATOR, deps=bare.deps, now=NOW)
    assert bare.ledger.records["load-1"].reverted_by == OPERATOR


# --- against the stand-ins that model what the stores do ----------------------------------------


def _content_recipe() -> Any:
    from tests.ingest.test_load_record_created_and_merged import _recipe

    return _recipe(content=True)


async def test_the_resets_revert_then_rerun_leaves_the_documents_readable_and_created() -> None:
    """The demo reset reverts a chapter's load and runs it again. The load wrote a content
    `Document` under `content:<sha>`; reverting it hides the Document, and the rerun writes the same
    id. The rerun must leave it live (the write replaces the reverted node) and record it as
    created (`existing_node_ids` leaves a reverted node out), or its own revert would skip it."""
    from services.api.studio_publish import load_with_rules

    graph = MergingGraph(ONTOLOGY)

    async def load(load_id: str, day: int) -> LoadRecord:
        report, _events, _held = await load_with_rules(
            _content_recipe(),
            [{"payer": "SYN-1", "payee": "SYN-2", "paid_at": f"2026-03-0{day}T09:00:00+00:00",
              "memo": "a note"}],
            LOADER,
            graph=graph,  # type: ignore[arg-type]
            ontology=ONTOLOGY,
            load_id=load_id,
            investigation_scope="case-1",
            source="private_cash.csv",
            media=InMemoryMediaStore(),
            rules=None,
            scheme=SCHEME,
        )  # fmt: skip
        assert report.rejections == []
        return load_record_from_report(
            report, source="private_cash.csv", created_by="loader-1", started_at=T0, now=T0,
            investigation_id="case-1",
        )  # fmt: skip

    first = await load("load-1", 1)
    (document,) = [n.id for n in graph.committed_nodes if n.type == "Document"]
    assert document in first.created_node_ids

    world = World(first)
    world.deps = RevertDeps(
        ledger=world.ledger, graph=graph,  # type: ignore[arg-type]
        analytics=world.analytics,  # type: ignore[arg-type]
        held_rows=world.held, alerts=world.alerts, audit=world.audit,
    )  # fmt: skip
    await revert("load-1", reverted_by=OPERATOR, deps=world.deps, now=NOW)
    assert document in graph.reverted and document not in graph.live_nodes

    second = await load("load-2", 2)
    assert document in second.created_node_ids and document not in second.merged_node_ids
    assert document in graph.live_nodes, "the rerun's Document is readable"
    assert second.merged_edge_ids == [], (
        "its links are new ones, the reverted ones were not merged into"
    )
    # So the rerun can be reverted in its turn: nothing in it merged into the first load's data.
    world.ledger.records["load-2"] = second
    await revert("load-2", reverted_by=OPERATOR, deps=world.deps, now=NOW)
    assert document in graph.reverted


async def test_a_reverted_loads_events_are_gone_from_every_read() -> None:
    """Against the real DuckDB adapter: after the revert every read, for every reader, equals a
    store that never held the load's events (Amendment 5), `trend` and `cross_filter` included."""
    events = _a_and_b_and_unattributed()
    survivors = [e for e in events if e.load_id != LOAD_A]
    readers = [OFFICIAL, CLEARED]
    async with duckdb_adapter(events, SCHEME) as adapter:
        before = {p.id: await _everything_a_reader_can_ask(adapter, p) for p in readers}
        steps = Steps()
        deps = RevertDeps(
            ledger=Ledger(_record(LOAD_A)),
            graph=Graph(steps),  # type: ignore[arg-type]
            analytics=adapter,
            held_rows=Held(steps),
            alerts=Alerts(steps),
            audit=Audit(steps),
        )
        await revert(LOAD_A, reverted_by=OPERATOR, deps=deps, now=NOW)
        after = {p.id: await _everything_a_reader_can_ask(adapter, p) for p in readers}
    async with duckdb_adapter(survivors, SCHEME) as never:
        expected = {p.id: await _everything_a_reader_can_ask(never, p) for p in readers}
    assert after == expected
    assert before != after, "the load's events were there to be removed"
    assert "trend" in after[CLEARED.id] and "cross_filter" in after[CLEARED.id]


# --- ADR-127 Amendment 6, B2-4c round 3: what a revert must not take from later loads -----------


async def test_a_later_load_that_merged_into_this_loads_link_makes_the_revert_refuse() -> None:
    later = _record("load-2", merged_edge_ids=["load-1-e1"], started_at=T0 + timedelta(hours=1))
    world = World(_record("load-1"), later)
    with pytest.raises(RevertRefused) as raised:
        await world.revert("load-1")
    (refusal,) = raised.value.refusals
    assert (refusal.load_id, refusal.reason, refusal.count) == (
        "load-1", "merged_into_by_later_load", 1,
    )  # fmt: skip
    assert "load-1-e1" not in str(raised.value), "a count, never an id"
    assert world.steps.log == [] and world.ledger.marked == []


async def test_a_later_load_that_merged_into_this_loads_node_makes_the_revert_refuse() -> None:
    later = _record("load-2", merged_node_ids=["load-1-n2"], started_at=T0 + timedelta(hours=1))
    world = World(_record("load-1"), later)
    with pytest.raises(RevertRefused) as raised:
        await world.revert("load-1")
    assert [r.reason for r in raised.value.refusals] == ["merged_into_by_later_load"]
    assert "load-1-n2" not in str(raised.value)
    assert world.steps.log == []


async def test_a_later_load_that_was_itself_reverted_does_not_stand_in_the_way() -> None:
    later = _record("load-2", merged_edge_ids=["load-1-e1"], reverted_at=T0, reverted_by="someone")
    world = World(_record("load-1"), later)
    result = await world.revert("load-1")
    assert [s.load_id for s in result.reverted] == ["load-1"]


async def test_a_live_link_outside_the_load_resting_on_a_node_it_created_makes_the_revert_refuse() -> (
    None
):
    """A later load only referenced the node, which its record keeps as a count: it has a link of
    its own to the node, which reverting the node would leave hanging."""
    world = World(_record("load-1"))
    world.graph.live = {"later-link": ("somewhere-else", "load-1-n1"), "load-1-e1": ("a", "b")}
    with pytest.raises(RevertRefused) as raised:
        await world.revert("load-1")
    (refusal,) = raised.value.refusals
    assert (refusal.reason, refusal.count) == ("rests_on_by_live_links", 1)
    assert "later-link" not in str(raised.value) and "load-1-n1" not in str(raised.value)
    assert world.steps.log == [] and world.ledger.marked == []


async def test_both_refusals_are_named_together_and_nothing_is_changed() -> None:
    later = _record("load-2", merged_edge_ids=["load-1-e1"], started_at=T0 + timedelta(hours=1))
    world = World(_record("load-1"), later)
    world.graph.live = {"later-link": ("x", "load-1-n2")}
    with pytest.raises(RevertRefused) as raised:
        await world.revert("load-1")
    assert {r.reason for r in raised.value.refusals} == {
        "merged_into_by_later_load",
        "rests_on_by_live_links",
    }
    assert world.steps.log == [] and world.graph.reverted == set()


async def test_the_loads_own_links_do_not_count_as_resting_on_it() -> None:
    world = World(_record("load-1"))
    world.graph.live = {"load-1-e1": ("load-1-n1", "load-1-n2")}  # the load's own created link
    result = await world.revert("load-1")
    assert [s.load_id for s in result.reverted] == ["load-1"]


async def test_a_release_that_merged_into_its_parents_link_does_not_block_the_cascade() -> None:
    """Judged within the plan: the release's merge is into an element the plan is reverting too."""
    parent = _record("load-1")
    release = _record(
        "rel-1", released_from="load-1", started_at=T0 + timedelta(minutes=5),
        merged_edge_ids=["load-1-e1"], merged_node_ids=["load-1-n1"],
    )  # fmt: skip
    world = World(parent, release)
    result = await world.revert("load-1")
    assert [s.load_id for s in result.reverted] == ["rel-1", "load-1"]


async def test_a_release_merging_into_something_outside_the_plan_still_refuses() -> None:
    parent = _record("load-1")
    release = _record(
        "rel-1", released_from="load-1", started_at=T0 + timedelta(minutes=5),
        merged_edge_ids=["load-1-e1", "someone-elses"],
    )  # fmt: skip
    world = World(parent, release)
    with pytest.raises(RevertRefused) as raised:
        await world.revert("load-1")
    ((refusal),) = raised.value.refusals
    assert (refusal.load_id, refusal.reason, refusal.count) == ("rel-1", "merged_links", 1)
    assert refusal.ids == ("someone-elses",)


async def test_a_point_a_live_node_outside_the_plan_still_names_is_kept() -> None:
    world = World(_record("load-1", created_geometry_refs=["g-shared", "g-own", "g-plan"]))
    world.analytics.geometries = {("g-shared", 1), ("g-own", 1), ("g-plan", 1)}
    world.graph.named = {
        "g-shared": {"a-later-location"},
        "g-own": {"load-1-n1"},
        "g-plan": {"load-1-n2", "a-later-location"},
    }
    result = await world.revert("load-1")
    ((_, refs, version),) = world.steps.of("geometries")
    assert refs == "g-own" and version == "1"
    assert world.analytics.geometries == {("g-shared", 1), ("g-plan", 1)}
    assert (result.reverted[0].geometries, result.reverted[0].geometries_kept) == (1, 2)


async def test_a_point_named_by_a_node_of_another_record_in_the_plan_is_removed() -> None:
    """The release is reverted first, while its parent's node (in the same plan) is still live and
    names the point. That node is going too, so it is no reason to keep the point."""
    parent = _record("load-1")
    release = _record(
        "rel-1", released_from="load-1", started_at=T0 + timedelta(minutes=5),
        created_geometry_refs=["g-1"],
    )  # fmt: skip
    world = World(parent, release)
    world.analytics.geometries = {("g-1", 1)}
    world.graph.named = {"g-1": {"load-1-n1"}}
    await world.revert("load-1")
    assert world.analytics.geometries == set()


async def test_a_release_that_merged_into_its_parents_content_node_does_not_leave_it_behind() -> (
    None
):
    """The release's write onto the parent's content `Document` rewrote its stored load to the
    release's. The release does not revert it (it merged), so the parent must, though the node's
    stored load is not the parent's: it is one of the plan's own."""
    parent = _record("load-1")
    release = _record(
        "rel-1", released_from="load-1", started_at=T0 + timedelta(minutes=5),
        merged_node_ids=["load-1-n1"],
    )  # fmt: skip
    world = World(parent, release)
    world.graph.load_ids = {"load-1-n1": "rel-1", "load-1-n2": "load-1"}
    result = await world.revert("load-1")
    assert [s.load_id for s in result.reverted] == ["rel-1", "load-1"]
    assert {"load-1-n1", "load-1-n2"} <= world.graph.reverted, "no live Document left behind"
    assert result.reverted[1].nodes_left_alone == 0


async def test_a_standalone_upload_that_merged_into_a_plan_node_is_refused_on_the_first_attempt() -> (
    None
):
    """A Files-tab upload (or any writer with no load) merged into a content `Document` the plan
    created and rewrote its stored load to none. Neither a later record nor a live link shows it;
    the revert would take the upload back, so it is refused, by count, and nothing is changed."""
    world = World(_record("load-1"))
    world.graph.load_ids = {"load-1-n1": "load-1", "load-1-n2": None}
    with pytest.raises(RevertRefused) as raised:
        await world.revert("load-1")
    (refusal,) = raised.value.refusals
    assert (refusal.load_id, refusal.reason, refusal.count) == (
        "load-1", "rewritten_by_another_writer", 1,
    )  # fmt: skip
    assert "load-1-n2" not in str(raised.value), "a count, never an id"
    assert world.steps.log == [] and world.graph.reverted == set() and world.ledger.marked == []


async def test_a_node_another_load_wrote_is_refused_on_the_first_attempt_too() -> None:
    world = World(_record("load-1"))
    world.graph.load_ids = {"load-1-n1": "load-1", "load-1-n2": "load-9"}
    with pytest.raises(RevertRefused) as raised:
        await world.revert("load-1")
    assert [r.reason for r in raised.value.refusals] == ["rewritten_by_another_writer"]
    assert world.steps.log == []


async def test_on_a_rerun_a_node_a_later_load_wrote_again_is_left_and_named_in_the_result() -> None:
    """Some of the plan's nodes are already reverted, so an earlier attempt passed the graph step:
    this is a rerun, and a node whose stored load is not the plan's was written again since."""
    world = World(_record("load-1"))
    world.graph.reverted = {"load-1-n1"}  # the earlier attempt's work
    world.graph.load_ids = {"load-1-n1": "load-1", "load-1-n2": "load-2"}
    result = await world.revert("load-1")
    ((_, nodes, _),) = world.steps.of("graph")
    assert nodes == "load-1-n1", "only a node that is still this plan's"
    summary = result.reverted[0]
    assert (summary.nodes, summary.nodes_left_alone) == (1, 1)
    assert summary.left_alone_node_ids == ("load-1-n2",)
    assert "load-1-n2" not in world.graph.reverted
    ((_, alert_nodes, _, _),) = world.steps.of("alerts")
    assert alert_nodes == "load-1-n1", "no alert is closed for a node that was left"


async def test_on_a_rerun_a_node_with_no_stored_load_is_left_not_taken_back() -> None:
    world = World(_record("load-1"))
    world.graph.reverted = {"load-1-n1"}
    world.graph.load_ids = {"load-1-n1": "load-1", "load-1-n2": None}
    result = await world.revert("load-1")
    assert result.reverted[0].left_alone_node_ids == ("load-1-n2",)
    assert "load-1-n2" not in world.graph.reverted


async def test_a_rerun_after_the_release_was_finished_still_reverts_the_node_it_rewrote() -> None:
    """The first attempt reverted and marked the release and failed in the parent. The release is
    no longer in the plan, but a node it rewrote is still the plan's family: its id counts."""
    parent = _record("load-1")
    release = _record(
        "rel-1", released_from="load-1", started_at=T0 + timedelta(minutes=5),
        merged_node_ids=["load-1-n1"], reverted_at=T0, reverted_by=OPERATOR,
    )  # fmt: skip
    world = World(parent, release)
    world.graph.load_ids = {"load-1-n1": "rel-1", "load-1-n2": "load-1"}
    result = await world.revert("load-1")
    assert [s.load_id for s in result.reverted] == ["load-1"]
    assert {"load-1-n1", "load-1-n2"} <= world.graph.reverted


async def test_the_rerun_window_a_node_rewritten_between_the_attempts_is_not_taken_back() -> None:
    """The first attempt fails after the graph step. Before the rerun the reset runs the load
    again, and its write onto the reverted node rewrote it (a fresh create stamps its own load). The
    rerun reverts the rest and leaves that node, and the revert still completes."""
    world = World(_record("load-1"))
    world.graph.load_ids = {"load-1-n1": "load-1", "load-1-n2": "load-1"}
    world.steps.fail_at = "events"
    with pytest.raises(RevertIncomplete):
        await world.revert("load-1")
    world.graph.reverted.discard("load-1-n1")  # the rerun of the load made it live again...
    world.graph.load_ids["load-1-n1"] = "load-9"  # ...under its own load
    again = await world.revert("load-1")
    assert again.reverted[0].left_alone_node_ids == ("load-1-n1",)
    assert "load-1-n1" not in world.graph.reverted and "load-1-n2" in world.graph.reverted
    assert world.ledger.records["load-1"].reverted_at == NOW
