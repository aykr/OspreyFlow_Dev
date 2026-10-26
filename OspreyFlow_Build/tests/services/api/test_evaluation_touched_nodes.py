"""ADR-127 decision 7(a), "no silent cut" (rule 2): `evaluate_hotlists_for_entry` read the first
`MAX_TOUCHED_NODES_PER_EVALUATION` (200) of an entry's node ids and silently dropped the rest, so a
hotlisted number past the two-hundredth node of a large load raised nothing. It now reads the ids in
chunks of that size until all are read. Pure: the stores, the lock and the graph are in-memory fakes
that each refuse what the real one refuses (a lock already held is not acquired; a graph hides a node
the principal may not read); the live proof against ArcadeDB, Postgres and Valkey is
`test_brief2_s7_hotlist_on_a_referenced_number.py`, and the lock and disclosure are
`test_evaluation.py`'s.

What a mistake would do, and the case that catches it:

- a node past the two-hundredth never looked at (`test_a_hotlisted_node_past_the_two_hundredth_alerts`);
- a chunk bigger than the cost cap (`test_the_graph_is_asked_for_chunks_of_the_cap_and_never_more`);
- a node of another dataset matching (`test_a_node_of_another_dataset_never_matches_whatever_its_place`);
- an alert disclosed through the matcher's own access, not the owner's (`record_match` is given the
  owner as `recipient`: `test_the_owner_is_the_recipient_never_the_matcher`);
- a monitor not waking for a run that only referenced nodes
  (`test_a_monitor_is_evaluated_for_a_run_that_only_referenced_nodes`).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, date, datetime
from types import SimpleNamespace
from typing import Any

import pytest
from services.api import evaluation
from services.api.change_stream import ChangeStreamEntry, touched_node_ids
from services.api.evaluation import (
    MAX_TOUCHED_NODES_PER_EVALUATION,
    evaluate_hotlists_for_entry,
    evaluate_monitors_for_entry,
)

from ontology.handling import load_uk_le_scheme
from schemas.domain import Hotlist, Monitor, PatternNode, PatternQuery, Principal, Subgraph
from schemas.ingest import LoadReport

SCHEME = load_uk_le_scheme()
OWNER = Principal(id="analyst-1", clearance="OFFICIAL", org_unit="unit-1")
HOT = "+447700900310"


class _Graph:
    """Holds `nodes` (id -> properties and datasets) and reads them as `get_nodes` does: only the
    ids it holds, each once, and none the principal's datasets exclude."""

    def __init__(self, nodes: dict[str, dict[str, Any]]) -> None:
        self.nodes = nodes
        self.chunks: list[int] = []
        self.principals: list[str] = []

    async def get_nodes(self, ids: Sequence[str], principal: Principal) -> list[Any]:
        self.chunks.append(len(ids))
        self.principals.append(principal.id)
        return [
            SimpleNamespace(
                id=i,
                properties=self.nodes[i]["properties"],
                datasets=self.nodes[i].get("datasets", []),
            )
            for i in sorted(set(ids))
            if i in self.nodes
        ]

    async def get_node(self, node_id: str, principal: Principal, **_: Any) -> Any:
        found = await self.get_nodes([node_id], principal)
        return found[0] if found else None

    async def match(self, definition: Any, principal: Principal) -> Subgraph:
        return Subgraph(nodes=[], edges=[])


class _Hotlists:
    def __init__(self, *hotlists: Hotlist) -> None:
        self.hotlists = list(hotlists)
        self.statuses: list[str] = []

    async def list_all_active(self) -> list[Hotlist]:
        return list(self.hotlists)

    async def set_status(self, hotlist_id: str, status: str) -> None:
        self.statuses.append(status)


class _Lock:
    async def acquire(self) -> bool:
        return True

    async def release(self) -> None:
        return None


class _Valkey:
    def lock(self, key: str, **_: Any) -> _Lock:
        return _Lock()

    async def get(self, key: str) -> None:
        return None

    async def set(self, key: str, value: str) -> None:
        return None


def _hotlist(identifier: str = HOT, dataset_id: str | None = None) -> Hotlist:
    return Hotlist(
        id="h1", identifier=identifier, owner_id=OWNER.id, review_date=date(2027, 1, 1),
        created_at=datetime(2026, 10, 26, tzinfo=UTC), dataset_id=dataset_id,
    )  # fmt: skip


def _entry(ids: list[str]) -> ChangeStreamEntry:
    return ChangeStreamEntry(
        entry_id="1-0", source="ingest", node_ids=ids, edge_ids=[],
        investigation_id="case-1", recorded_at=datetime(2026, 10, 26, tzinfo=UTC),
    )  # fmt: skip


@pytest.fixture
def recorded(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []

    async def record_match(**kwargs: Any) -> Any:
        calls.append(kwargs)
        return SimpleNamespace(id=f"alert-{len(calls)}")

    monkeypatch.setattr(evaluation, "record_match", record_match)
    return calls


async def _hotlists_for(
    graph: _Graph, entry: ChangeStreamEntry, hotlist: Hotlist, *more: Hotlist
) -> list[Any]:
    async def owner(owner_id: str) -> Principal | None:
        return OWNER

    return await evaluate_hotlists_for_entry(
        entry, graph=graph,  # type: ignore[arg-type]
        scheme=SCHEME, hotlist_store=_Hotlists(hotlist, *more),  # type: ignore[arg-type]
        alert_store=None, audit=None, valkey=_Valkey(),  # type: ignore[arg-type]
        principal_for_owner=owner, policy="strict",
    )  # fmt: skip


def _filler(count: int) -> dict[str, dict[str, Any]]:
    return {f"n{i:04d}": {"properties": {"value_normalised": f"+4420794{i:05d}"}} for i in range(count)}


async def test_a_hotlisted_node_past_the_two_hundredth_alerts(recorded: list[dict[str, Any]]) -> None:
    nodes = _filler(450)
    nodes["n0449"] = {"properties": {"value_normalised": HOT}}
    entry = _entry(list(nodes))
    assert entry.node_ids.index("n0449") > MAX_TOUCHED_NODES_PER_EVALUATION
    alerts = await _hotlists_for(_Graph(nodes), entry, _hotlist())
    assert [c["triggering_node_ids"] for c in recorded] == [["n0449"]]
    assert len(alerts) == 1


async def test_the_graph_is_asked_for_chunks_of_the_cap_and_never_more(
    recorded: list[dict[str, Any]],
) -> None:
    graph = _Graph(_filler(450))
    await _hotlists_for(graph, _entry(list(graph.nodes)), _hotlist())
    assert graph.chunks == [200, 200, 50]
    assert max(graph.chunks) <= MAX_TOUCHED_NODES_PER_EVALUATION


def _hotlist_n(n: int, identifier: str, dataset_id: str | None = None) -> Hotlist:
    return _hotlist(identifier, dataset_id).model_copy(update={"id": f"h{n}"})


async def test_the_entry_is_read_once_however_many_hotlists_are_active(
    recorded: list[dict[str, Any]],
) -> None:
    """H hotlists over N nodes cost ceil(N / 200) reads, not H times that: the nodes are read once,
    indexed by their normalised value, and each hotlist looks itself up."""
    nodes = _filler(450)
    nodes["n0100"] = {"properties": {"value_normalised": "+447700900001"}}
    nodes["n0300"] = {"properties": {"value_normalised": "+447700900002"}}
    graph = _Graph(nodes)
    hotlists = [_hotlist_n(i, f"+44770090000{i % 3 + 1}") for i in range(7)]
    await _hotlists_for(graph, _entry(list(nodes)), *hotlists)
    assert graph.chunks == [200, 200, 50], "three reads for seven hotlists, not twenty-one"
    # Each hotlist still alerts on its own identifier, on the nodes that carry it.
    by_hotlist: dict[str, list[str]] = {}
    for call in recorded:
        by_hotlist.setdefault(call["rule_id"], []).extend(call["triggering_node_ids"])
    expected = {"+447700900001": ["n0100"], "+447700900002": ["n0300"], "+447700900003": []}
    for i, hotlist in enumerate(hotlists):
        assert by_hotlist.get(f"hotlist:h{i}", []) == expected[hotlist.identifier]


async def test_each_hotlist_keeps_its_own_dataset_check_over_the_shared_read(
    recorded: list[dict[str, Any]],
) -> None:
    nodes = {
        "a": {"properties": {"value_normalised": HOT}, "datasets": ["ds-1"]},
        "b": {"properties": {"value_normalised": HOT}, "datasets": ["ds-2"]},
    }
    graph = _Graph(nodes)
    await _hotlists_for(
        graph,
        _entry(["a", "b"]),
        _hotlist_n(1, HOT, "ds-1"),
        _hotlist_n(2, HOT, "ds-2"),
        _hotlist_n(3, HOT),
    )
    assert graph.chunks == [2]
    got = {c["rule_id"]: sorted(c["triggering_node_ids"]) for c in recorded if c["rule_id"] != "hotlist:h3"}
    assert got == {"hotlist:h1": ["a"], "hotlist:h2": ["b"]}
    assert sorted(c["triggering_node_ids"][0] for c in recorded if c["rule_id"] == "hotlist:h3") == [
        "a",
        "b",
    ]
    assert all(c["recipient"].id == OWNER.id for c in recorded)


async def test_with_no_active_hotlist_the_entry_is_not_read_at_all(
    recorded: list[dict[str, Any]],
) -> None:
    graph = _Graph(_filler(450))

    async def owner(owner_id: str) -> Principal | None:
        return OWNER

    alerts = await evaluate_hotlists_for_entry(
        _entry(list(graph.nodes)), graph=graph,  # type: ignore[arg-type]
        scheme=SCHEME, hotlist_store=_Hotlists(),  # type: ignore[arg-type]
        alert_store=None, audit=None, valkey=_Valkey(),  # type: ignore[arg-type]
        principal_for_owner=owner, policy="strict",
    )  # fmt: skip
    assert alerts == [] and graph.chunks == []


async def test_a_hotlist_whose_owner_cannot_be_resolved_is_stopped_and_reads_nothing_more(
    recorded: list[dict[str, Any]],
) -> None:
    graph = _Graph({"a": {"properties": {"value_normalised": HOT}}})
    store = _Hotlists(_hotlist_n(1, HOT))

    async def nobody(owner_id: str) -> Principal | None:
        return None

    alerts = await evaluate_hotlists_for_entry(
        _entry(["a"]), graph=graph,  # type: ignore[arg-type]
        scheme=SCHEME, hotlist_store=store,  # type: ignore[arg-type]
        alert_store=None, audit=None, valkey=_Valkey(),  # type: ignore[arg-type]
        principal_for_owner=nobody, policy="strict",
    )  # fmt: skip
    assert alerts == [] and recorded == [] and store.statuses == ["stopped"]


async def test_every_node_of_an_entry_is_read_whatever_its_size(
    recorded: list[dict[str, Any]],
) -> None:
    nodes = _filler(1234)
    for i in (0, 199, 200, 399, 400, 1233):
        nodes[f"n{i:04d}"] = {"properties": {"value_normalised": HOT}}
    await _hotlists_for(_Graph(nodes), _entry(list(nodes)), _hotlist())
    assert sorted(c["triggering_node_ids"][0] for c in recorded) == [
        f"n{i:04d}" for i in (0, 199, 200, 399, 400, 1233)
    ]


async def test_a_node_of_another_dataset_never_matches_whatever_its_place(
    recorded: list[dict[str, Any]],
) -> None:
    nodes = _filler(250)
    nodes["n0240"] = {"properties": {"value_normalised": HOT}, "datasets": ["other-dataset"]}
    nodes["n0241"] = {"properties": {"value_normalised": HOT}, "datasets": ["case-dataset"]}
    await _hotlists_for(_Graph(nodes), _entry(list(nodes)), _hotlist(dataset_id="case-dataset"))
    assert [c["triggering_node_ids"] for c in recorded] == [["n0241"]]


async def test_the_owner_is_the_recipient_never_the_matcher(recorded: list[dict[str, Any]]) -> None:
    nodes = {"a": {"properties": {"value_normalised": HOT}}}
    graph = _Graph(nodes)
    await _hotlists_for(graph, _entry(["a"]), _hotlist())
    assert recorded[0]["recipient"].id == OWNER.id
    assert graph.principals != [OWNER.id], "the match itself is read unscoped, as the docstring says"


async def test_an_entry_with_no_nodes_reads_nothing(recorded: list[dict[str, Any]]) -> None:
    graph = _Graph({})
    assert await _hotlists_for(graph, _entry([]), _hotlist()) == []
    assert graph.chunks == [] and recorded == []


async def test_a_monitor_is_evaluated_for_a_run_that_only_referenced_nodes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The entry of a run that created nothing used to be empty and was never published. A monitor
    re-runs its pattern in full for an entry; here the entry is built from a run that only
    referenced nodes, and the evaluation still fires once, nothing breaking."""
    run = LoadReport(
        load_id="l", recipe_id="r", recipe_version=1, referenced_node_ids=["existing-1", "existing-2"]
    )
    entry = _entry(touched_node_ids(run))
    assert entry.node_ids == ["existing-1", "existing-2"]

    matched = SimpleNamespace(id="existing-1")

    class _Graph2(_Graph):
        async def match(self, definition: Any, principal: Principal) -> Subgraph:
            return Subgraph.model_construct(nodes=[matched], edges=[])

    class _Monitors:
        async def list_all_active(self) -> list[Monitor]:
            return [
                Monitor(
                    id="m1", pattern_id="p1", owner_id=OWNER.id, review_date=date(2027, 1, 1),
                    created_at=datetime(2026, 10, 26, tzinfo=UTC),
                )  # fmt: skip
            ]

        async def set_status(self, monitor_id: str, status: str) -> None:
            return None

    class _Patterns:
        async def get_authorized(self, pattern_id: str, principal: Principal) -> Any:
            return SimpleNamespace(
                name="a pattern",
                definition=PatternQuery(nodes=[PatternNode(var="e", entity_type="Endpoint")], edges=[]),
            )

    calls: list[dict[str, Any]] = []

    async def record_match(**kwargs: Any) -> Any:
        calls.append(kwargs)
        return SimpleNamespace(id="alert-1")

    monkeypatch.setattr(evaluation, "record_match", record_match)

    async def owner(owner_id: str) -> Principal | None:
        return OWNER

    alerts = await evaluate_monitors_for_entry(
        entry, graph=_Graph2({}),  # type: ignore[arg-type]
        monitor_store=_Monitors(), pattern_store=_Patterns(),  # type: ignore[arg-type]
        alert_store=None, audit=None, valkey=_Valkey(),  # type: ignore[arg-type]
        principal_for_owner=owner,
    )  # fmt: skip
    assert len(alerts) == 1 and calls[0]["recipient"].id == OWNER.id
