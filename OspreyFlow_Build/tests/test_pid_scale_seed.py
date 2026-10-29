"""The scale cohort's seed (ADR-127 Amendment 40, "What it writes").

`scripts.seed_pid_scale.seed_scale` writes `pid_writes.writes(build_plan("scale"), "seed", ...)`
through the dataset-stamping adapter: 3,000 prisoners, exactly 30,000 links, 7,176 nodes, every
element in the scale dataset and none in the demo one. A second call counts the whole cohort stored
and writes nothing; a run that finds it part-stored refuses, since writing it again would merge the
stored links a second time. Pure: the graph here is a recording fake, which models what the real
adapter refuses (rule 15): a write outside a transaction, a link whose end is not stored, a bulk
load while a transaction is open, and `get_nodes` given a bare string; and, as the real
`type_counts` does, it counts only what the principal's datasets read. The real adapter's side is
`tests/services/api/test_pid_scale_seed_live.py`.
"""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest
from scripts import seed_pid_scale

from demo_fixtures import pid_plan, pid_writes
from demo_fixtures.datasets import PID, PID_SCALE
from ontology.errors import OntologyError
from ports.graph import BulkEdgeResult
from schemas.domain import Principal

CREATED = datetime(2026, 10, 29, 9, 0, tzinfo=UTC)
SEEDER = Principal(id="pid-scale-seed-worker", clearance="OFFICIAL", org_unit="unit-1")


class FakeGraph:
    """Stores nodes by id and edges by id; offers `bulk_load_edges`, as the real adapter does."""

    def __init__(self) -> None:
        self.nodes: dict[str, Any] = {}
        self.edges: dict[str, Any] = {}
        self.open: set[str] = set()
        self.bulk_calls = 0

    async def begin_transaction(self) -> str:
        self.open.add("tx")
        return "tx"

    async def commit_transaction(self, tx: str) -> None:
        self.open.remove(tx)

    async def rollback_transaction(self, tx: str) -> None:
        self.open.discard(tx)

    async def type_counts(self, principal: Principal) -> Any:
        """Per-type counts of what the principal's datasets read (all of it for `None`)."""

        def read(element: Any) -> bool:
            return principal.datasets is None or bool(
                set(element.datasets) & set(principal.datasets)
            )

        return SimpleNamespace(
            nodes=Counter(n.type for n in self.nodes.values() if read(n)),
            edges=Counter(e.type for e in self.edges.values() if read(e)),
        )

    async def get_nodes(self, node_ids: Any, principal: Principal) -> list[Any]:
        if isinstance(node_ids, str):
            raise TypeError("get_nodes takes a sequence of ids, not a bare string")
        return [self.nodes[i] for i in sorted(set(node_ids)) if i in self.nodes]

    async def upsert_nodes(self, nodes: Any, tx: str) -> list[str]:
        assert tx in self.open, "a write outside a transaction"
        for node in nodes:
            self.nodes[node.id] = node
        return [n.id for n in nodes]

    async def upsert_edges(self, edges: Any, tx: str) -> list[str]:
        assert tx in self.open, "a write outside a transaction"
        self._check_ends(edges)
        for edge in edges:
            self.edges[edge.id] = edge
        return [e.id for e in edges]

    async def bulk_load_edges(
        self, edges: Any, *, chunk_size: int = 500, progress: Any = None
    ) -> BulkEdgeResult:
        assert not self.open, "the nodes must be committed before the edges are bulk loaded"
        self.bulk_calls += 1
        self._check_ends(edges)
        written = []
        for edge in edges:
            if edge.id not in self.edges:
                self.edges[edge.id] = edge
                written.append(edge.id)
        return BulkEdgeResult(written=written, received=len(edges), chunks=1)

    def _check_ends(self, edges: Any) -> None:
        for edge in edges:
            if edge.source not in self.nodes or edge.target not in self.nodes:
                raise OntologyError(f"link {edge.id}: an end is not stored")


@pytest.fixture(scope="module")
def scale() -> Any:
    return pid_plan.build_plan("scale")


def _quiet(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("builtins.print", lambda *a, **k: None)


def test_the_writes_are_the_scale_plans_7176_nodes_and_30000_links_in_the_scale_dataset_alone(
    scale: Any,
) -> None:
    nodes, edges = seed_pid_scale.scale_writes(CREATED)
    assert len(nodes) == len(scale.entities) == 7_176
    assert len(edges) == len(scale.links) == pid_plan.SCALE_LINKS == 30_000
    assert (nodes, edges) == pid_writes.writes(
        scale, "seed", dataset=PID_SCALE.id, created_at=CREATED
    )
    elements: list[Any] = [*nodes, *edges]
    for element in elements:
        assert element.datasets == ["prison-intelligence-scale"]
        assert PID.id not in element.datasets


def test_a_first_call_writes_everything_and_a_second_writes_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import asyncio

    _quiet(monkeypatch)
    graph = FakeGraph()
    first = asyncio.run(seed_pid_scale.seed_scale(graph, SEEDER, created_at=CREATED))  # type: ignore[arg-type]
    assert (first.nodes, first.links, first.already_here) == (7_176, 30_000, False)
    assert len(graph.nodes) == 7_176 and len(graph.edges) == 30_000
    assert graph.bulk_calls == 1
    held = (dict(graph.nodes), dict(graph.edges))

    second = asyncio.run(seed_pid_scale.seed_scale(graph, SEEDER, created_at=CREATED))  # type: ignore[arg-type]
    assert (second.nodes, second.links, second.already_here) == (0, 0, True)
    assert graph.bulk_calls == 1, "a second run must not load again"
    assert (graph.nodes, graph.edges) == held


def test_the_fake_refuses_what_the_real_adapter_refuses() -> None:
    """Rule 15: the fake is only evidence if it can refuse. A link before its ends, a bare string
    to `get_nodes`."""
    import asyncio

    graph = FakeGraph()
    _, edges = seed_pid_scale.scale_writes(CREATED)
    with pytest.raises(OntologyError):
        asyncio.run(graph.bulk_load_edges(edges[:1]))
    with pytest.raises(TypeError):
        asyncio.run(graph.get_nodes("pid-abc", SEEDER))


def test_a_run_that_finds_the_cohort_part_stored_refuses_and_writes_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A run that stopped after its nodes (the links go last) left the first prisoner stored and
    no links. Called again, the seed must neither say the cohort is here nor write the links a
    second time, which would merge the stored ones twice: it refuses, naming what is stored."""
    import asyncio

    _quiet(monkeypatch)
    graph = FakeGraph()
    nodes, _ = seed_pid_scale.scale_writes(CREATED)
    for node in nodes:
        graph.nodes[node.id] = node
    with pytest.raises(
        seed_pid_scale.PartialCohort, match=r"7,176 of 7,176 nodes and 0 of 30,000 links"
    ):
        asyncio.run(seed_pid_scale.seed_scale(graph, SEEDER, created_at=CREATED))  # type: ignore[arg-type]
    assert graph.bulk_calls == 0 and not graph.edges


def test_another_datasets_elements_do_not_count_as_the_cohort(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The demo pack's elements in the same store are not the scale cohort: the seed counts the
    scale dataset only, so it still writes the whole cohort."""
    import asyncio

    _quiet(monkeypatch)
    graph = FakeGraph()
    demo_nodes, _ = pid_writes.writes(
        pid_plan.build_plan("demo"), "seed", dataset=PID.id, created_at=CREATED
    )
    for node in demo_nodes:
        graph.nodes[node.id] = node
    result = asyncio.run(seed_pid_scale.seed_scale(graph, SEEDER, created_at=CREATED))  # type: ignore[arg-type]
    assert (result.nodes, result.links, result.already_here) == (7_176, 30_000, False)


def test_the_arguments_default_to_the_bulk_method_and_need_a_case() -> None:
    args = seed_pid_scale.parse_args(["--case-name", "x"])
    assert args.method == "bulk"
    with pytest.raises(SystemExit):
        seed_pid_scale.parse_args([])
    assert seed_pid_scale.parse_args(["--case-name", "x", "--method", "upsert"]).method == "upsert"
