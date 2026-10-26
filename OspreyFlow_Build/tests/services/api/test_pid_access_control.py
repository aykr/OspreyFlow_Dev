"""The Prison Intelligence Dataset against a real ArcadeDB (the throwaway one): the figures the
script quotes, read by the demo analyst, and Amendment 7's circle (ADR-120 D4 to D9 and
Amendments 7 to 12 and 16; ADR-123; Brief 1 stage 5 unit 5c).

ADR-120 Amendment 16 made the dataset OFFICIAL throughout, so this module no longer compares a
store holding a `SECRET` link with one that does not: there is no such link. Its other cases stay.

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

- **A** chapter 4; **C** the seed moment. Pictures are loaded into each (see `PICTURE_STORES`).
- **P1 to P3** only the Amendment 7 circle's links and their end nodes (`pid_writes.circle_writes`),
  at chapter 4, with no pictures, each under one planted wrong rule: `TRANSACTED` heavy 60,
  `SHARED_CELL_WITH` heavy 1, `COMMUNICATED_WITH` heavy 4,000. A planted rule is version 3 with one
  rule changed, put in force by pointing `adapters.graph_arcadedb.adapter.load_weight_rules` at it,
  as the conformance suite does for a version. From weights version 2 a link's weight depends on
  the link alone, so its stored weight in a circle-only store is what a full load gives it.

Two principals read: the **analyst** (`OFFICIAL`, no restricted codes, both datasets) and a
**cleared** one (`SECRET`, otherwise the same); with nothing above `OFFICIAL` in the dataset they
read the same figures.

What each test proves:

- **J1, J2, J5, J7** and the **229** reports, the **inferred** `PASSES_ITEMS_TO` links: the figures
  the script quotes, each from the store.
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
from dataclasses import dataclass
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
from services.api.search import SearchRequest, search
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
from schemas.compute import CentralityRequest
from schemas.domain import (
    AuditStub,
    Connections,
    ConnectionsRequest,
    Edge,
    ExpandRequest,
    Node,
    NodeWrite,
    PatternQuery,
    Principal,
    ProvenanceState,
    Subgraph,
)
from tests.scenarios.test_pid_plan import View

from .working_set.fakes import FakeWorkingSetStore

pytestmark = pytest.mark.asyncio(loop_scope="module")

ONTOLOGY = load_deployment_ontology()
SCHEME = load_uk_le_scheme()
HISTORY = load_weight_history()

#: The load day: what `now_utc` returns while a store is written.
PINNED_NOW = datetime(2026, 5, 1, 9, 0, tzinfo=UTC)
#: Amendment 7 decision 2's second and third points: the intelligence cut-off (the plan's, at
#: 23:59:59 UTC), and every dated end far in the past (recency halves every 90 days and never
#: reaches 0).
CUT_OFF_INSTANT = datetime.combine(pid_plan.CUT_OFF, clock_time(23, 59, 59), tzinfo=UTC)
FAR_PAST = datetime(1900, 1, 1, tzinfo=UTC)
POINTS = ("as stored", "at the cut-off", "with every end far in the past")

#: The stores that get the plan's pictures through the picture route (Amendment 13 decision 4): A
#: and C carry them, for J1 and the circle. About 1,600 each, which is the largest part of the
#: module's time. The stores that exist for one comparison (P1 to P3) carry none.
PICTURE_STORES = frozenset({"A", "C"})

CASE = "pid-case"
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
async def store_c(plan: Any) -> AsyncIterator[Store]:
    async with AsyncExitStack() as stack:
        yield await _open(stack, plan, "C", "seed")


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


# --- Reading the stores -----------------------------------------------------------------------

Triple = tuple[str, str, str]


def _triple(edge: Edge) -> Triple:
    return (edge.type, edge.source, edge.target)


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
    for principal in (ANALYST, CLEARED):  # nothing is above OFFICIAL, so the two read the same
        star = await store.graph.expand(ExpandRequest(node_ids=[PRINCIPAL], depth=1), principal)
        assert len(star.edges) == len({e.id for e in star.edges})
        stars[principal.id] = star
        # The count "With all links" shows, and the degree the best-connected list gives him.
        assert len(star.edges) == expected, (store.name, principal.id)
        assert await _degree_by_ranking(store, principal, PRINCIPAL) == expected, (
            store.name,
            principal.id,
        )
        assert Counter(e.type for e in star.edges) == Counter(by_type), (store.name, principal.id)
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


async def test_j1_the_principals_star_is_49_in_a_and_45_in_c_for_the_analyst_and_the_cleared(
    store_a: Store, store_c: Store
) -> None:
    """J1: the depth-1 expand's link count (what "With all links" shows) and the principal's
    `most_connected` degree agree, with his real picture link among them."""
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
