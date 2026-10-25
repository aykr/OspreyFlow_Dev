"""The Prison Intelligence Dataset against a real ArcadeDB (the throwaway one): what the demo
analyst can and cannot see of the one `SECRET` link, and the figures the script quotes (ADR-120 D4
to D9 and Amendments 7 to 12; ADR-123; Brief 1 stage 5 unit 5c).

**Live, and slow.** Every store is a fresh database loaded from the plan itself (`pid_writes`
through `scripts.seed_support.write_graph`, `method="bulk"`, chunks of 100), with the composed
ontology (core and NIEM) and the UK handling scheme, `arcadedb_adapter` directly and not
`GRAPH_PORT_ADAPTERS`, whose factory composes the core only and would refuse the pack's types.
`now_utc` is pinned where the adapter and the bulk loader import it, to the load day
(2026-05-01 at 09:00 UTC), and only while a store is loading, so no later store inherits an earlier
one's patches. Pictures go through the real `EntityPictureService.set` with `InMemoryMediaStore`,
the fake working-set store `test_entity_pictures.py` uses, and the graph wrapped in `stamping`
with the two datasets registered, one by one: about 1,600 of them for each store that holds them,
which is most of this module's time.

The stores:

- **A** chapter 4 with the `SECRET` link; **B** chapter 4 without it; **C** the seed moment with it.
  Pictures are loaded into each (see `PICTURE_STORES`).
- **A1 / B1** as A and B under weights version 1, with no pictures.
- **P1 to P3** only the Amendment 7 circle's links and their end nodes (`pid_writes.circle_writes`),
  at chapter 4, with no pictures, each under one planted wrong rule: `TRANSACTED` heavy 60,
  `SHARED_CELL_WITH` heavy 1, `COMMUNICATED_WITH` heavy 4,000. A planted rule is version 3 with one
  rule changed, put in force by pointing `adapters.graph_arcadedb.adapter.load_weight_rules` at it,
  as the conformance suite does for a version. From weights version 2 a link's weight depends on
  the link alone, so its stored weight in a circle-only store is what a full load gives it.

Two principals read: the **analyst** (`OFFICIAL`, no restricted codes, both datasets) and the
**cleared** one (`SECRET`, otherwise the same).

What each test proves, and what shows it red:

- **No trace** (rule 3, Amendment 13): for the analyst, A and B are identical in every reading the
  Glass shows over the link's two ends (`_observe` lists them: expands, statistics, degrees, the
  busiest links, links among, link structure, shared contacts, recent loads, type counts, routes,
  the path search and connections, the service's expand and per-type previews, a pattern's preview
  and run, links among at degrees 1 to 3, the shared pair's canvas, search, suggest and the
  starter questions, the export manifest, the centralities and the communities). There is no
  withheld count left to differ (`filtered_count` was removed, ADR-124 U2c), and the previews'
  candidate counts, which were counted over the stored set, are equal for the analyst in A and B,
  in a case the cleared principal has worked in too. The export manifest carries a yes or no
  (`withheld`, U9) that is true in A and false in B for the analyst in a shared case, pinned by
  `test_adr124_the_manifest_says_withheld_in_the_case_that_holds_the_secret_link`. *Red twice:* the
  same comparison for the cleared principal finds exactly the readings in `CLEARED_DIFFERS`, and
  under weights version 1 (A1 against B1) only the readings that carry a weight differ.
- **J1, J2, J5, J7** and the **229** reports, the **inferred** `PASSES_ITEMS_TO` links: the figures
  the script quotes, each from the store, with the analyst's and the cleared principal's where they
  differ.
- **Amendment 7's circle** at three points (as stored; recomputed by the store's own
  `compute_weight` from the stored components, under the version their `parameter_set` names, at
  the cut-off 30 April 2026 23:59:59 UTC; the same with every dated end far in the past) in A and
  C. *Red:* each plant, P1 to P3, fails at all three points, and for its own reason (the transfers,
  the one-week share, the call), with its stored weights moving the way the rule says.

**No unbounded search.** "Not connected" (J5) is proved only to length 3. An unbounded search over
the whole case enumerates every simple path, and a heavy query keeps running on the server after
its client gives up (rule 14). No test here calls `paths`, or `find_connections` with no degree,
for the unconnected prisoner.

**Budget.** The module is meant to run in under 30 minutes on the throwaway stack; each store
prints how long it took to load.
"""

from __future__ import annotations

import dataclasses
import math
import time
from collections import Counter
from collections.abc import AsyncIterator, Callable, Sequence
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from datetime import UTC, datetime
from datetime import time as clock_time
from typing import Any

import pytest
import pytest_asyncio
from scripts.seed_support import write_graph
from services.api.access import narrow_to_visible
from services.api.connections import find_connections
from services.api.dataset_scope import stamping
from services.api.datasets import Dataset, InMemoryDatasetStore
from services.api.entity_pictures import DEPICTS, EntityPictureService
from services.api.explore import ExploreService, TooManyMatches
from services.api.link_types import public_ontology
from services.api.patterns import preview_pattern, run_pattern
from services.api.search import SearchRequest, SuggestRequest, search, suggest
from services.api.working_set.models import MAX_EDGES, MAX_NODES, DeltaSnapshot
from services.api.working_set.service import WorkingSetService

from adapters.compute_rustworkx.adapter import ComputeRustworkxAdapter
from adapters.graph_arcadedb.testing import arcadedb_adapter
from adapters.graph_arcadedb.weight import compute_weight
from adapters.media_objectstore.testing import InMemoryMediaStore
from demo_fixtures import pid_plan, pid_writes
from demo_fixtures.datasets import PID, PID_SCALE
from demo_fixtures.pid_plan import Moment, node_id
from ontology.handling import load_uk_le_scheme
from ontology.packs import load_deployment_ontology
from ontology.weights import WeightRules, load_weight_history, load_weight_rules
from schemas.compute import CentralityRequest, CommunityRequest
from schemas.domain import (
    AuditStub,
    Connections,
    ConnectionsRequest,
    Edge,
    ExpandRequest,
    Node,
    NodeWrite,
    PathRequest,
    PatternEdge,
    PatternNode,
    PatternQuery,
    Principal,
    ProvenanceState,
    RoutesAtLength,
    Subgraph,
)
from tests.scenarios.test_pid_plan import View

from .working_set.fakes import FakeWorkingSetStore

pytestmark = pytest.mark.asyncio(loop_scope="module")

ONTOLOGY = load_deployment_ontology()
SCHEME = load_uk_le_scheme()
HISTORY = load_weight_history()
#: Every link type of the ontology the Glass can expand by.
LINK_TYPES = tuple(e.name for e in public_ontology(ONTOLOGY).edge_types if not e.system)

#: The load day: what `now_utc` returns while a store is written.
PINNED_NOW = datetime(2026, 5, 1, 9, 0, tzinfo=UTC)
#: Amendment 7 decision 2's second and third points: the intelligence cut-off (the plan's, at
#: 23:59:59 UTC), and every dated end far in the past (recency halves every 90 days and never
#: reaches 0).
CUT_OFF_INSTANT = datetime.combine(pid_plan.CUT_OFF, clock_time(23, 59, 59), tzinfo=UTC)
FAR_PAST = datetime(1900, 1, 1, tzinfo=UTC)
POINTS = ("as stored", "at the cut-off", "with every end far in the past")

#: The stores that get the plan's pictures through the picture route (Amendment 13 decision 4): the
#: cases with and without the `SECRET` link both carry them, so they differ only by the link, and C
#: carries them for J1. About 1,600 each, which is the largest part of the module's time. The stores
#: that exist for one comparison (A1, B1, P1 to P3) carry none.
PICTURE_STORES = frozenset({"A", "B", "C"})

CASE = "pid-case"
PAGE = 1_000
#: Routes asked for at one length. Far above any the case has; a store whose answer says `more`
#: fails the comparison loudly rather than compare a cut-off list.
ROUTE_LIMIT = 1_000
LOCAL = pid_plan.LOCAL_UNIT
BOTH_DATASETS = [PID.id, PID_SCALE.id]
ANALYST = Principal(
    id="pid-analyst", clearance="OFFICIAL", org_unit=LOCAL, datasets=list(BOTH_DATASETS)
)
CLEARED = Principal(
    id="pid-cleared", clearance="SECRET", org_unit=LOCAL, datasets=list(BOTH_DATASETS)
)

PRINCIPAL = node_id("principal")
COORDINATOR = node_id("number:coordinator")
RELAY_4 = node_id("relay_4")
UNCONNECTED = node_id("unconnected")
CALDER_3 = node_id("calder_3")

#: The three planted wrong rules (ADR-123 decision 6), each with the reason it must turn the circle
#: red: what it moves, and the place it pushes past its threshold.
PLANTS = (
    ("P1", "TRANSACTED", 60),
    ("P2", "SHARED_CELL_WITH", 1),
    ("P3", "COMMUNICATED_WITH", 4_000),
)

#: The links the amendment names, by (type, source key, target key), as the pure tests read them.
CALL = pid_writes.CIRCLE_CALL
TRANSFERS = pid_writes.CIRCLE_TRANSFERS
ONE_WEEK_SHARE = pid_writes.CIRCLE_ONE_WEEK_SHARE


# --- The plan, the stores and their loading ------------------------------------------------------


@pytest.fixture(scope="module")
def plan() -> Any:
    return pid_plan.build_plan("demo")


@dataclass
class Store:
    name: str
    graph: Any
    moment: Moment
    #: The rules the store wrote under when they are not the file's own: a planted rule, or a
    #: version chosen by index. `None`: the weights file's latest, found by each weight's
    #: `parameter_set`.
    rules: WeightRules | None
    #: Subject node id -> the id of the picture Document the route made for it.
    pictures: dict[str, str]
    #: Nodes written from the plan, pictures not counted.
    nodes: int
    plan: Any
    seconds: float
    observed: dict[str, Observation] = field(default_factory=dict)


def _chosen_rules(weights: int | WeightRules | None) -> WeightRules:
    if weights is None:
        return load_weight_rules()
    if isinstance(weights, int):
        rules = HISTORY[weights - 1]
        assert rules.version == weights
        return rules
    return weights


def _planted(link_type: str, heavy: int) -> WeightRules:
    """Weights version 3 with one counted rule's `heavy` changed."""
    rules = HISTORY[2]
    assert rules.version == 3
    wrong = dataclasses.replace(rules.rules[link_type], heavy=heavy)
    return dataclasses.replace(rules, rules={**rules.rules, link_type: wrong})


def _stub(write: NodeWrite) -> Node:
    """The working set's copy of a subject the route is asked to give a picture."""
    return Node(
        id=write.id,
        type=write.type,
        properties=write.properties,
        provenance=write.provenance,
        handling=write.handling,
        audit=AuditStub(created_at=PINNED_NOW, created_by=write.created_by),
        datasets=write.datasets,
    )


async def _attach_pictures(
    graph: Any, plan: Any, moment: Moment, nodes: Sequence[NodeWrite]
) -> dict[str, str]:
    """The pictures the plan holds by `moment`, through the real route: `EntityPictureService.set`
    over the graph wrapped in `stamping`, so each Document and `DEPICTS` link belongs to the case's
    dataset, and each picture carries its subject's own handling as the plan has it. Returns subject
    node id -> picture Document id."""
    registry = InMemoryDatasetStore()
    for seed in (PID, PID_SCALE):
        await registry.register(
            Dataset(
                id=seed.id, name=seed.name, owning_unit=LOCAL, created_at=PINNED_NOW,
                created_by=pid_writes.CREATED_BY,
            )
        )  # fmt: skip
    stamped = stamping(graph, dataset=PID.id, registry=registry)
    wanted = {
        node_id(lk.target)
        for lk in pid_plan.links_at(plan, moment, secret_cleared=True)
        if lk.link_type == "DEPICTS"
    }
    by_id = {n.id: n for n in nodes}
    working = FakeWorkingSetStore()
    await working.add_nodes(CASE, [_stub(by_id[i]) for i in sorted(wanted)])
    service = EntityPictureService(
        WorkingSetService(stamped, working, SCHEME),
        stamped,
        InMemoryMediaStore(),
        ONTOLOGY,
        scheme=SCHEME,
    )
    pictures: dict[str, str] = {}
    for subject, name, data in pid_writes.picture_writes(plan):
        if subject in wanted:
            result = await service.set(
                CASE, subject, ANALYST, name=name, data=data, handling=by_id[subject].handling
            )
            pictures[subject] = result.document_id
    assert set(pictures) == wanted, "a picture was not attached"
    assert len(set(pictures.values())) == len(pictures), "two subjects share one picture Document"
    return pictures


async def _open(
    stack: AsyncExitStack,
    plan: Any,
    name: str,
    moment: Moment,
    *,
    secret: bool = True,
    weights: int | WeightRules | None = None,
    circle_only: bool = False,
) -> Store:
    """A fresh database, loaded as the module's docstring says. The patches (the pinned clock, and
    the weights chosen) are undone before this returns, so a later store never inherits them; the
    database is dropped when `stack` closes."""
    started = time.monotonic()
    rules = _chosen_rules(weights)
    with pytest.MonkeyPatch.context() as patch:
        import adapters.graph_arcadedb.adapter as adapter_module
        import adapters.graph_arcadedb.bulk as bulk_module

        patch.setattr(adapter_module, "now_utc", lambda: PINNED_NOW)
        patch.setattr(bulk_module, "now_utc", lambda: PINNED_NOW)
        patch.setattr(adapter_module, "load_weight_rules", lambda: rules)
        graph = await stack.enter_async_context(arcadedb_adapter(ONTOLOGY, SCHEME))
        make = pid_writes.circle_writes if circle_only else pid_writes.writes
        nodes, edges = make(plan, moment, dataset=PID.id, created_at=PINNED_NOW)
        if not secret:
            edges = [e for e in edges if e.handling.classification != "SECRET"]
        await write_graph(
            graph, nodes, edges, chunk=100, nouns=("nodes", "links"),
            progress=lambda line: None, method="bulk",
        )  # fmt: skip
        pictures: dict[str, str] = {}
        if name in PICTURE_STORES:
            pictures = await _attach_pictures(graph, plan, moment, nodes)
    seconds = time.monotonic() - started
    print(
        f"PID-ACCESS store {name}: {len(nodes):,} nodes, {len(edges):,} links, "
        f"{len(pictures):,} pictures, loaded in {seconds:,.0f} s",
        flush=True,
    )
    return Store(
        name,
        graph,
        moment,
        None if weights is None else rules,
        pictures,
        len(nodes),
        plan,
        seconds,
    )


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def store_a(plan: Any) -> AsyncIterator[Store]:
    async with AsyncExitStack() as stack:
        yield await _open(stack, plan, "A", "chapter4")


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def store_b(plan: Any) -> AsyncIterator[Store]:
    async with AsyncExitStack() as stack:
        yield await _open(stack, plan, "B", "chapter4", secret=False)


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def store_c(plan: Any) -> AsyncIterator[Store]:
    async with AsyncExitStack() as stack:
        yield await _open(stack, plan, "C", "seed")


@pytest_asyncio.fixture(loop_scope="module")
async def store_a1(plan: Any) -> AsyncIterator[Store]:
    async with AsyncExitStack() as stack:
        yield await _open(stack, plan, "A1", "chapter4", weights=1)


@pytest_asyncio.fixture(loop_scope="module")
async def store_b1(plan: Any) -> AsyncIterator[Store]:
    async with AsyncExitStack() as stack:
        yield await _open(stack, plan, "B1", "chapter4", secret=False, weights=1)


@pytest_asyncio.fixture(loop_scope="module")
async def store_p1(plan: Any) -> AsyncIterator[Store]:
    async with AsyncExitStack() as stack:
        yield await _open(
            stack, plan, "P1", "chapter4", weights=_planted("TRANSACTED", 60), circle_only=True
        )


@pytest_asyncio.fixture(loop_scope="module")
async def store_p2(plan: Any) -> AsyncIterator[Store]:
    async with AsyncExitStack() as stack:
        yield await _open(
            stack, plan, "P2", "chapter4", weights=_planted("SHARED_CELL_WITH", 1),
            circle_only=True,
        )  # fmt: skip


@pytest_asyncio.fixture(loop_scope="module")
async def store_p3(plan: Any) -> AsyncIterator[Store]:
    async with AsyncExitStack() as stack:
        yield await _open(
            stack, plan, "P3", "chapter4", weights=_planted("COMMUNICATED_WITH", 4_000),
            circle_only=True,
        )  # fmt: skip


# --- What a principal reads: the comparison the no-trace test makes -------------------------------

Triple = tuple[str, str, str]

#: Page sizes. Links are paged larger: each page sorts every link the principal can see.
PAGE_LINKS = 2_000

#: Amendment 13 decisions 2 and 3: for the `SECRET`-cleared principal the two cases differ in
#: exactly these readings. The set is stated from reasoning over the code and the plan, offline,
#: before any run; a run that disagrees is investigated, never copied in. The one link joins the
#: principal and calder_3, and is the only link between them (the plan's only `SECRET` element;
#: every other handling is the default `P`, so nothing else gates a read). Entry by entry:
#: - principal_links, calder_links, stats, edges_among, link_structure, link_weights, paths: the
#:   link is one of each end's links, listed, counted, or (paths) a length-1 route.
#: - most_connected, busiest_global, busiest_around, type_counts, recent_loads: each counts or
#:   lists the link (a degree of each end +1, the totals +1, the load's links +1).
#: - conflict_weights: the cleared reader's `IN_CONFLICT_WITH` links are three, the analyst's two.
#: - betweenness: the working set holds both ends and, for the cleared reader, a direct link, so the
#:   pair no longer routes through est:fenwick-moor and its betweenness drops.
#: - service_expand, expand_preview: the principal's and calder_3's delta carries the link, and the
#:   view `_view` built already holds it for the cleared reader, so every preview's
#:   `candidate_edge_count` (the view's edges plus the new ones) is one higher in A, whatever the
#:   link type asked for.
#: - path_search: within two hops the analyst's case has one route (via est:fenwick-moor, two
#:   `HELD_AT` links) and the cleared reader's A has two (that one and the direct link), both under
#:   `k` 10, so nothing is cut and the routes themselves differ.
#: - connections: the fewest degrees are 1 for the cleared reader and 2 for the analyst's case.
#: - pattern_preview, pattern_run: the one-edge pattern from the principal matches his `IN_CONFLICT`
#:   targets, and `matched_count` is `len(subgraph.nodes)` (`patterns.py`), the principal included:
#:   4 in A against 3 in B, so the count and the nodes differ.
#: - links_among_1, _2, _3: over the two-node view the cleared reader's degree-1 call adds the link
#:   (1 against 0), and at degrees 2 and 3 the first length with a route is 1 in A (the direct link,
#:   no node added) and 2 in B (est:fenwick-moor and two `HELD_AT` links, one node added). The
#:   degree-3 outcome equals the degree-2 one in each case, because the search stops at the first
#:   length. The two share one neighbour (est:fenwick-moor, one route of two links), under
#:   `CONNECTIONS_SHOWN`, so `more_routes_pairs` is 0 throughout.
#: - shared_pair: the pair's canvas puts `edges_among` the two on the canvas: the link in A.
#: - centrality_degree, centrality_weighted_degree, centrality_pagerank: one more edge between two
#:   nodes of the working set moves every one (degrees +1, weights +w, the random walk).
#: - centrality_eigenvector, centrality_clustering_coefficient: GUESS that they move (the extra edge
#:   closes a triangle through est:fenwick-moor, which changes clustering, and moves the leading
#:   eigenvector); the graph holds odd cycles (principal, brother, establishment), so the
#:   eigenvector iteration should converge, and the analyst's reading is asserted not an error.
#: Not in the set, and why:
#: - shared_contacts: the walk lists b, where b has an `IN_CONFLICT_WITH` into a node the principal
#:   conflicts with (calder_1 and calder_2, and calder_3 for the cleared reader), and b is not the
#:   principal. The plan stores no such link from anyone else, so the list is empty in every case:
#:   the reading is vacuous, red under neither the cleared principal nor weights version 1.
#: - starter: the offered questions, and their order (busiest link types first), are the same in
#:   both: `IN_CONFLICT_WITH` ranks about fifteenth with 96 or 97 links and no neighbour ties. Total
#:   159 either way, and none of the six offered questions walks `IN_CONFLICT_WITH`; the chains
#:   over `COMMUNICATED_WITH` or `USES` match more than the run limit and are refused alike, and the
#:   one small chain (`USES` person to device, `PRESENT_AT` location) holds neither end.
#: - communities: GUESS that Louvain (seeded) gives one partition either way.
#: - expand_nodes (both ends are seeds, so both are in every union), weights (version 3: from the
#:   link alone), search and suggest (a name, not a link), export_withheld (over the reader's own
#:   view, 0 in both).
CLEARED_DIFFERS = frozenset(
    {
        "principal_links", "calder_links", "stats", "most_connected", "busiest_global",
        "busiest_around", "edges_among", "link_structure", "link_weights",
        "recent_loads", "type_counts", "paths", "conflict_weights", "betweenness",
        "service_expand", "expand_preview", "path_search", "connections", "pattern_preview",
        "pattern_run", "links_among_1", "links_among_2", "links_among_3", "shared_pair",
        "centrality_degree", "centrality_weighted_degree", "centrality_pagerank",
        "centrality_eigenvector", "centrality_clustering_coefficient",
    }
)  # fmt: skip
#: The readings that carry a link's weight: under weights version 1 these may differ, and only
#: these.
WEIGHT_READINGS = frozenset(
    {"weights", "conflict_weights", "link_weights", "centrality_weighted_degree"}
)


@dataclass(frozen=True)
class Observation:
    """Everything the no-trace comparison reads for one principal in one store (Amendment 13
    decision 2 and the coordinator's list of what the Glass shows). Each reading is comparable by
    `==`. Links are by (type, source id, target id): a link's own id is random in a store the route
    wrote to, and a node's id is the plan's derived one (a picture Document's is its content's),
    the same in every store.

    `weights` is every link any reading met, by triple, compared over the links both principals
    met."""

    readings: dict[str, Any]
    weights: dict[Triple, float]


def _triple(edge: Edge) -> Triple:
    return (edge.type, edge.source, edge.target)


async def _ranking(graph: Any, principal: Principal) -> tuple[int, dict[str, int]]:
    """Every node's degree, `most_connected` paged to `total` (never a first page taken for all)."""
    degrees: dict[str, int] = {}
    offset = 0
    while True:
        page = await graph.most_connected(principal, limit=PAGE, offset=offset)
        for ranked in page.nodes:
            degrees[ranked.node.id] = ranked.degree
        offset += len(page.nodes)
        if not page.nodes or offset >= page.total:
            assert len(degrees) == page.total, (
                f"{len(degrees)} nodes read of {page.total} ranked: a page was lost"
            )
            return page.total, degrees


async def _busiest_links(graph: Any, principal: Principal, **where: Any) -> tuple[int, list[Any]]:
    """The ranked links, paged to `total`."""
    found: list[Any] = []
    offset = 0
    while True:
        page = await graph.busiest_links(principal, limit=PAGE_LINKS, offset=offset, **where)
        found.extend(page.links)
        offset += len(page.links)
        if not page.links or offset >= page.total:
            assert len(found) == page.total, "a page of ranked links was lost"
            return page.total, found


def _ranked(found: tuple[int, list[Any]]) -> tuple[int, tuple[tuple[Triple, int], ...]]:
    total, links = found
    return total, tuple(sorted((_triple(r.edge), r.edge.occurrences) for r in links))


def _routes(found: RoutesAtLength) -> frozenset[tuple[tuple[str, ...], tuple[str, ...]]]:
    assert not found.more, f"more than {ROUTE_LIMIT} routes at length {found.length}"
    return frozenset(
        (tuple(n.id for n in p.nodes), tuple(e.type for e in p.edges)) for p in found.paths
    )


def _route_set(paths: Sequence[Any]) -> frozenset[tuple[tuple[str, ...], tuple[str, ...]]]:
    return frozenset((tuple(n.id for n in p.nodes), tuple(e.type for e in p.edges)) for p in paths)


def _shape(nodes: Sequence[Node], edges: Sequence[Edge]) -> tuple[frozenset[Any], frozenset[Any]]:
    """A set of nodes and links as the comparison reads them: ids and types, and triples."""
    return frozenset((n.id, n.type) for n in nodes), frozenset(_triple(e) for e in edges)


class _NoJobs:
    """`run_pattern` hands a pattern at its limit to a job; a one-edge pattern pinned to one
    person never reaches it, and a test that did would say so."""

    async def submit(self, job_type: str, payload: dict[str, Any]) -> str:
        raise AssertionError("the pattern should have run in the request")


async def _view(store: Store, principal: Principal) -> tuple[WorkingSetService, dict[str, Any]]:
    """A working set holding the principal and calder_3, built as the Glass builds it: by the real
    `WorkingSetService.expand` of each, one after the other."""
    service = WorkingSetService(store.graph, FakeWorkingSetStore(), SCHEME)
    outcomes = {}
    for seed in (PRINCIPAL, CALDER_3):
        outcomes[seed] = await service.expand(
            CASE, ExpandRequest(node_ids=[seed], depth=1), principal
        )
    return service, outcomes


async def _two_node_view(store: Store, principal: Principal) -> WorkingSetService:
    """A working set holding the principal and calder_3 and nothing else, as the Glass would after
    two searches: seeded through the service, not expanded, so the links among them are the only
    thing `links_among` can add at degree 1."""
    service = WorkingSetService(store.graph, FakeWorkingSetStore(), SCHEME)
    nodes = [await store.graph.get_node(i, principal) for i in (PRINCIPAL, CALDER_3)]
    assert all(n is not None for n in nodes), "both ends are visible to both readers"
    await service.seed(CASE, [n for n in nodes if n is not None], [], principal)
    return service


async def _observe(store: Store, principal: Principal) -> Observation:
    """The no-trace comparison's readings, once per store and principal."""
    if principal.id in store.observed:
        return store.observed[principal.id]
    started = time.monotonic()
    graph = store.graph
    readings: dict[str, Any] = {}
    weights: dict[Triple, float] = {}

    def note(edges: Sequence[Edge]) -> None:
        weights.update({_triple(e): e.weight for e in edges})

    # The graph's own depth-1 expands, statistics and the case-wide counts.
    expands = {}
    for seed in (PRINCIPAL, CALDER_3):
        found = await graph.expand(ExpandRequest(node_ids=[seed], depth=1), principal)
        assert len(found.edges) == len({e.id for e in found.edges})
        assert len(found.edges) == len({_triple(e) for e in found.edges}), (
            "two links of one type and pair"
        )
        note(found.edges)
        expands[seed] = found
    readings["expand_nodes"] = frozenset((n.id, n.type) for f in expands.values() for n in f.nodes)
    readings["principal_links"] = _shape([], expands[PRINCIPAL].edges)[1]
    readings["calder_links"] = _shape([], expands[CALDER_3].edges)[1]
    stats = [await graph.neighbourhood_stats(seed, principal) for seed in (PRINCIPAL, CALDER_3)]
    readings["stats"] = tuple((s.degree, tuple(sorted(s.degree_by_type.items()))) for s in stats)
    counts = await graph.type_counts(principal)
    readings["type_counts"] = (
        tuple(sorted(counts.nodes.items())),
        tuple(sorted(counts.edges.items())),
    )
    readings["most_connected"] = await _ranking(graph, principal)
    readings["busiest_global"] = _ranked(await _busiest_links(graph, principal))
    readings["busiest_around"] = _ranked(await _busiest_links(graph, principal, node_id=PRINCIPAL))
    conflicts = await _busiest_links(graph, principal, edge_type="IN_CONFLICT_WITH")
    readings["conflict_weights"] = {_triple(r.edge): r.edge.weight for r in conflicts[1]}
    readings["edges_among"] = frozenset(
        _triple(e) for e in await graph.edges_among([PRINCIPAL, CALDER_3], principal)
    )
    structure = await graph.link_structure(principal, max_nodes=MAX_NODES, max_edges=MAX_EDGES)
    readings["link_structure"] = (
        frozenset((n.id, n.type) for n in structure.nodes),
        tuple(sorted((e.source, e.target) for e in structure.edges)),
    )
    readings["link_weights"] = tuple(
        sorted((e.source, e.target, e.weight) for e in structure.edges)
    )
    shared = await graph.shared_contacts(
        PRINCIPAL, principal, edge_type="IN_CONFLICT_WITH", min_shared=1, limit=PAGE
    )
    readings["shared_contacts"] = (
        shared.total,
        tuple(sorted((c.node.id, c.shared) for c in shared.contacts)),
    )
    loads = await graph.recent_loads(principal, limit=PAGE)
    # `latest` is left out: the picture route stamps its Documents with the wall clock.
    readings["recent_loads"] = (
        loads.total,
        tuple(
            sorted(
                (
                    load.load_id or "", load.recipe_id or "", load.recipe_version or 0,
                    load.nodes, load.links,
                )
                for load in loads.loads
            )
        ),
    )  # fmt: skip
    readings["paths"] = {
        length: _routes(
            await graph.paths_at_length(PRINCIPAL, CALDER_3, length, ROUTE_LIMIT, principal)
        )
        for length in (1, 2, 3)
    }
    # Every centrality the compute adapter offers, and the communities, over a working set that
    # holds both ends: the two expansions' nodes, and the links among them as `narrow_to_visible`
    # leaves them. Nodes and links are sorted, so the two stores are given the same graph in the
    # same order (Louvain and the eigenvector iteration are sensitive to it).
    held = sorted({n.id for f in expands.values() for n in f.nodes})
    assert PRINCIPAL in held and CALDER_3 in held
    visible = await narrow_to_visible(graph, held, principal)
    held_graph = Subgraph(
        nodes=sorted(visible.nodes.values(), key=lambda n: n.id),
        edges=sorted(
            {e.id: e for e in visible.edges}.values(), key=lambda e: (*_triple(e), e.weight)
        ),
    )
    compute = ComputeRustworkxAdapter()
    readings["betweenness"] = await compute.centrality(
        CentralityRequest(subgraph=held_graph, metric="betweenness")
    )
    for metric in (
        "degree", "weighted_degree", "pagerank", "eigenvector", "clustering_coefficient",
    ):  # fmt: skip
        try:
            readings[f"centrality_{metric}"] = await compute.centrality(
                CentralityRequest(subgraph=held_graph, metric=metric)
            )
        except Exception as error:  # an iteration that does not converge is a reading too
            readings[f"centrality_{metric}"] = f"error: {type(error).__name__}"
    if principal.id == ANALYST.id:
        # A reading both cases share as an error would make their equality pass for nothing.
        for name, value in readings.items():
            assert not isinstance(value, str), (name, value)
    groups: dict[Any, set[str]] = {}
    for member, label in (await compute.communities(CommunityRequest(subgraph=held_graph))).items():
        groups.setdefault(label, set()).add(member)
    readings["communities"] = frozenset(frozenset(g) for g in groups.values())

    # The service the routes call: the real `WorkingSetService.expand` of each end (its delta and
    # `links_among` flag), and `expand_preview` for every link type the ontology has, from each end.
    service, outcomes = await _view(store, principal)
    # The export gate's withheld manifest over the working set the service just built.
    readings["export_withheld"] = await service.withheld_for(CASE, principal)
    readings["service_expand"] = {
        seed: (*_shape(o.delta.nodes, o.delta.edges), o.links_among) for seed, o in outcomes.items()
    }
    for seed, outcome in outcomes.items():
        note(outcome.delta.edges)
    previews: dict[tuple[str, str | None], Any] = {}
    for seed in (PRINCIPAL, CALDER_3):
        for link_type in (None, *LINK_TYPES):
            request = ExpandRequest(
                node_ids=[seed], depth=1, edge_types=None if link_type is None else [link_type]
            )
            preview = await service.expand_preview(CASE, request, principal)
            previews[(seed, link_type)] = (
                preview.candidate_node_count,
                preview.candidate_edge_count,
                preview.would_breach,
            )
    readings["expand_preview"] = previews

    # `/paths` (bounded to two hops) and `/connections`, principal to calder_3.
    found_paths = await graph.paths(
        PathRequest(source=PRINCIPAL, target=CALDER_3, max_hops=2, k=10), principal
    )
    for path in found_paths:
        note(path.edges)
    # At most two routes exist within two hops, under `k`, so none is cut and the routes
    # themselves are compared.
    assert len(found_paths) < 10
    readings["path_search"] = _route_set(found_paths)
    connection = await find_connections(
        graph, ConnectionsRequest(source=PRINCIPAL, target=CALDER_3), principal
    )
    for path in connection.paths:
        note(path.edges)
    readings["connections"] = (
        connection.degree,
        connection.searched_to,
        connection.more,
        _route_set(connection.paths),
    )

    # `/patterns/preview` and `/patterns/run`: a one-edge `IN_CONFLICT_WITH` pattern pinned to the
    # principal.
    pattern = PatternQuery(
        nodes=[
            PatternNode(var="a", entity_type="Person", node_id=PRINCIPAL),
            PatternNode(var="b", entity_type="Person"),
        ],
        edges=[PatternEdge(edge_type="IN_CONFLICT_WITH", from_var="a", to_var="b")],
        limit=100,
    )
    preview_of = await preview_pattern(pattern, graph=graph, principal=principal)
    readings["pattern_preview"] = (preview_of.estimated_count, preview_of.is_floor)
    ran = await run_pattern(pattern, graph=graph, principal=principal, jobs=_NoJobs())  # type: ignore[arg-type]
    assert ran.mode == "sync" and ran.subgraph is not None
    readings["pattern_run"] = (ran.matched_count, frozenset(n.id for n in ran.subgraph.nodes))

    # `links_among` at degrees 1, 2 and 3 over a view of the two ends alone, through the service
    # (its counts are readings too).
    for degree in (1, 2, 3):
        again = await _two_node_view(store, principal)
        among = await again.links_among(
            CASE, principal, node_ids=[PRINCIPAL, CALDER_3], degree=degree
        )
        note(among.delta.edges)
        readings[f"links_among_{degree}"] = (
            among.added, among.added_nodes, among.unconnected_pairs, among.more_routes_pairs,
            *_shape(among.delta.nodes, among.delta.edges),
        )  # fmt: skip

    # The shared-contacts canvas for the principal and calder_3.
    explore = ExploreService(graph, None)
    pair_nodes, pair_edges = await explore.shared_pair(
        principal, PRINCIPAL, CALDER_3, edge_type="IN_CONFLICT_WITH"
    )
    note(pair_edges)
    readings["shared_pair"] = _shape(pair_nodes, pair_edges)

    # `/search` and `/suggest` for calder_3's name (and the identifier search matches).
    person = store.plan.entity("calder_3").properties
    name, number = str(person["family_name"]), str(person["prison_number"])
    readings["search"] = {}
    for query in (name, number):
        hits = await search(graph, SearchRequest(query=query, limit=100), principal)
        readings["search"][query] = sorted(n.id for n in hits.nodes)
    suggested = await suggest(
        graph, SuggestRequest(query=name, mode="exact", ignore_case=True, limit=25), principal
    )
    readings["suggest"] = (sorted(n.id for n in suggested.nodes), suggested.more)

    # The starter questions on offer, and what each puts on the canvas.
    ontology = public_ontology(ONTOLOGY)
    offered = await explore.starter_questions(principal, ontology)
    ran_questions: dict[str, Any] = {}
    for question in offered.questions:
        try:
            nodes, edges = await explore.run_starter(principal, ontology, question.id)
            ran_questions[question.id] = _shape(nodes, edges)
        except TooManyMatches as refused:
            ran_questions[question.id] = f"too many matches: {refused}"
    readings["starter"] = (offered.total, tuple(q.id for q in offered.questions), ran_questions)

    observed = Observation(readings=readings, weights=weights)
    store.observed[principal.id] = observed
    print(
        f"PID-ACCESS observed {store.name} as {principal.id}: {time.monotonic() - started:,.0f} s",
        flush=True,
    )
    return observed


def _same_reading(name: str, left: Any, right: Any) -> bool:
    """Whether two stores' readings agree. A centrality reading (betweenness and the other
    centralities) is a node -> float map, compared by identical keys and `math.isclose` per node
    (`rel_tol=1e-9`, `abs_tol=1e-12`), not by `==`: rustworkx's `betweenness_centrality` runs in
    parallel above its `parallel_threshold` (default 50), and its float sums then vary from run to
    run by about 5e-17. Measured on one fixed 800-node graph: 19 of 19 repeat runs differed, and
    with `parallel_threshold=10**9` none of 19 did. That is not a leak. The cleared principal's real
    differences here are structural (an extra edge between two nodes moves a score by orders of
    magnitude more than the tolerance), so they still register. Everything else is compared by
    `==`."""
    if name == "betweenness" or name.startswith("centrality_"):
        if isinstance(left, dict) and isinstance(right, dict):
            return left.keys() == right.keys() and all(
                math.isclose(left[k], right[k], rel_tol=1e-9, abs_tol=1e-12) for k in left
            )
    return bool(left == right)


def _differences(a: Observation, b: Observation) -> list[str]:
    """The readings that differ, by name. Weights are compared over
    the links both principals met, so that a link only one of them met is a difference of the
    links, not of the weights."""
    assert a.readings.keys() == b.readings.keys()
    common = a.weights.keys() & b.weights.keys()
    out = [
        name for name in a.readings if not _same_reading(name, a.readings[name], b.readings[name])
    ]
    if {k: a.weights[k] for k in common} != {k: b.weights[k] for k in common}:
        out.append("weights")
    return out


# --- No trace of the SECRET link (rule 3) ---------------------------------------------------------


async def test_the_analyst_sees_no_trace_of_the_secret_link(store_a: Store, store_b: Store) -> None:
    """A holds the one `SECRET` link and B does not, and both carry the same pictures. For the
    `OFFICIAL` analyst every reading the Glass shows over this link's two ends is identical
    (Amendment 13 decision 2, widened): the depth-1 expands (nodes, links, weights) and
    neighbourhood statistics of the principal and calder_3; every node's degree; the busiest
    links, globally and around the principal, with their totals; the links among the two; the link
    structure; the shared contacts over `IN_CONFLICT_WITH`; the recent loads; the counts by type;
    the routes at lengths 1 to 3, the bounded path search and the connections; every
    `IN_CONFLICT_WITH` weight; betweenness and the other centralities over a working set holding
    both; the service's expand and its per-link-type previews; a one-edge pattern's preview and
    run; the links among at degrees 1, 2 and 3; and the shared pair's canvas. Everything but the
    expansion's withheld count and the status bar's, which are pinned below as a defect
    (ADR-124, accepted, option A′), not an allowance.

    **Readings neither proof can redden** (Amendment 13 decision 3): they are compared here, but
    neither the cleared principal nor weights version 1 changes them, so equality is no evidence
    the analyst is protected. `shared_contacts` (empty in every case: nobody but the principal
    has an `IN_CONFLICT_WITH` into his conflicts), `starter`, `communities` (a guess),
    `expand_nodes`, `search`, `suggest` and `export_withheld`.

    **Not covered, by design:** the Dossier (it renders the spans of an email's accepted
    extraction candidates, which this case does not have); the Reports view, history step
    summaries and hotlist or monitor alerts (the coordinator's list); ownership, KYC and risk walk
    other link types; histogram, cross-filter, geobins, first-seen, sightings, busiest-days and
    trends are Brief 2's, once its recipes load the events (this store loads none, Amendment 9
    decision 4)."""
    in_a = await _observe(store_a, ANALYST)
    in_b = await _observe(store_b, ANALYST)
    assert _differences(in_a, in_b) == []
    # The comparison read something: the principal's star, a ranking of every node, routes, the
    # visible conflict links, and a service expand that brought the star.
    assert len(in_a.readings["principal_links"]) == pid_plan.PRINCIPAL_LINK_COUNT
    total, degrees = in_a.readings["most_connected"]
    assert total == store_a.nodes + len(store_a.pictures)
    assert degrees[PRINCIPAL] == len(in_a.readings["principal_links"])
    routes = in_a.readings["paths"]
    assert routes[1] == frozenset(), "no direct link to calder_3 is visible"
    assert any(routes[length] for length in (2, 3)), "routes to calder_3 exist to compare"
    assert in_a.readings["conflict_weights"] and in_a.readings["edges_among"] == frozenset()
    assert in_a.readings["service_expand"][PRINCIPAL][1] >= in_a.readings["principal_links"]
    assert in_a.readings["busiest_global"][0] == sum(dict(in_a.readings["type_counts"][1]).values())
    assert len(in_a.readings["expand_preview"]) == 2 * (1 + len(LINK_TYPES))


async def test_the_analysts_own_snapshot_is_the_same_with_and_without_the_link(
    store_a: Store, store_b: Store
) -> None:
    """The `sync` projection (what the WebSocket and a reconnect send) of the analyst's own working
    set, after the service expanded both ends for the analyst: the same nodes and links. It carries
    no count of what is withheld (`filtered_count` was removed, ADR-124 U2c); the shared-case
    manifest's yes or no is pinned below."""
    snapshots = {}
    for store in (store_a, store_b):
        service, _ = await _view(store, ANALYST)
        (snapshot,) = await service.sync(CASE, ANALYST, last_acknowledged_seq=None)
        assert isinstance(snapshot, DeltaSnapshot)
        assert "filtered_count" not in snapshot.model_dump()
        snapshots[store.name] = _shape(snapshot.nodes, snapshot.edges)
    assert snapshots["A"] == snapshots["B"]


async def _shared_case(store: Store, reader: Principal = ANALYST) -> tuple[Any, ...]:
    """One `FakeWorkingSetStore` per store: the cleared principal expands the principal and
    calder_3 into it, then `reader` (the analyst, by default) `sync`s it (the shared-case path: a
    case several people work in) and the export gate's manifest is read for `reader`. Returns the
    snapshot's nodes and links, the manifest's `withheld` and the snapshot's `withheld`."""
    service, _ = await _view(store, CLEARED)
    (snapshot,) = await service.sync(CASE, reader, last_acknowledged_seq=None)
    assert isinstance(snapshot, DeltaSnapshot)
    manifest = await service.withheld_for(CASE, reader)
    return (*_shape(snapshot.nodes, snapshot.edges), manifest, snapshot.withheld)


async def _shared_previews(
    store: Store, reader: Principal = ANALYST
) -> dict[tuple[str, str | None], tuple[int, int, Any]]:
    """The previews `reader` is shown in the shared case: for each end and every link type, the
    candidate counts and any breach, over a working set the cleared principal built (ADR-124
    decision 2: counted over `reader`'s own view of it)."""
    service, _ = await _view(store, CLEARED)
    previews = {}
    for seed in (PRINCIPAL, CALDER_3):
        for link_type in (None, *LINK_TYPES):
            request = ExpandRequest(
                node_ids=[seed], depth=1, edge_types=None if link_type is None else [link_type]
            )
            preview = await service.expand_preview(CASE, request, reader)
            previews[(seed, link_type)] = (
                preview.candidate_node_count,
                preview.candidate_edge_count,
                preview.would_breach,
            )
    return previews


async def test_the_analysts_snapshot_of_a_shared_case_has_the_same_nodes_and_links(
    store_a: Store, store_b: Store
) -> None:
    """The cleared principal put the `SECRET` link in the working set; the analyst's snapshot of it
    holds the same nodes and links as in the case without the link. Shown red: the cleared
    principal's snapshot of the same two working sets differs by exactly the `SECRET` link."""
    in_a = await _shared_case(store_a)
    in_b = await _shared_case(store_b)
    assert in_a[:2] == in_b[:2]
    assert in_a[0], "the snapshot holds nodes to compare"
    cleared_a = await _shared_case(store_a, CLEARED)
    cleared_b = await _shared_case(store_b, CLEARED)
    assert cleared_a[0] == cleared_b[0]
    assert cleared_a[1] - cleared_b[1] == {("IN_CONFLICT_WITH", PRINCIPAL, CALDER_3)}
    assert cleared_b[1] - cleared_a[1] == frozenset()


async def test_the_expansion_and_preview_figures_are_the_same_with_and_without_the_link(
    store_a: Store, store_b: Store
) -> None:
    """ADR-124 decision 1, rewritten from the defect test
    `test_adr124_defect_the_expansion_count_leaks_the_secret_link`, which pinned the leak: the
    withheld count of an expansion or a preview was 1 with the `SECRET` link and 0 without, in six
    readings, and so located the link by its type and its two ends.
    There is no such count now: neither an expansion's outcome nor a preview has a field for one,
    and the previews' candidate counts, which were counted over the stored set, are equal for the
    analyst in A and B.

    **In the analyst's own case and in a case the cleared principal worked in.** In the first the
    analyst's expansions put nothing above them in the store, so equality is not yet a proof; the
    second is: the cleared principal's expansions put the `SECRET` link in A's store, and the
    analyst's preview of every type from each end is counted over their own view of it (a link
    counts only when it and both its ends are readable). *Shown red:* the cleared principal's
    previews of the same two stores differ by exactly that link."""
    from services.api.working_set.models import CardinalityPreview, ExpansionOutcome

    assert "filtered_count" not in ExpansionOutcome.model_fields
    assert "filtered_count" not in CardinalityPreview.model_fields

    in_a = await _observe(store_a, ANALYST)
    in_b = await _observe(store_b, ANALYST)
    assert in_a.readings["expand_preview"] == in_b.readings["expand_preview"]
    assert len(in_a.readings["expand_preview"]) == 2 * (1 + len(LINK_TYPES))

    shared_a = await _shared_previews(store_a)
    shared_b = await _shared_previews(store_b)
    assert shared_a == shared_b
    assert any(counts[1] > 0 for counts in shared_a.values()), "the previews counted links"

    cleared_a = await _shared_previews(store_a, CLEARED)
    cleared_b = await _shared_previews(store_b, CLEARED)
    for seed in (PRINCIPAL, CALDER_3):
        for link_type in (None, *LINK_TYPES):
            nodes_a, edges_a, _ = cleared_a[(seed, link_type)]
            nodes_b, edges_b, _ = cleared_b[(seed, link_type)]
            # The cleared reader's view holds the `SECRET` link whatever type is asked about, so
            # every preview of theirs counts it, and nothing else differs.
            assert nodes_a == nodes_b, (seed, link_type)
            assert edges_a - edges_b == 1, (seed, link_type)


async def test_adr124_the_manifest_says_withheld_in_the_case_that_holds_the_secret_link(
    store_a: Store, store_b: Store
) -> None:
    """Decision 9: the export manifest's `withheld` is true for the analyst in the case the cleared
    principal has worked in with the `SECRET` link present (A), and false in the case without it
    (B). It is a yes and never a number: U9 replaced the count, which was `(1, 0)` here until then.
    In a case shared with a cleared colleague, A′ deliberately tells the analyst that material is
    withheld, never what or where, so Brief 1 section 5.3 is met only in a case the analyst works
    alone.

    **Expected, reasoned before any run.** `withheld_for` reads the counted access index, which
    judges every stored element by its own handling. The cleared principal's expansions put the
    `SECRET` link in A's store and nothing above `OFFICIAL` in B's. Only classification and a
    restricted handling code gate a read (`ontology/handling.py`, `principal_may_view`), every
    handling code the plan gives is the default `P` (`PlanHandling` in `pid_plan.py`), and the one
    `SECRET` element is the link; calder_3 is readable. So: true in A, false in B."""
    in_a = await _shared_case(store_a)
    in_b = await _shared_case(store_b)
    print(f"PID-ACCESS shared-case manifest withheld: A {in_a[2]} B {in_b[2]}", flush=True)
    assert (in_a[2], in_b[2]) == (True, False)
    cleared_a = await _shared_case(store_a, CLEARED)
    cleared_b = await _shared_case(store_b, CLEARED)
    assert (cleared_a[2], cleared_b[2]) == (False, False)


async def test_adr124_the_snapshot_says_withheld_in_the_case_that_holds_the_secret_link(
    store_a: Store, store_b: Store
) -> None:
    """Decision 5 and U2c's text, made true by U5: in the case the cleared principal has worked in,
    the analyst's full snapshot carries `withheld` true (the one `SECRET` link is stored and above
    them) and in the case without it, false. It is a yes and never a number. The cleared principal,
    for whom nothing is above their clearance, is told false in both. The manifest's `withheld`
    above says the same of the manifest."""
    in_a = await _shared_case(store_a)
    in_b = await _shared_case(store_b)
    cleared_a = await _shared_case(store_a, CLEARED)
    cleared_b = await _shared_case(store_b, CLEARED)
    print(f"PID-ACCESS shared-case withheld: A {in_a[3]} B {in_b[3]}", flush=True)
    assert (in_a[3], in_b[3]) == (True, False)
    assert (cleared_a[3], cleared_b[3]) == (False, False)


async def test_the_comparison_can_see_the_secret_link_for_the_cleared_principal(
    store_a: Store, store_b: Store
) -> None:
    """Shown red (rule 15): the same comparison, run for a principal cleared to `SECRET`, finds
    the difference, in exactly the readings of `CLEARED_DIFFERS` (Amendment 13 decision 3; stated
    from reasoning, and a run that disagrees is investigated, not copied in). If it found none,
    the test above would prove nothing about the analyst."""
    in_a = await _observe(store_a, CLEARED)
    in_b = await _observe(store_b, CLEARED)
    differing = set(_differences(in_a, in_b))
    print(
        f"PID-ACCESS the cleared principal's A against B differ in: {sorted(differing)}",
        flush=True,
    )
    assert differing == CLEARED_DIFFERS, (
        sorted(differing - CLEARED_DIFFERS),
        sorted(CLEARED_DIFFERS - differing),
    )
    # The difference is the one link: calder_3 is one link away only for A's cleared reader.
    link = ("IN_CONFLICT_WITH", PRINCIPAL, CALDER_3)
    ra, rb = in_a.readings, in_b.readings
    assert ra["principal_links"] - rb["principal_links"] == {link}
    assert ra["calder_links"] - rb["calder_links"] == {link}
    assert rb["principal_links"] - ra["principal_links"] == frozenset()
    assert ra["edges_among"] == {link} and rb["edges_among"] == frozenset()
    assert ra["paths"][1] and not rb["paths"][1]
    assert ra["stats"][0][0] == rb["stats"][0][0] + 1
    assert ra["stats"][1][0] == rb["stats"][1][0] + 1
    assert ra["most_connected"][1][PRINCIPAL] == rb["most_connected"][1][PRINCIPAL] + 1
    assert ra["most_connected"][1][CALDER_3] == rb["most_connected"][1][CALDER_3] + 1
    assert ra["busiest_global"][0] == rb["busiest_global"][0] + 1
    assert ra["busiest_around"][0] == rb["busiest_around"][0] + 1
    assert ra["connections"][0] == 1 and rb["connections"][0] == 2


async def test_under_weights_version_1_the_analysts_link_weights_show_the_secret_link(
    store_a1: Store, store_b1: Store
) -> None:
    """Shown red (rule 15, ADR-123): under weights version 1, whose mutual-information term counts
    links the reader cannot see, the analyst's own links weigh differently with the `SECRET` link
    present, and only the readings that carry a weight differ. Under version 3 (the first test)
    nothing does."""
    in_a1 = await _observe(store_a1, ANALYST)
    in_b1 = await _observe(store_b1, ANALYST)
    differing = set(_differences(in_a1, in_b1))
    assert differing <= WEIGHT_READINGS, sorted(differing)
    assert {"weights", "conflict_weights"} <= differing, sorted(differing)
    moved = {
        link: (in_a1.weights[link], in_b1.weights[link])
        for link in in_a1.weights.keys() & in_b1.weights.keys()
        if in_a1.weights[link] != in_b1.weights[link]
    }
    print(
        f"PID-ACCESS version 1: {len(moved)} of the analyst's weights move, e.g. "
        f"{sorted(moved.values())[:3]}",
        flush=True,
    )
    assert all(link[0] == "IN_CONFLICT_WITH" for link in moved), moved


# --- J1: the principal's star ---------------------------------------------------------------------


async def _degree_by_ranking(store: Store, principal: Principal, wanted: str) -> int:
    """A person's degree as `most_connected` gives it, paging the people by degree until he is
    found (he is among the best connected, so this stops early)."""
    offset = 0
    while True:
        page = await store.graph.most_connected(
            principal, entity_type="Person", limit=100, offset=offset
        )
        for ranked in page.nodes:
            if ranked.node.id == wanted:
                return int(ranked.degree)
        offset += len(page.nodes)
        assert page.nodes and offset < page.total, f"{wanted} is not among the {page.total} people"


async def _all_depicts(store: Store) -> list[Any]:
    """Every `DEPICTS` link the analyst reads, with both ends, paged to `total`."""
    found: list[Any] = []
    offset = 0
    while True:
        page = await store.graph.busiest_links(ANALYST, edge_type=DEPICTS, limit=500, offset=offset)
        found.extend(page.links)
        offset += len(page.links)
        if not page.links or offset >= page.total:
            assert len(found) == page.total, "a page of DEPICTS links was lost"
            return found


async def _j1(store: Store, expected: int, by_type: dict[str, int]) -> None:
    stars: dict[str, Subgraph] = {}
    for principal, extra in ((ANALYST, 0), (CLEARED, 1)):
        star = await store.graph.expand(ExpandRequest(node_ids=[PRINCIPAL], depth=1), principal)
        assert len(star.edges) == len({e.id for e in star.edges})
        stars[principal.id] = star
        # The count "With all links" shows, and the degree the best-connected list gives him.
        assert len(star.edges) == expected + extra, (store.name, principal.id)
        assert await _degree_by_ranking(store, principal, PRINCIPAL) == expected + extra, (
            store.name,
            principal.id,
        )
        want = Counter(by_type) + Counter({"IN_CONFLICT_WITH": extra})
        assert Counter(e.type for e in star.edges) == want, (store.name, principal.id)
    # The real `DEPICTS` among them: his one picture, a link from the image Document the route made.
    star = stars[ANALYST.id]
    (depicts,) = [e for e in star.edges if e.type == "DEPICTS"]
    assert depicts.target == PRINCIPAL and depicts.source == store.pictures[PRINCIPAL]
    (document,) = [n for n in star.nodes if n.id == depicts.source]
    assert document.type == "Document" and document.properties["media_kind"] == "image"
    # Every `DEPICTS` joins one image Document to one entity, and each entity has one picture.
    links = await _all_depicts(store)
    assert len(links) == len(store.pictures) > 0
    sources: Counter[str] = Counter()
    targets: Counter[str] = Counter()
    for link in links:
        assert link.source.type == "Document", link.source.id
        assert link.source.properties.get("media_kind") == "image", link.source.id
        assert link.target.type != "Document", link.target.id
        # Every picture belongs to the case's dataset and carries its subject's own handling.
        for element in (link.edge, link.source):
            assert element.datasets == [PID.id], (element.id, element.datasets)
        assert link.source.handling == link.target.handling == link.edge.handling, link.source.id
        sources[link.source.id] += 1
        targets[link.target.id] += 1
    assert set(sources.values()) == {1}, "an image Document depicts more than one entity"
    assert set(targets.values()) == {1}, "an entity has more than one picture"
    assert set(targets) == set(store.pictures)
    assert set(sources) == set(store.pictures.values())


async def test_j1_the_principals_star_is_49_for_the_analyst_and_50_cleared_in_a_and_45_and_46_in_c(
    store_a: Store, store_c: Store
) -> None:
    """J1: the depth-1 expand's link count (what "With all links" shows) and the principal's
    `most_connected` degree agree, with his real picture link among them."""
    assert pid_plan.PRINCIPAL_LINK_COUNT_SECRET == pid_plan.PRINCIPAL_LINK_COUNT + 1
    assert pid_plan.PRINCIPAL_LINK_COUNT_ACT1_SECRET == pid_plan.PRINCIPAL_LINK_COUNT_ACT1 + 1
    await _j1(store_a, pid_plan.PRINCIPAL_LINK_COUNT, dict(pid_plan.PRINCIPAL_LINKS_BY_TYPE))
    await _j1(
        store_c,
        pid_plan.PRINCIPAL_LINK_COUNT_ACT1,
        {k: v for k, v in pid_plan.PRINCIPAL_LINKS_BY_TYPE.items() if k != "MENTIONED_IN"},
    )


# --- J2: the coordinator's number -----------------------------------------------------------------


async def test_j2_a_search_for_the_coordinators_number_finds_one_endpoint_with_four_pin_accounts(
    plan: Any, store_a: Store
) -> None:
    """J2: `services/api/search.py`'s search for `+447700900640` finds exactly one `Endpoint`, and
    four PIN accounts link to it (the principal's and three relays'). What the other written forms
    return is recorded, not asserted (the brief's VERIFY)."""
    graph = store_a.graph
    held = plan.entity("number:coordinator").properties
    number, national = str(held["value_normalised"]), str(held["value_raw"])
    found = await search(graph, SearchRequest(query=number), ANALYST)
    endpoints = [n for n in found.nodes if n.type == "Endpoint"]
    assert [n.id for n in endpoints] == [COORDINATOR]
    assert endpoints[0].properties["value_normalised"] == number
    print(
        f"PID-ACCESS J2 {number!r}: {len(found.nodes)} node(s), "
        f"{Counter(n.type for n in found.nodes)}",
        flush=True,
    )
    for written in ("+44 " + national[1:], national):
        other = await search(graph, SearchRequest(query=written), ANALYST)
        print(
            f"PID-ACCESS J2 VERIFY {written!r}: {len(other.nodes)} node(s), "
            f"{sorted((n.type, n.properties.get('value_normalised')) for n in other.nodes)}",
            flush=True,
        )
    key_of = {node_id(e.key): e.key for e in plan.entities}
    star = await graph.expand(
        ExpandRequest(node_ids=[COORDINATOR], depth=1, edge_types=["COMMUNICATED_WITH"]), ANALYST
    )
    callers = {
        key_of[e.source if e.target == COORDINATOR else e.target]
        for e in star.edges
        if COORDINATOR in (e.source, e.target)
    }
    pins = {key for key in callers if key.startswith("pin:")}
    assert pins == {"pin:principal", "pin:relay_1", "pin:relay_2", "pin:relay_3"}
    assert len(pins) == 4
    # Each of the four is used by a prisoner: a Person with a prison number.
    for pin in sorted(pins):
        used = await graph.expand(
            ExpandRequest(node_ids=[node_id(pin)], depth=1, edge_types=["USES"]), ANALYST
        )
        kinds = {n.id: n for n in used.nodes}
        users = [
            kinds[e.source]
            for e in used.edges
            if e.target == node_id(pin) and kinds[e.source].type == "Person"
        ]
        assert users and all("prison_number" in u.properties for u in users), pin


# --- J5: two degrees and six routes; and no route at all ------------------------------------------


async def _j5(store: Store, routes: int) -> None:
    request = ConnectionsRequest(source=PRINCIPAL, target=RELAY_4)
    found: Connections = await find_connections(store.graph, request, ANALYST)
    assert found.degree == pid_plan.PAIR_DEGREES == 2, store.name
    assert len(found.paths) == routes and not found.more, store.name
    assert {p.length for p in found.paths} == {2}
    # The prisoner with no route: none at length 1, 2 or 3, for either reader, and NO unbounded
    # search, which on this store would enumerate every simple path of a whole component.
    for principal in (ANALYST, CLEARED):
        for length in (1, 2, 3):
            none = await store.graph.paths_at_length(
                PRINCIPAL, UNCONNECTED, length, ROUTE_LIMIT, principal
            )
            assert none.paths == [] and not none.more, (store.name, principal.id, length)


async def test_j5_principal_and_relay_4_are_two_degrees_apart_by_6_routes_in_a_and_5_in_c(
    store_a: Store, store_c: Store
) -> None:
    await _j5(store_a, pid_plan.PAIR_ROUTES)
    await _j5(store_c, pid_plan.PAIR_ROUTES_ACT1)


# --- J7: who the working set turns on -------------------------------------------------------------


async def _j7(plan: Any, store: Store, expected: float) -> None:
    keys, links = pid_plan.j7_working_set(plan, store.moment)
    # The plan's picture Documents are written by the route, under ids of their own.
    picture_of = {
        lk.source: store.pictures[node_id(lk.target)]
        for lk in pid_plan.links_at(plan, store.moment, secret_cleared=True)
        if lk.link_type == "DEPICTS"
    }

    def stored(key: str) -> str:
        return picture_of.get(key) or node_id(key)

    ids = sorted({stored(k) for k in keys})
    visible = await narrow_to_visible(store.graph, ids, ANALYST)
    assert set(visible.nodes) == set(ids), "the working set is not what the plan says"
    edges = list({e.id: e for e in visible.edges}.values())
    assert {_triple(e) for e in edges} == {
        (lk.link_type, stored(lk.source), stored(lk.target)) for lk in links
    }
    centrality = await ComputeRustworkxAdapter().centrality(
        CentralityRequest(
            subgraph=Subgraph(nodes=list(visible.nodes.values()), edges=edges),
            metric="betweenness",
        )
    )
    ranked = sorted(centrality.items(), key=lambda kv: kv[1], reverse=True)
    assert ranked[0][0] == PRINCIPAL, store.name
    assert ranked[0][1] >= 2 * ranked[1][1], store.name
    assert {k for k, _ in ranked[1:4]} == {node_id(f"relay_{i}") for i in (1, 2, 3)}, store.name
    assert round(centrality[PRINCIPAL], 2) == expected, (store.name, centrality[PRINCIPAL])


async def test_j7_the_principal_ranks_first_by_betweenness_then_the_relays_in_a_and_c(
    plan: Any, store_a: Store, store_c: Store
) -> None:
    await _j7(plan, store_a, pid_plan.PRINCIPAL_BETWEENNESS)
    await _j7(plan, store_c, pid_plan.PRINCIPAL_BETWEENNESS_ACT1)


# --- The one pattern, and the inferred links ------------------------------------------------------


async def test_the_one_pattern_finds_229_reports(plan: Any, store_a: Store) -> None:
    """`REPORT_PATTERN` matches exactly the plan's 229 reports, and nothing is cut short (rule 2):
    `match_count`, with a ceiling far above the pattern's own `limit`, counts what `match` returns,
    and that is under the `limit`."""
    pattern = PatternQuery.model_validate(pid_plan.REPORT_PATTERN)
    wanted = View(plan).selected  # the plan test's own rule over the plan's links and dates
    assert len(wanted) == pid_plan.REPORTS_SELECTED
    for principal in (ANALYST, CLEARED):
        matched = await store_a.graph.match(pattern, principal)
        reports = {n.id for n in matched.nodes if n.type == "Document"}
        assert reports == {node_id(k) for k in wanted}, principal.id
        assert len(reports) == pid_plan.REPORTS_SELECTED
        counted = await store_a.graph.match_count(pattern, principal, ceiling=10 * pattern.limit)
        assert counted == len(matched.nodes), "match_count and match disagree about what matched"
        assert counted < pattern.limit, f"the pattern's limit of {pattern.limit} may have cut it"


async def test_passes_items_to_is_stored_inferred(plan: Any, store_a: Store) -> None:
    """D8's five links are model-derived, so they are stored `inferred` with who extracted them and
    how sure (rule 5): never asserted, whatever a reader's clearance."""
    wanted = [lk for lk in plan.links if lk.link_type == "PASSES_ITEMS_TO"]
    assert wanted
    seeds = sorted({node_id(k) for lk in wanted for k in (lk.source, lk.target)})
    for principal in (ANALYST, CLEARED):
        star = await store_a.graph.expand(
            ExpandRequest(node_ids=seeds, depth=1, edge_types=["PASSES_ITEMS_TO"]), principal
        )
        stored = {e.id: e for e in star.edges}
        assert len(stored) == len(wanted), principal.id
        assert {_triple(e) for e in stored.values()} == {
            ("PASSES_ITEMS_TO", node_id(lk.source), node_id(lk.target)) for lk in wanted
        }
        by_pair = {(node_id(lk.source), node_id(lk.target)): lk for lk in wanted}
        for edge in stored.values():
            want = by_pair[(edge.source, edge.target)]
            assert edge.provenance.state is ProvenanceState.INFERRED, edge.id
            assert edge.provenance.extracted_by == want.extracted_by is not None, edge.id
            assert edge.provenance.extraction_confidence == want.extraction_confidence
            assert edge.provenance.extraction_confidence is not None, edge.id
            assert edge.provenance.confirmed_by is None, "nobody has confirmed it"


# --- Amendment 7's circle -------------------------------------------------------------------------


async def _circle(store: Store, principal: Principal = ANALYST) -> list[Edge]:
    """The circle as the analyst reads it from the store: the principal's links, the links of each
    endpoint he uses, and the links of each endpoint those exchange calls or money with, each by
    `expand` from the ids found by the step before."""
    graph = store.graph
    first = await graph.expand(ExpandRequest(node_ids=[PRINCIPAL], depth=1), principal)
    kinds = {n.id: n.type for n in first.nodes}
    used = sorted(
        e.target
        for e in first.edges
        if e.type == "USES" and e.source == PRINCIPAL and kinds[e.target] == "Endpoint"
    )
    second = await graph.expand(ExpandRequest(node_ids=used, depth=1), principal)
    exchange: set[str] = set()
    for e in second.edges:
        if e.type in ("COMMUNICATED_WITH", "TRANSACTED"):
            if e.source in used:
                exchange.add(e.target)
            if e.target in used:
                exchange.add(e.source)
    centre = {PRINCIPAL, *used, *exchange}
    third = await graph.expand(ExpandRequest(node_ids=sorted(centre), depth=1), principal)
    return list({e.id: e for e in third.edges if e.source in centre or e.target in centre}.values())


def _the_stores_circle_is_the_plans(plan: Any, store: Store, edges: Sequence[Edge]) -> None:
    """What the store's circle must be before its weights say anything: the plan's circle, by id,
    with the principal's picture link where the store holds pictures and nowhere else."""
    _, links = pid_writes.circle_links(plan, store.moment)
    want = {
        (lk.link_type, node_id(lk.source), node_id(lk.target))
        for lk in links
        if lk.link_type != "DEPICTS"
    }
    assert {_triple(e) for e in edges if e.type != "DEPICTS"} == want, store.name
    pictures = [e for e in edges if e.type == "DEPICTS"]
    if store.pictures:
        assert [_triple(e) for e in pictures] == [
            ("DEPICTS", store.pictures[PRINCIPAL], PRINCIPAL)
        ], store.name
    else:
        assert pictures == [], store.name
    assert len(edges) == len(links) - (0 if store.pictures else 1), store.name


def _aware(value: datetime | None) -> datetime | None:
    return None if value is None else (value if value.tzinfo else value.replace(tzinfo=UTC))


def _rules_of(store: Store, edge: Edge) -> WeightRules:
    """The rules a stored weight was computed under: the planted ones for a plant, otherwise the
    version its `parameter_set` names."""
    assert edge.weight_components is not None, f"{edge.id} stores no weight components"
    named = edge.weight_components.parameter_set
    assert named is not None, f"{edge.id} stores no parameter_set"
    rules = store.rules or HISTORY[int(named.partition("/")[0]) - 1]
    assert rules.parameter_set(edge.type) == named, (edge.id, named, rules.parameter_set(edge.type))
    return rules


def _weights_at(store: Store, edges: Sequence[Edge]) -> dict[str, dict[str, float]]:
    """The circle's weights at the three points, by link id. The recomputed points use the store's
    own `compute_weight` on the stored components. Each recomputation is first shown to reproduce
    the stored weight from the stored components at the moment they were taken (rule 15), so the
    recomputation is the store's own and not an approximation of it."""
    stored: dict[str, float] = {}
    cut: dict[str, float] = {}
    past: dict[str, float] = {}
    for edge in edges:
        rules = _rules_of(store, edge)
        components = edge.weight_components
        assert components is not None
        valid_to = _aware(edge.interval.valid_to) if edge.interval else None
        loop = edge.source == edge.target

        def weight(now: datetime, end: datetime | None) -> float:
            return compute_weight(
                components, edge_type=edge.type, valid_to=end, now=now, rules=rules, self_loop=loop
            )

        written = weight(_aware(components.computed_at) or PINNED_NOW, valid_to)
        assert math.isclose(written, edge.weight, abs_tol=1e-9), (
            f"{store.name}: {edge.type} {edge.id} stores {edge.weight} and its own components "
            f"give {written} at the time they were taken"
        )
        stored[edge.id] = edge.weight
        cut[edge.id] = weight(CUT_OFF_INSTANT, valid_to)
        past[edge.id] = weight(CUT_OFF_INSTANT, None if valid_to is None else FAR_PAST)
    return dict(zip(POINTS, (stored, cut, past), strict=True))


def _place(plan_pair: tuple[str, str, str], edges: Sequence[Edge]) -> Edge:
    """The one link of this type between the two keyed nodes."""
    link_type, a, b = plan_pair
    (match,) = [
        e for e in edges
        if e.type == link_type and {e.source, e.target} == {node_id(a), node_id(b)}
    ]  # fmt: skip
    return match


def _verdict(edges: Sequence[Edge], weights: dict[str, float], *, picture: bool) -> dict[str, Any]:
    """Amendment 7 decision 2's thresholds, from the heavy end for the call and the transfers and
    the light end for the cell share and the picture; a tie takes the worse place; a fraction of
    the circle rounds up. The call must be 1st (ADR-123 decision 6; the amendment's own is the top
    three)."""
    n = len(edges)

    def heavy(edge: Edge) -> int:
        return sum(1 for v in weights.values() if v >= weights[edge.id])

    def light(edge: Edge) -> int:
        return sum(1 for v in weights.values() if v <= weights[edge.id])

    call_edge = _place(CALL, edges)
    call = heavy(call_edge)
    transfers = [heavy(_place(t, edges)) for t in TRANSFERS]
    lightest = [light(_place(ONE_WEEK_SHARE, edges))]
    if picture:
        (depicts,) = [e for e in edges if e.type == "DEPICTS"]
        lightest.append(light(depicts))
    quarter, eighth = math.ceil(n / 4), math.ceil(n / 8)
    outranking = sorted({e.type for e in edges if weights[e.id] > weights[call_edge.id]})
    return {
        "n": n, "call": call, "transfers": transfers, "share": lightest[0], "lightest": lightest,
        "quarter": quarter, "eighth": eighth, "outranking": outranking,
        "green": call == 1 and call <= 3 and max(transfers) <= quarter
        and max(lightest) <= eighth,
    }  # fmt: skip


async def test_amendment_7_circle_on_stored_weights(
    plan: Any, store_a: Store, store_c: Store
) -> None:
    """The principal's payment and call circle, read from the stores as the analyst sees it, weighs
    as Amendment 7 decision 2 and ADR-123 decision 6 say at three points and both moments: the call
    link first, the payer's three transfers in the top quarter, and the one-week cell share and the
    principal's picture in the bottom eighth. The circle holds about 58 links at the seed and about
    62 after chapter 4."""
    for store in (store_a, store_c):
        edges = await _circle(store)
        assert len(edges) == len(pid_writes.circle_links(plan, store.moment)[1]), store.name
        _the_stores_circle_is_the_plans(plan, store, edges)
        # The full cases weigh under weights version 3, whatever the file's latest becomes.
        for edge in edges:
            assert edge.weight_components is not None
            named = edge.weight_components.parameter_set or ""
            assert named.startswith("3/"), (store.name, edge.type, named)
        for point, weights in _weights_at(store, edges).items():
            verdict = _verdict(edges, weights, picture=True)
            print(f"PID-ACCESS circle {store.name} {point}: {verdict}", flush=True)
            assert verdict["call"] == 1, (store.name, point, verdict)
            assert verdict["outranking"] == [], (store.name, point, verdict)
            assert verdict["green"], (store.name, point, verdict)


async def test_amendment_7_circle_is_red_under_each_planted_wrong_rule_at_all_three_points(
    plan: Any, store_a: Store, store_p1: Store, store_p2: Store, store_p3: Store
) -> None:
    """Shown red (rule 15, ADR-123 decision 6): each store holds the circle alone under one planted
    wrong rule, and the check fails at the stored weights and at both recomputed points, for the
    plant's own reason. Each plant's stored weights also move the way its rule says against A's, so
    the planted rule reached the adapter that weighed them."""
    right = {e.id: e for e in await _circle(store_a)}
    stored_in_a = {_triple(e): e.weight for e in right.values()}
    # (what the rule does to its own link against A, and the place it pushes past its threshold)
    reasons: dict[str, tuple[tuple[tuple[str, str, str], ...], str, Callable[[Any], bool]]] = {
        "P1": (TRANSFERS, "lighter", lambda v: max(v["transfers"]) > v["quarter"]),
        "P2": ((ONE_WEEK_SHARE,), "heavier", lambda v: v["share"] > v["eighth"]),
        "P3": ((CALL,), "lighter", lambda v: v["call"] > 3),
    }
    for (name, link_type, heavy), store in zip(PLANTS, (store_p1, store_p2, store_p3), strict=True):
        assert store.name == name and store.rules is not None
        assert store.rules.rule_for(link_type)[1].heavy == heavy
        edges = await _circle(store)
        _the_stores_circle_is_the_plans(plan, store, edges)
        # A circle-only load weighs as a full one does (version 3: a weight comes from the link
        # alone): every link not of the planted type weighs exactly as in A.
        unplanted = [e for e in edges if e.type != link_type]
        assert unplanted
        for e in unplanted:
            assert e.weight == stored_in_a[_triple(e)], (name, e.type, e.weight)
        moved_links, direction, own_reason = reasons[name]
        for link in moved_links:
            here = _place(link, edges).weight
            there = stored_in_a[(link[0], node_id(link[1]), node_id(link[2]))]
            assert (here < there) if direction == "lighter" else (here > there), (name, link)
        for point, weights in _weights_at(store, edges).items():
            verdict = _verdict(edges, weights, picture=False)
            print(f"PID-ACCESS circle {name} {point}: {verdict}", flush=True)
            assert not verdict["green"], (name, point, verdict)
            assert own_reason(verdict), (name, point, verdict)
