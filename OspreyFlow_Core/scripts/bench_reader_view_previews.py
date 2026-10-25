"""Times the reader's view of a large working set: previews, a concurrent menu, an expansion.

    python -m scripts.bench_reader_view_previews                       # 50,000 nodes, 250,000 links
    python -m scripts.bench_reader_view_previews --concurrent          # the menu's 16 sent at once
    python -m scripts.bench_reader_view_previews --expand              # a 500-node expansion
    python -m scripts.bench_reader_view_previews --store memory        # the computation alone
    python -m scripts.bench_reader_view_previews --nodes 20000 --edges 40000 --menus 5

ADR-124 decision 2 counts a preview's figures, a cap's refusal and an expansion's choice over the
reader's projected view of the stored set, plus what the request adds. The view is never built:
the store keeps counts (nodes by signature, links by signature and ends' signatures), the service
sums them over the signatures the reader may read, and looks up only the ids a request would add
(Amendment 4). Every run reports what the counts cost to read and what a write costs (500 nodes
and a link from each, through the store's script on Valkey), and then:

  default       the untyped preview and one per link type of the default ontology, in turn: the
                first after a change (cold: the reader's readable signatures are worked out again)
                and the whole menu again (warm);
  --concurrent  the same sixteen previews started at once, as `GlassCanvas` sends them, after a
                change (cold) and again (warm);
  --branch      `WorkingSetService.branch` of the whole case into a new one, and --restore
                `WorkingSetService.restore` of its whole membership over itself: each writes tens
                of thousands of elements, in scripts of at most 1,000, and the figure is the
                longest single script (how long Valkey is held at once);
  --forward     what the live forward adds to each pushed delta (ADR-124 decision 2, "the cost
                on the live path"): a delta that adds a node the reader can read makes the forward
                recount that reader's projected view against the caps, from the counted index.
                `--sockets` simulated readers are open at once and each gets each of `--deltas`
                additions; the figures are the median and the worst of that recount per delta (the
                slowest socket's, started at once as the sockets' own tasks are), against a case
                of `--nodes` nodes;
  --expand      `WorkingSetService.expand` end to end for an expansion that returns 500 new nodes
                (and a link from each): the figures, the choice of asking for the links among
                them, the cap and the writes to the store and the index. `02_GLASS_FRONTEND.md` §5
                allows 800 ms for it.

What is real and what is not. The service, its projection and its cap arithmetic are the real ones.
The store is the real `ValkeyWorkingSetStore` (`--store valkey`, the default, against the Valkey the
Conduit's own settings name) or a dictionary (`--store memory`), which leaves out the cost of
the transfer. The graph is a stub: its `expand` returns a small neighbourhood (a preview) or 500
new nodes (`--expand`), and its `edges_among` finds nothing. Nothing here touches ArcadeDB. The
dictionary store is this script's own and not the test fake (`FakeWorkingSetStore`): that lives in
Build's tests, which Core does not import (`06_DECISIONS.md` ADR-114 Amendment 2, Core stands
alone), so a Core script cannot reach it.

Safety. The working set is written under an investigation id of its own (`bench-reader-view-...`)
and cleared when the run ends, even on an error. It writes nothing else. Run it against a Valkey
nothing else is using: a timing taken under another load is not a measurement of this one
(`process/CLAUDE.md` rule 14).
"""

from __future__ import annotations

import argparse
import asyncio
import statistics
import sys
import time
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from services.api.config import ValkeyConfig
from services.api.working_set.access_index import (
    AccessCounts,
    AccessEntries,
    IndexState,
    signature_id,
    signature_of,
)
from services.api.working_set.models import MAX_EDGES, MAX_NODES, DeltaAdd
from services.api.working_set.service import WorkingSetService
from services.api.working_set.store import ValkeyWorkingSetStore
from valkey.asyncio import Valkey

from ontology.handling import load_uk_le_scheme, principal_may_read
from ontology.loader import load_default_ontology
from schemas.domain import (
    AuditStub,
    Edge,
    EdgeId,
    ExpandRequest,
    Handling,
    Node,
    NodeId,
    Principal,
    Provenance,
    ProvenanceState,
    SourceRef,
    Subgraph,
)

PREFIX = "bench-reader-view-"
WHEN = datetime(2026, 1, 1, tzinfo=UTC)
READER = Principal(id="bench-reader", clearance="OFFICIAL", org_unit="unit-1")
#: One node in this many is above the reader's clearance, and so is the link to it.
HIDDEN_EVERY = 100


def _provenance() -> Provenance:
    return Provenance(
        state=ProvenanceState.ASSERTED,
        sources=[SourceRef(document_id="doc-1", locator="p.1", excerpt_hash="a" * 64)],
        first_seen=WHEN,
    )


def _handling(classification: str) -> Handling:
    return Handling(
        classification=classification, handling_code="P", originator="unit-1", owning_unit="unit-1"
    )


def make_node(index: int) -> Node:
    classification = "SECRET" if index % HIDDEN_EVERY == 0 else "OFFICIAL"
    return Node(
        id=f"n{index:07d}",
        type="Person",
        properties={"family_name": f"Name{index}"},
        provenance=_provenance(),
        handling=_handling(classification),
        audit=AuditStub(created_at=WHEN, created_by="bench"),
    )


def make_edge(index: int, source: int, target: int) -> Edge:
    return Edge(
        id=f"e{index:08d}",
        type="ASSOCIATE_OF",
        source=f"n{source:07d}",
        target=f"n{target:07d}",
        provenance=_provenance(),
        handling=_handling("OFFICIAL"),
        audit=AuditStub(created_at=WHEN, created_by="bench"),
    )


class _MemoryStore:
    """What the service reads and writes, from dictionaries; the index is `IndexState`, the same
    logic the Valkey store's scripts are written to."""

    def __init__(self) -> None:
        self.nodes: dict[NodeId, Node] = {}
        self.edges: dict[EdgeId, Edge] = {}
        self.index = IndexState()
        self.seq = 0

    async def current_seq(self, investigation_id: str) -> int:
        return self.seq

    async def next_seq(self, investigation_id: str) -> int:
        self.seq += 1
        return self.seq

    async def access_counts(self, investigation_id: str) -> AccessCounts:
        return self.index.counts()

    async def access_entries(
        self, investigation_id: str, node_ids: Sequence[NodeId], edge_ids: Sequence[EdgeId]
    ) -> AccessEntries:
        return self.index.entries(list(node_ids), list(edge_ids))

    async def stored_node_signatures(self, investigation_id: str) -> dict[NodeId, str]:
        return dict(self.index.index.nodes)

    async def add_nodes(self, investigation_id: str, nodes: Sequence[Node]) -> None:
        self.nodes.update({n.id: n for n in nodes})
        for n in nodes:
            signature = signature_of(n.handling, n.datasets)
            self.index.set_node(n.id, signature_id(signature), signature)
        self.index.written("bench")

    async def add_edges(self, investigation_id: str, edges: Sequence[Edge]) -> None:
        self.edges.update({e.id: e for e in edges})
        for e in edges:
            signature = signature_of(e.handling, e.datasets)
            self.index.set_edge(e.id, signature_id(signature), signature, e.source, e.target)
        self.index.written("bench")

    async def source_fidelity_nodes(self, investigation_id: str) -> dict[NodeId, Node]:
        return dict(self.nodes)

    async def source_fidelity_edges(self, investigation_id: str) -> dict[EdgeId, Edge]:
        return dict(self.edges)

    async def node_ids(self, investigation_id: str) -> set[NodeId]:
        return set(self.nodes)

    async def edge_ids(self, investigation_id: str) -> set[EdgeId]:
        return set(self.edges)

    async def remove_nodes(self, investigation_id: str, node_ids: Sequence[NodeId]) -> None:
        for node_id in node_ids:
            self.nodes.pop(node_id, None)
            self.index.remove_node(node_id)
        self.index.written("bench")

    async def remove_edges(self, investigation_id: str, edge_ids: Sequence[EdgeId]) -> None:
        for edge_id in edge_ids:
            self.edges.pop(edge_id, None)
            self.index.remove_edge(edge_id)
        self.index.written("bench")

    async def append_delta(self, investigation_id: str, delta: Any) -> None:
        return None

    async def clear(self, investigation_id: str) -> None:
        self.nodes.clear()
        self.edges.clear()
        self.index = IndexState()


class _StubGraph:
    """A preview of one node reads a small neighbourhood: `neighbours` nodes, some already in the
    working set and some new, and a link to each. An expansion (`new_nodes` set) returns that many
    nodes not in the working set, different on every call, and a link to each."""

    def __init__(self, nodes: int, neighbours: int = 30, new_nodes: int = 0) -> None:
        self.nodes, self.neighbours, self.new_nodes = nodes, neighbours, new_nodes
        self.calls = 0
        #: What a restore's by-id reads find (`--restore` fills these with the case's own bodies:
        #: the Vault holds what the working set holds).
        self.vault_nodes: dict[str, Node] = {}
        self.vault_edges: dict[str, Edge] = {}
        self._scheme = load_uk_le_scheme()

    async def get_nodes(self, node_ids: Sequence[str], principal: Principal) -> list[Node]:
        found = (self.vault_nodes.get(i) for i in sorted(set(node_ids)))
        return [
            n
            for n in found
            if n is not None and principal_may_read(n.handling, n.datasets, principal, self._scheme)
        ]

    async def get_edges(self, edge_ids: Sequence[str], principal: Principal) -> list[Edge]:
        found = (self.vault_edges.get(i) for i in sorted(set(edge_ids)))
        return [
            e
            for e in found
            if e is not None
            and principal_may_read(e.handling, e.datasets, principal, self._scheme)
            and e.source in self.vault_nodes
            and e.target in self.vault_nodes
            and principal_may_read(
                self.vault_nodes[e.source].handling,
                self.vault_nodes[e.source].datasets,
                principal,
                self._scheme,
            )
            and principal_may_read(
                self.vault_nodes[e.target].handling,
                self.vault_nodes[e.target].datasets,
                principal,
                self._scheme,
            )
        ]

    async def expand(self, req: ExpandRequest, principal: Principal) -> Subgraph:
        if self.new_nodes:
            self.calls += 1
            first = self.nodes + 10 + self.calls * self.new_nodes
            ids = list(range(first, first + self.new_nodes))
            # Each new node with a link to a node already in the working set.
            return Subgraph(
                nodes=[make_node(i + 1) for i in ids],
                edges=[make_edge(20_000_000 + i, i + 1, (i * 7 + 1) % self.nodes) for i in ids],
            )
        base = int(req.node_ids[0][1:]) if req.node_ids else 0
        ids = [(base + step * 977) % (self.nodes + 5) for step in range(self.neighbours)]
        return Subgraph(
            nodes=[make_node(i + 1) for i in ids],  # +1: never a hidden node, which is every 100th
            edges=[make_edge(10_000_000 + i, i + 1, (i * 7 + 1) % self.nodes) for i in ids],
        )

    async def edges_among(self, node_ids: Sequence[str], principal: Principal) -> list[Edge]:
        return []


async def _fill(store: Any, nodes: int, edges: int) -> float:
    started = time.monotonic()
    for start in range(0, nodes, 5_000):
        await store.add_nodes(
            "bench", [make_node(i) for i in range(start, min(start + 5_000, nodes))]
        )
    for start in range(0, edges, 5_000):
        await store.add_edges(
            "bench",
            [
                make_edge(i, i % nodes, (i * 7 + 1) % nodes)
                for i in range(start, min(start + 5_000, edges))
            ],
        )
    return time.monotonic() - started


async def run(args: argparse.Namespace) -> int:
    client: Valkey | None = None
    store: Any
    if args.store == "valkey":
        client = Valkey(**ValkeyConfig.from_env().client_kwargs())
        store = ValkeyWorkingSetStore(client)
    else:
        store = _MemoryStore()
    case = f"{PREFIX}{uuid.uuid4().hex[:8]}"
    branched = f"{case}-branch"
    if args.forward:
        # Each delta adds a node: stay under the node cap, or the recount measured is a refusal's.
        room = MAX_NODES - args.deltas - 10
        if args.nodes > room:
            args.nodes = room
            print(f"loading {args.nodes:,} nodes, to stay under the cap")
    if args.expand or args.branch or args.restore:
        # The write-cost step adds 500 nodes and 500 links first, and each expansion 500 more; leave
        # room under the caps for all of them, or the first refusal ends the run (it would be the
        # measurement of a refusal, not of what was asked for).
        room_nodes = MAX_NODES - 500 * (args.menus + 2)
        room_edges = MAX_EDGES - 500 * (args.menus + 2)
        if args.nodes > room_nodes or args.edges > room_edges:
            args.nodes, args.edges = min(args.nodes, room_nodes), min(args.edges, room_edges)
            print(f"loading {args.nodes:,} nodes and {args.edges:,} links, to stay under the caps")
    link_types = [e.name for e in load_default_ontology().edge_types]
    requests = [ExpandRequest(node_ids=["n0000001"], depth=1)] + [
        ExpandRequest(node_ids=["n0000001"], depth=1, edge_types=[t]) for t in link_types
    ]
    try:

        class _Case:
            """The store, with every call under this run's own case id."""

            def __getattr__(self, name: str) -> Any:
                inner = getattr(store, name)

                async def call(investigation_id: str, *rest: Any) -> Any:
                    # A case this run made (a branch's) is its own; everything else is `case`.
                    own = investigation_id if investigation_id.startswith(PREFIX) else case
                    return await inner(own, *rest)

                return call

        scoped = _Case()
        loaded = await _fill(scoped, args.nodes, args.edges)
        print(
            f"loaded {args.nodes:,} nodes and {args.edges:,} links in {loaded:.1f} s ({args.store})"
        )
        graph = _StubGraph(args.nodes, new_nodes=500 if args.expand else 0)
        service = WorkingSetService(graph, scoped, load_uk_le_scheme())  # type: ignore[arg-type]

        # What the reader's figures are computed from: small whatever the case holds.
        started = time.monotonic()
        counts = await scoped.access_counts(case)
        counts_read = time.monotonic() - started
        print(
            f"counts read: {counts_read * 1000:,.1f} ms ({len(counts.signatures)} signatures, "
            f"{len(counts.edge_counts)} link triples)"
        )

        # What a write costs: 500 new nodes and a link from each to a node already there, through
        # the store's own write (the script, on Valkey): the cost of a case's change to the index.
        first = args.nodes + 1_000_000
        new_nodes = [make_node(first + i) for i in range(500)]
        new_edges = [
            make_edge(30_000_000 + i, first + i, (i * 7 + 1) % args.nodes) for i in range(500)
        ]
        started = time.monotonic()
        await scoped.add_nodes(case, new_nodes)
        nodes_written = time.monotonic() - started
        started = time.monotonic()
        await scoped.add_edges(case, new_edges)
        edges_written = time.monotonic() - started
        print(
            "write cost, 500 nodes then 500 links through the store: "
            f"{nodes_written * 1000:,.0f} ms and {edges_written * 1000:,.0f} ms"
        )

        async def change(round_number: int) -> None:
            """A write to the store: a version moved, so what a reader is shown is recounted."""
            await scoped.add_nodes(case, [make_node(args.nodes + 1 + round_number)])

        def longest_script() -> str:
            runs = getattr(store, "script_runs", [])
            if not runs:
                return "no scripts (the memory store has none)"
            name, elements, seconds = max(runs, key=lambda run: run[2])
            return (
                f"{len(runs)} scripts, the longest {seconds * 1000:,.0f} ms "
                f"({name}, {elements} elements); the most elements in one: "
                f"{max(run[1] for run in runs)}"
            )

        if args.forward:
            readers = [
                READER.model_copy(update={"id": f"bench-reader-{i}"}) for i in range(args.sockets)
            ]
            worst_per_delta: list[float] = []
            every: list[float] = []
            for step in range(args.deltas):
                added = make_node(args.nodes + 1 + step + (step % HIDDEN_EVERY == 0))
                await scoped.add_nodes(case, [added])
                pushed = DeltaAdd(seq=step + 1, nodes=[added])

                async def recount(reader: Principal, pushed: DeltaAdd = pushed) -> float:
                    projected = service.project_delta(pushed, reader)
                    began = time.monotonic()
                    await service.over_cap_after(case, projected, reader)
                    return time.monotonic() - began

                took = await asyncio.gather(*(recount(r) for r in readers))
                every.extend(took)
                worst_per_delta.append(max(took))
            print(
                f"forward recount, {args.sockets} sockets, {args.deltas} deltas on "
                f"{args.nodes:,} nodes: per delta, median "
                f"{statistics.median(worst_per_delta) * 1000:,.1f} ms and worst "
                f"{max(worst_per_delta) * 1000:,.1f} ms (the slowest socket's); over every "
                f"socket and delta, median {statistics.median(every) * 1000:,.1f} ms and worst "
                f"{max(every) * 1000:,.1f} ms"
            )
            return 0

        if args.branch or args.restore:
            # What the working set does in bulk: a branch writes the whole visible case into a new
            # one; a restore writes a step's whole membership over the current one. Each is chunked,
            # and the point is the longest single script, which is how long Valkey is held.
            if hasattr(store, "script_runs"):
                store.script_runs.clear()
            started = time.monotonic()
            if args.branch:
                outcome = await service.branch(case, branched, READER)
                label = (
                    f"branch of the whole case into a new one ({len(outcome.delta.nodes):,} nodes)"
                )
            else:
                held_nodes = list((await scoped.source_fidelity_nodes(case)).values())
                held_edges = list((await scoped.source_fidelity_edges(case)).values())
                graph.vault_nodes = {n.id: n for n in held_nodes}
                graph.vault_edges = {e.id: e for e in held_edges}
                if hasattr(store, "script_runs"):
                    store.script_runs.clear()
                started = time.monotonic()
                snapshot = (await service.restore(case, held_nodes, held_edges, READER)).response
                label = f"restore of the whole case over itself ({len(snapshot.nodes):,} nodes)"
            elapsed = time.monotonic() - started
            print(f"{label}: {elapsed:,.1f} s; {longest_script()}")
            return 0

        if args.expand:
            expands: list[float] = []
            for _ in range(args.menus):
                started = time.monotonic()
                outcome = await service.expand(case, requests[0], READER)
                expands.append(time.monotonic() - started)
                assert len(outcome.delta.nodes) == 500
            expand_ms = statistics.median(expands) * 1000
            print(
                f"expand of 500 new nodes, end to end (store writes included): median "
                f"{expand_ms:,.0f} ms, worst {max(expands) * 1000:,.0f} ms over {len(expands)}"
            )
            print(f"target <= 800 ms: {'met' if expand_ms <= 800 else 'NOT MET'}")
            return 0

        firsts: list[float] = []
        menus: list[float] = []
        each: list[float] = []
        for round_number in range(args.menus):
            await change(round_number)
            if args.concurrent:
                # The sixteen at once after a change: every preview started together.
                started = time.monotonic()
                await asyncio.gather(*(service.expand_preview(case, r, READER) for r in requests))
                firsts.append(time.monotonic() - started)
                started = time.monotonic()
                await asyncio.gather(*(service.expand_preview(case, r, READER) for r in requests))
                menus.append(time.monotonic() - started)
                continue
            started = time.monotonic()
            await service.expand_preview(case, requests[0], READER)
            firsts.append(time.monotonic() - started)
            started = time.monotonic()
            for request in requests:
                one = time.monotonic()
                await service.expand_preview(case, request, READER)
                each.append(time.monotonic() - one)
            menus.append(time.monotonic() - started)
        first_ms = statistics.median(firsts) * 1000
        menu_ms = statistics.median(menus) * 1000
        if args.concurrent:
            print(
                f"a menu of {len(requests)} previews sent at once after a change (cold): median "
                f"{first_ms:,.0f} ms, worst {max(firsts) * 1000:,.0f} ms over {len(firsts)}"
            )
            print(
                f"the same {len(requests)} sent at once again (warm): median "
                f"{menu_ms:,.0f} ms, worst {max(menus) * 1000:,.0f} ms"
            )
        else:
            print(
                f"first preview after a change (cold): median {first_ms:,.0f} ms, "
                f"worst {max(firsts) * 1000:,.0f} ms over {len(firsts)}"
            )
            print(
                f"one radial menu ({len(requests)} previews), warm: "
                f"median {menu_ms:,.0f} ms, worst {max(menus) * 1000:,.0f} ms"
            )
            print(
                f"one warm preview: median {statistics.median(each) * 1000:,.1f} ms, "
                f"worst {max(each) * 1000:,.1f} ms"
            )
        print(
            f"targets ({args.nodes:,} nodes, {args.edges:,} links): cold preview <= 500 ms: "
            f"{'met' if first_ms <= 500 else 'NOT MET'}"
        )
    finally:
        await store.clear(case)
        await store.clear(branched)
        if client is not None:
            await client.aclose()
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--nodes", type=int, default=50_000)
    parser.add_argument("--edges", type=int, default=250_000)
    parser.add_argument("--menus", type=int, default=3, help="radial menus to time")
    parser.add_argument("--store", choices=("valkey", "memory"), default="valkey")
    parser.add_argument(
        "--concurrent", action="store_true", help="send a menu's previews at once, cold and warm"
    )
    parser.add_argument(
        "--expand", action="store_true", help="time a 500-node expansion end to end"
    )
    parser.add_argument(
        "--branch",
        action="store_true",
        help="time a branch of the whole case, and its longest script",
    )
    parser.add_argument(
        "--restore",
        action="store_true",
        help="time a restore of the whole case, and its longest script",
    )
    parser.add_argument(
        "--forward",
        action="store_true",
        help="time the live forward's recount of the reader's view per pushed delta",
    )
    parser.add_argument("--sockets", type=int, default=6, help="simulated readers for --forward")
    parser.add_argument("--deltas", type=int, default=100, help="pushed additions for --forward")
    args = parser.parse_args(argv)
    return asyncio.run(run(args))


if __name__ == "__main__":
    sys.exit(main())
