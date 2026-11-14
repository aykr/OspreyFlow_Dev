"""The client-size loader (ROUTE_052 step B, `v052-load`; its DESIGN.md is under
`process/lanes/rules/v052-load/`).

Offline: a tiny generated set is loaded through the real dataset-stamping graph
(`services.api.dataset_scope.stamping`) over a recording fake of the graph adapter, with fakes of
the analytics store, the text store and the case registry. The graph fake refuses what the real
adapter refuses (rule 15): a write outside a transaction, a link whose end is not stored, a bulk
load while a transaction is open; and, as the real bulk loader does, hands back a pair already
stored as a collision instead of writing it, while `upsert_edges` merges a stored pair by adding
its occurrences. The analytics fake removes by `load_id` as `retract_load` does.
"""

from __future__ import annotations

import asyncio
import json
from collections import Counter
from pathlib import Path
from typing import Any

import pytest
from scripts import client_size_plan as plan
from scripts import generate_client_size as gen
from scripts import load_client_size as loader
from services.api.dataset_scope import stamping

from ontology.errors import OntologyError
from ontology.handling import load_uk_le_scheme
from ports.graph import BulkEdgeResult, GraphPort
from schemas.domain import ProvenanceState

SCALE = 0.0002
GRAPH_SCALE = 0.01


class Crash(RuntimeError):
    """A stop part-way, planted by a test."""


class FakeGraph:
    def __init__(self) -> None:
        self.nodes: dict[str, Any] = {}
        self.edges: dict[str, Any] = {}
        self.open: set[int] = set()
        self._tx = 0
        self.bulk_calls = 0
        self.node_writes = 0
        self.crash_on_bulk_call: int | None = None

    async def begin_transaction(self) -> int:
        self._tx += 1
        self.open.add(self._tx)
        return self._tx

    async def commit_transaction(self, tx: int) -> None:
        self.open.remove(tx)

    async def rollback_transaction(self, tx: int) -> None:
        self.open.discard(tx)

    async def upsert_nodes(self, nodes: Any, tx: int) -> list[str]:
        assert tx in self.open, "a write outside a transaction"
        for node in nodes:
            self.node_writes += 1
            held = self.nodes.get(node.id)
            datasets = sorted(set(node.datasets) | set(held.datasets if held else []))
            self.nodes[node.id] = node.model_copy(update={"datasets": datasets})
        return [n.id for n in nodes]

    def _pair(self, edge: Any) -> tuple[str, str, str]:
        return (edge.type, edge.source, edge.target)

    async def upsert_edges(self, edges: Any, tx: int) -> list[str]:
        assert tx in self.open, "a write outside a transaction"
        self._check_ends(edges)
        for edge in edges:
            held = next((e for e in self.edges.values() if self._pair(e) == self._pair(edge)), None)
            if held is not None:
                self.edges[held.id] = held.model_copy(
                    update={"occurrences": held.occurrences + edge.occurrences}
                )
            else:
                self.edges[edge.id] = edge
        return [e.id for e in edges]

    async def bulk_load_edges(
        self, edges: Any, *, chunk_size: int = 500, progress: Any = None
    ) -> BulkEdgeResult:
        assert not self.open, "the nodes must be committed before links are bulk loaded"
        self.bulk_calls += 1
        self._check_ends(edges)
        stored = {self._pair(e) for e in self.edges.values()}
        written, collisions = [], []
        for start in range(0, len(edges), chunk_size):
            if self.crash_on_bulk_call == self.bulk_calls and start > 0:
                raise Crash("stopped part-way through a bulk load")
            for edge in edges[start : start + chunk_size]:
                if self._pair(edge) in stored:
                    collisions.append(edge)
                    continue
                self.edges[edge.id] = edge
                stored.add(self._pair(edge))
                written.append(edge.id)
        return BulkEdgeResult(written=written, collisions=collisions, received=len(edges), chunks=1)

    def _check_ends(self, edges: Any) -> None:
        for edge in edges:
            if edge.source not in self.nodes or edge.target not in self.nodes:
                raise OntologyError(f"link {edge.id}: an end is not stored")


class FakeAnalytics:
    def __init__(self) -> None:
        self.rows: list[Any] = []
        self.batches = 0
        self.crash_on_batch: int | None = None

    async def load_events(self, records: Any) -> None:
        self.batches += 1
        if self.crash_on_batch == self.batches:
            raise Crash("stopped part-way through an events file")
        self.rows.extend(records)

    async def retract_load(self, load_id: str) -> int:
        before = len(self.rows)
        self.rows = [r for r in self.rows if r.load_id != load_id]
        return before - len(self.rows)


class FakeTexts:
    def __init__(self) -> None:
        self.texts: dict[str, tuple[str, str]] = {}

    async def store_document_text(self, document_id: str, text: str, principal: Any) -> None:
        self.texts[document_id] = (text, principal.org_unit)


@pytest.fixture(scope="module")
def generated(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, dict[str, Any]]:
    out = tmp_path_factory.mktemp("client-size-load")
    manifest = gen.generate(
        out, seed=11, scale=SCALE, graph_scale=GRAPH_SCALE, say=lambda *_a: None
    )
    return out, manifest


@pytest.fixture
def folder(generated: tuple[Path, dict[str, Any]], tmp_path: Path) -> Path:
    """A copy per test, so each has its own ledger."""
    import shutil

    copy = tmp_path / "set"
    shutil.copytree(generated[0], copy)
    return copy


@pytest.fixture(autouse=True)
def _no_ceiling(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OSPREY_HIGHEST_MARKING", raising=False)


class Stack:
    def __init__(self) -> None:
        self.graph = FakeGraph()
        self.analytics = FakeAnalytics()
        self.texts = FakeTexts()
        self.cases: list[str] = []
        self.lines: list[str] = []
        self.checked: list[str] = []

    def deps(self) -> loader.Deps:
        async def ensure_case(source: plan.Source) -> str:
            self.cases.append(source.key)
            return f"case-{source.key}"

        async def check(types: Any) -> int:
            self.checked = list(types)
            return 0

        return loader.Deps(
            graph_for=lambda dataset: stamping(self.graph, dataset=dataset),  # type: ignore[arg-type]
            raw_graph=self.graph,  # type: ignore[arg-type]
            analytics=self.analytics,  # type: ignore[arg-type]
            texts=self.texts,
            ensure_case=ensure_case,
            scheme=load_uk_le_scheme(),
            check=check,
            say=self.lines.append,
        )


def _load(folder: Path, stack: Stack, **kwargs: Any) -> dict[str, loader.Totals]:
    return asyncio.run(loader.load(folder, stack.deps(), **kwargs))


def _manifest_rows(folder: Path, kind: str) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    manifest = json.loads((folder / "manifest.json").read_text())
    out = []
    for entry in manifest["files"]:
        if entry["kind"] == kind:
            out += [(entry, json.loads(line)) for line in (folder / entry["path"]).open()]
    return out


def _event_count(folder: Path) -> int:
    manifest = json.loads((folder / "manifest.json").read_text())
    return int(manifest["totals"]["events"])


# --- A whole load -------------------------------------------------------------------------------


def test_a_load_writes_every_element_stamped_marked_and_attributed(folder: Path) -> None:
    stack = Stack()
    _load(folder, stack)
    nodes = _manifest_rows(folder, "nodes")
    expected_datasets: dict[str, set[str]] = {}
    for entry, row in nodes:
        expected_datasets.setdefault(row["id"], set()).add(
            plan.SOURCES_BY_KEY[entry["source"]].dataset
        )
    assert set(stack.graph.nodes) == set(expected_datasets)
    for node_id, datasets in expected_datasets.items():
        stored = stack.graph.nodes[node_id]
        assert set(stored.datasets) == datasets, node_id
        assert stored.provenance.state == ProvenanceState.ASSERTED
        assert stored.provenance.sources[0].document_id.startswith("client-size:cs-")
    # A shared number is in both the subscribers' and the calls' datasets.
    assert set(stack.graph.nodes["cs-msisdn-0"].datasets) == {"cs-calls", "cs-subscribers"}
    by_id = {row["id"]: (entry, row) for entry, row in nodes}
    for node_id, (entry, row) in by_id.items():
        marking = row.get("marking") or plan.SOURCES_BY_KEY[entry["source"]].marking.as_dict()
        assert stack.graph.nodes[node_id].handling.model_dump(include=set(marking)) == marking
    intel_marks = {
        stack.graph.nodes[i].handling.classification
        for i in stack.graph.nodes
        if i.startswith("cs-intel-doc-")
    }
    assert intel_marks == {"OFFICIAL-SENSITIVE", "SECRET"}


def test_every_link_is_written_once_with_its_occurrences(folder: Path) -> None:
    stack = Stack()
    _load(folder, stack)
    rows = _manifest_rows(folder, "edges")
    pairs = Counter((r["type"], r["s"], r["t"]) for _e, r in rows)
    stored = Counter(
        (e.type, e.source, e.target) for e in stack.graph.edges.values() if e.type != "SAME_AS"
    )
    assert set(stored) == set(pairs)
    assert max(stored.values()) == 1
    occurrences = {(r["type"], r["s"], r["t"]): 0 for _e, r in rows}
    for _e, r in rows:
        occurrences[(r["type"], r["s"], r["t"])] += r.get("occ", 1)
    for e in stack.graph.edges.values():
        if e.type != "SAME_AS":
            # The fake keeps the first write of a pair repeated within one file (the real bulk
            # loader aggregates it); no pair is repeated across files.
            assert e.occurrences <= occurrences[(e.type, e.source, e.target)]
    assert {e.type for e in stack.graph.edges.values()} == set(loader.EDGE_TYPES)
    assert stack.checked == list(loader.EDGE_TYPES)


def test_the_merge_candidates_are_inferred_marked_as_the_stricter_record_and_in_no_dataset(
    folder: Path,
) -> None:
    stack = Stack()
    _load(folder, stack)
    planted = {r["id"]: r for _e, r in _manifest_rows(folder, "same_as")}
    stored = {e.id: e for e in stack.graph.edges.values() if e.type == "SAME_AS"}
    assert set(stored) == set(planted)
    rank = load_uk_le_scheme().classification.index
    for edge_id, edge in stored.items():
        assert edge.provenance.state == ProvenanceState.INFERRED
        assert edge.datasets == []
        assert "truth" not in json.dumps(edge.properties)
        assert edge.properties["score"] == planted[edge_id]["score"]
        assert edge.properties["model_version"] == plan.SAME_AS_MODEL
        ends = [stack.graph.nodes[edge.source].handling, stack.graph.nodes[edge.target].handling]
        assert rank(edge.handling.classification) == max(rank(h.classification) for h in ends)
        if "R" in {h.handling_code for h in ends}:
            assert edge.handling.handling_code == "R"
    covert = next(e for e in stored.values() if e.target.startswith("cs-covert-person-"))
    assert (
        covert.handling.classification,
        covert.handling.handling_code,
        covert.handling.owning_unit,
    ) == ("SECRET", "R", "unit-covert")


def test_texts_are_held_by_their_documents_owning_unit(folder: Path) -> None:
    stack = Stack()
    _load(folder, stack)
    for _entry, row in _manifest_rows(folder, "texts"):
        text, unit = stack.texts.texts[row["document_id"]]
        assert text == row["text"]
        assert unit == stack.graph.nodes[row["document_id"]].handling.owning_unit


def test_events_are_loaded_once_into_their_sources_case_under_their_files_load_id(
    folder: Path,
) -> None:
    stack = Stack()
    _load(folder, stack)
    assert len(stack.analytics.rows) == _event_count(folder)
    assert sorted(stack.cases) == sorted(s.key for s in plan.SOURCES)
    by_source = Counter(r.investigation_scope for r in stack.analytics.rows)
    assert set(by_source) == {"case-calls", "case-cells", "case-transactions"}
    for record in stack.analytics.rows:
        source = record.investigation_scope.removeprefix("case-")
        assert record.load_id.startswith(f"client-size:{source}/")
        assert record.handling.model_dump(include={"classification", "handling_code"}) == {
            "classification": plan.SOURCES_BY_KEY[source].marking.classification,
            "handling_code": plan.SOURCES_BY_KEY[source].marking.handling_code,
        }
        assert record.edge_id in stack.graph.edges


# --- Resuming ----------------------------------------------------------------------------------


def test_a_second_run_writes_nothing(folder: Path) -> None:
    stack = Stack()
    _load(folder, stack)
    writes, bulk, rows = stack.graph.node_writes, stack.graph.bulk_calls, len(stack.analytics.rows)
    again = _load(folder, stack)
    assert (stack.graph.node_writes, stack.graph.bulk_calls) == (writes, bulk)
    assert len(stack.analytics.rows) == rows
    assert all(t.files == 0 and t.skipped > 0 for t in again.values())


def test_a_link_file_stopped_part_way_is_finished_without_merging_its_links_twice(
    folder: Path,
) -> None:
    stack = Stack()
    bigger = max(
        (
            e
            for e in json.loads((folder / "manifest.json").read_text())["files"]
            if e["kind"] == "edges"
        ),
        key=lambda e: e["rows"],
    )
    assert bigger["rows"] > loader.BULK_CHUNK
    order = [
        e["path"]
        for e in loader._files(json.loads((folder / "manifest.json").read_text()), "edges")
    ]
    stack.graph.crash_on_bulk_call = order.index(bigger["path"]) + 1
    with pytest.raises(Crash):
        _load(folder, stack, stages=("cases", "nodes", "edges"))
    part_written = len(stack.graph.edges)
    assert part_written > 0
    stack.graph.crash_on_bulk_call = None
    _load(folder, stack)
    assert any("resumed" in line for line in stack.lines)
    rows = _manifest_rows(folder, "edges")
    occurrences: Counter[tuple[str, str, str]] = Counter()
    for _e, r in rows:
        occurrences[(r["type"], r["s"], r["t"])] += r.get("occ", 1)
    for e in stack.graph.edges.values():
        if e.type != "SAME_AS":
            assert e.occurrences <= occurrences[(e.type, e.source, e.target)], e.id


def test_the_resume_rule_matters_merging_the_collisions_would_count_links_twice(
    folder: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Red for the rule above: a rerun that merges collisions (the seeds' first-attempt path)
    doubles the occurrences of every link the stopped attempt had written."""
    stack = Stack()
    order = loader._files(json.loads((folder / "manifest.json").read_text()), "edges")
    calls = next(i for i, e in enumerate(order) if e["source"] == "calls")
    stack.graph.crash_on_bulk_call = calls + 1
    with pytest.raises(Crash):
        _load(folder, stack, stages=("cases", "nodes", "edges"))
    stack.graph.crash_on_bulk_call = None
    original = loader._links

    async def always_first_attempt(
        graph: GraphPort, writes: Any, *, resumed: bool, say: Any
    ) -> Any:
        return await original(graph, writes, resumed=False, say=say)

    monkeypatch.setattr(loader, "_links", always_first_attempt)
    _load(folder, stack, stages=("edges",))
    rows = {r["id"]: r for _e, r in _manifest_rows(folder, "edges")}
    doubled = [
        e
        for e in stack.graph.edges.values()
        if e.id in rows and e.occurrences > rows[e.id].get("occ", 1)
    ]
    assert doubled


def test_an_events_file_stopped_part_way_is_retracted_and_loaded_again(
    folder: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(loader, "EVENT_BATCH", 500)
    stack = Stack()
    stack.analytics.crash_on_batch = 3
    with pytest.raises(Crash):
        _load(folder, stack)
    assert 0 < len(stack.analytics.rows) < _event_count(folder)
    stack.analytics.crash_on_batch = None
    _load(folder, stack)
    assert len(stack.analytics.rows) == _event_count(folder)
    assert len({r.event_id for r in stack.analytics.rows}) == len(stack.analytics.rows)
    assert any("part-loaded" in line for line in stack.lines)


# --- Refusals ----------------------------------------------------------------------------------


def test_a_ledger_of_another_set_is_refused(folder: Path) -> None:
    stack = Stack()
    _load(folder, stack, stages=("cases",))
    state = json.loads((folder / "load_state.json").read_text())
    state["identity"]["seed"] = 999
    (folder / "load_state.json").write_text(json.dumps(state))
    with pytest.raises(loader.LoadRefused, match="another generated set"):
        _load(folder, Stack())


def test_a_changed_file_is_refused_and_not_marked_done(folder: Path) -> None:
    manifest = json.loads((folder / "manifest.json").read_text())
    entry = next(e for e in manifest["files"] if e["kind"] == "texts")
    path = folder / entry["path"]
    path.write_bytes(path.read_bytes().replace(b'"text":"', b'"text":"X', 1))
    stack = Stack()
    with pytest.raises(loader.LoadRefused, match="SHA-256 differs"):
        _load(folder, stack, stages=("cases", "texts"))
    state = json.loads((folder / "load_state.json").read_text())
    assert f"texts:{entry['path']}" not in state["done"]


def test_events_without_a_case_are_refused(folder: Path) -> None:
    with pytest.raises(loader.LoadRefused, match="no case recorded"):
        _load(folder, Stack(), stages=("events",))


def test_a_deployment_ceiling_below_secret_is_refused_before_anything(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OSPREY_HIGHEST_MARKING", "OFFICIAL")
    with pytest.raises(loader.LoadRefused, match="below SECRET"):
        loader.refuse_below_secret()
    monkeypatch.setenv("OSPREY_HIGHEST_MARKING", "SECRET")
    loader.refuse_below_secret()


def test_every_node_id_names_a_source_whose_marking_it_carries(
    generated: tuple[Path, dict[str, Any]],
) -> None:
    folder, _manifest = generated
    for entry, row in _manifest_rows(folder, "nodes"):
        if "marking" not in row:
            assert loader.marking_of(row["id"]) == plan.SOURCES_BY_KEY[entry["source"]].marking


def test_a_folder_with_no_set_is_refused_before_any_store_is_opened(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import socket

    def no_network(*_a: object, **_k: object) -> None:
        raise OSError("no store may be opened by a refused load")

    monkeypatch.setattr(socket, "create_connection", no_network)
    monkeypatch.setattr(socket.socket, "connect", no_network)
    assert loader.main(["--from", str(tmp_path)]) == 2
    assert "holds no manifest.json" in capsys.readouterr().err


def test_a_grant_names_every_case_or_one_sources_case() -> None:
    """`ACCOUNT=LEVEL` on every source's case; `SOURCE:ACCOUNT=LEVEL` on that source's alone; a
    prefix naming no source refused (a misspelt key would leave a case unshared unsaid)."""
    given = ["m10-cleared=viewer", "intel:m10-part=viewer", "nominals:m10-part=viewer"]
    assert loader.grants_for("intel", given) == ["m10-cleared=viewer", "m10-part=viewer"]
    assert loader.grants_for("covert", given) == ["m10-cleared=viewer"]
    with pytest.raises(SystemExit, match="'intell' is not a source"):
        loader.grants_for("intel", ["intell:m10-part=viewer"])


def test_a_rerun_with_grants_shares_cases_already_made(folder: Path) -> None:
    """The cases stage run again with a grant finds every recorded case again, so its grants are
    set; without one, a recorded case is left alone."""
    stack = Stack()
    _load(folder, stack, stages=["cases"])
    made = list(stack.cases)
    stack.cases.clear()
    _load(folder, stack, stages=["cases"])
    assert stack.cases == []
    deps = stack.deps()
    deps.regrant = True
    asyncio.run(loader.load(folder, deps, stages=["cases"]))
    assert stack.cases == made
