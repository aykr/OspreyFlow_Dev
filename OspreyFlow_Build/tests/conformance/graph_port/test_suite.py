"""`GraphPort` conformance suite —
`spec/04_VAULT_BACKEND.md` §6, `spec/00_ARCHITECTURE.md` §2.1 and §5.

Parametrised over `GRAPH_PORT_ADAPTERS` in `tests/conformance/registry.py` —
each entry opens a fresh, uniquely-named ArcadeDB database per test. A
second dialect or a second adapter proves itself against these same cases
with no change to this file's shape, only the registry.

The existence-leak tests (`test_unauthorised_*`) are the hard part: it is
not enough that an unauthorised principal's query omits a hidden node's
properties. Each one builds a "hidden" fixture — a SECRET-classified
node/edge an OFFICIAL-cleared analyst cannot see — and asserts the
unauthorised principal's result carries no trace of it at all: not in a
degree count, not in a path length, not in a match result. A leak here
would mean the result differs only because the hidden record exists, which
is exactly what must never be observable.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from conduit_common.identity import new_edge_id, new_node_id, now_utc
from ontology.errors import OntologyError
from ports.graph import GraphPort, SubgraphTooLarge, SuggestOptions
from schemas.domain import (
    Edge,
    EdgeWrite,
    ExpandRequest,
    Interval,
    NodeWrite,
    PathRequest,
    PatternEdge,
    PatternNode,
    PatternQuery,
    Principal,
    Provenance,
    ProvenanceState,
    SourceRef,
)
from tests.conformance.registry import GRAPH_PORT_ADAPTERS, GraphAdapterFactory

pytestmark = [
    pytest.mark.parametrize("factory", GRAPH_PORT_ADAPTERS, ids=str),
    # The stale-database sweep (`conftest.py`) is requested here, not `autouse` there — this is
    # the one module in this directory that actually opens ArcadeDB connections; `test_guard.py`
    # does not, and must not be made to depend on a live store just by sharing this directory.
    pytest.mark.usefixtures("_sweep_stale_conformance_databases"),
]

OFFICIAL = Principal(id="analyst-official", clearance="OFFICIAL", org_unit="unit-1")
SENSITIVE = Principal(id="analyst-sensitive", clearance="OFFICIAL-SENSITIVE", org_unit="unit-1")
CLEARED = Principal(id="analyst-secret", clearance="SECRET", org_unit="unit-1")
UNKNOWN_CLEARANCE = Principal(id="analyst-unknown", clearance="NOT-A-SCHEME-LEVEL", org_unit="u")
#: ADR-099: a principal reading for a case over one dataset, and one over none.
IN_ENRON = Principal(id="analyst-enron", clearance="SECRET", org_unit="unit-1", datasets=["enron"])
IN_FIXTURE = Principal(
    id="analyst-fixture", clearance="SECRET", org_unit="unit-1", datasets=["fixture"]
)
IN_NOTHING = Principal(id="analyst-none", clearance="SECRET", org_unit="unit-1", datasets=[])


def _provenance() -> Provenance:
    return Provenance(
        state=ProvenanceState.ASSERTED,
        sources=[SourceRef(document_id="doc-1", locator="p.1", excerpt_hash="a" * 64)],
        first_seen=datetime.now(UTC),
    )


def _handling(
    classification: str,
    *,
    handling_code: str = "P",
    owning_unit: str = "unit-1",
    originator: str = "unit-1",
    action_code: str | None = None,
    sanitisation_code: str | None = None,
) -> dict[str, str | None]:
    return {
        "classification": classification,
        "handling_code": handling_code,
        "originator": originator,
        "owning_unit": owning_unit,
        "action_code": action_code,
        "sanitisation_code": sanitisation_code,
    }


#: Required properties per default-ontology entity type, so every test
#: fixture satisfies `validate_properties` without each call site having to
#: know the ontology's required fields.
_DEFAULT_PROPERTIES: dict[str, dict[str, object]] = {
    "Person": {"family_name": "Test"},
    "Endpoint": {"value_normalised": "+441234567890"},
    "Alert": {"rule_id": "rule-1"},  # ADR-109: an alert names the rule that raised it
    # Location has no required properties — geometry_ref is optional
    # (03_CONDUIT_MIDDLEWARE.md §5.1: a jurisdiction or an administrative
    # boundary has no single point and must be able to carry none).
}


def _node(
    node_type: str,
    *,
    classification: str,
    handling_code: str = "P",
    owning_unit: str = "unit-1",
    originator: str = "unit-1",
    action_code: str | None = None,
    sanitisation_code: str | None = None,
    load_id: str | None = None,
    recipe_id: str | None = None,
    recipe_version: int | None = None,
    datasets: list[str] | None = None,
    **properties: object,
) -> NodeWrite:
    merged_properties = {**_DEFAULT_PROPERTIES.get(node_type, {}), **properties}
    return NodeWrite(
        id=new_node_id(),
        type=node_type,
        properties=merged_properties,
        provenance=_provenance(),
        handling=_handling(  # type: ignore[arg-type]
            classification, handling_code=handling_code, owning_unit=owning_unit,
            originator=originator, action_code=action_code, sanitisation_code=sanitisation_code,
        ),
        created_by="loader-1",
        created_at=now_utc(),
        load_id=load_id,
        recipe_id=recipe_id,
        recipe_version=recipe_version,
        datasets=datasets or [],
    )


def _edge(
    edge_type: str,
    source: str,
    target: str,
    *,
    classification: str,
    handling_code: str = "P",
    owning_unit: str = "unit-1",
    originator: str = "unit-1",
    interval: Interval | None = None,
    occurrences: int = 1,
    load_id: str | None = None,
    recipe_id: str | None = None,
    recipe_version: int | None = None,
    basis: str | None = None,
    datasets: list[str] | None = None,
) -> EdgeWrite:
    return EdgeWrite(
        id=new_edge_id(),
        type=edge_type,
        source=source,
        target=target,
        provenance=_provenance(),
        handling=_handling(  # type: ignore[arg-type]
            classification, handling_code=handling_code, owning_unit=owning_unit,
            originator=originator,
        ),
        created_by="loader-1",
        created_at=now_utc(),
        interval=interval,
        occurrences=occurrences,
        basis=basis,  # type: ignore[arg-type]
        load_id=load_id,
        recipe_id=recipe_id,
        recipe_version=recipe_version,
        datasets=datasets or [],
    )


async def _write(
    adapter: GraphPort, nodes: list[NodeWrite], edges: list[EdgeWrite]
) -> tuple[list[str], list[str]]:
    tx = await adapter.begin_transaction()
    node_ids = await adapter.upsert_nodes(nodes, tx)
    edge_ids = await adapter.upsert_edges(edges, tx) if edges else []
    await adapter.commit_transaction(tx)
    return node_ids, edge_ids


# --- basic round trips -------------------------------------------------------


async def test_write_and_read_back_every_default_ontology_entity_type(
    factory: GraphAdapterFactory,
) -> None:
    from ontology.loader import load_default_ontology

    ontology = load_default_ontology()
    async with factory.context() as adapter:
        for entity in ontology.entity_types:
            (node_id,), _ = await _write(
                adapter, [_node(entity.name, classification="OFFICIAL")], []
            )
            node = await adapter.get_node(node_id, CLEARED)
            assert node is not None
            assert node.type == entity.name


async def test_node_property_values_round_trip_exactly(factory: GraphAdapterFactory) -> None:
    """Not just "the write succeeds and the type is right"
    (`test_write_and_read_back_every_default_ontology_entity_type`, above)
    — every property *value*, across the ontology's declared types
    (`string`, `string[]`, `date`), must survive the round trip unchanged.
    This is the shape of test the `upsert_edges` merge defect slipped
    past: a property asserted at write time but never compared against
    what a read actually returns."""
    async with factory.context() as adapter:
        (node_id,), _ = await _write(
            adapter,
            [
                _node(
                    "Person",
                    classification="OFFICIAL",
                    family_name="O'Brien-Smith",
                    given_names="Mary Jane",
                    date_of_birth="1990-05-17",
                    aliases=["MJ", "Marie"],
                )
            ],
            [],
        )
        node = await adapter.get_node(node_id, CLEARED)
        assert node is not None
        assert node.properties["family_name"] == "O'Brien-Smith"
        assert node.properties["given_names"] == "Mary Jane"
        assert node.properties["date_of_birth"] == "1990-05-17"
        assert node.properties["aliases"] == ["MJ", "Marie"]


async def test_node_resolution_state_round_trips_exactly(factory: GraphAdapterFactory) -> None:
    from schemas.domain import ResolutionState

    async with factory.context() as adapter:
        write = _node("Person", classification="OFFICIAL")
        write = write.model_copy(
            update={
                "resolution": ResolutionState(
                    cluster_id="cluster-42",
                    cluster_score=0.87,
                    resolution_run="run-2026-01",
                    manually_linked=["node-a", "node-b"],
                    manually_split=["node-c"],
                )
            }
        )
        (node_id,), _ = await _write(adapter, [write], [])
        node = await adapter.get_node(node_id, CLEARED)
        assert node is not None
        assert node.resolution.cluster_id == "cluster-42"
        assert node.resolution.cluster_score == 0.87
        assert node.resolution.resolution_run == "run-2026-01"
        assert node.resolution.manually_linked == ["node-a", "node-b"]
        assert node.resolution.manually_split == ["node-c"]


async def test_edge_properties_and_distinct_interval_round_trip_exactly(
    factory: GraphAdapterFactory,
) -> None:
    async with factory.context() as adapter:
        (a, b), _ = await _write(
            adapter,
            [
                _node("Endpoint", classification="OFFICIAL", value_normalised="+441111111111"),
                _node("Endpoint", classification="OFFICIAL", value_normalised="+442222222222"),
            ],
            [],
        )
        start = datetime(2026, 1, 1, 9, 0, tzinfo=UTC)
        end = datetime(2026, 1, 1, 9, 5, tzinfo=UTC)
        _, (edge_id,) = await _write(
            adapter,
            [],
            [
                EdgeWrite(
                    id=new_edge_id(),
                    type="COMMUNICATED_WITH",
                    source=a,
                    target=b,
                    properties={"duration_s": 42.5, "direction": "inbound"},
                    interval=Interval(valid_from=start, valid_to=end),
                    provenance=_provenance(),
                    handling=_handling("OFFICIAL"),  # type: ignore[arg-type]
                    created_by="loader-1",
                    created_at=now_utc(),
                )
            ],
        )
        subgraph = await adapter.expand(ExpandRequest(node_ids=[a], depth=1), CLEARED)
        (edge,) = subgraph.edges
        assert edge.id == edge_id
        assert edge.properties["duration_s"] == 42.5
        assert edge.properties["direction"] == "inbound"
        assert edge.interval == Interval(valid_from=start, valid_to=end)


async def test_action_code_and_sanitisation_code_never_gate_a_read(
    factory: GraphAdapterFactory,
) -> None:
    """`01_DOMAIN_MODEL.md` §2.2's field-by-field table: `action_code`
    constrains what may be *done*, `sanitisation_code` is the export
    gate's reason for existing — neither gates a *read*. Stated in prose;
    nothing previously exercised it, since every other test in this suite
    leaves both fields `None`."""
    async with factory.context() as adapter:
        (node_id,), _ = await _write(
            adapter,
            [
                _node(
                    "Person",
                    classification="OFFICIAL",
                    action_code="A1",  # covert development — the most access-restrictive-sounding
                    sanitisation_code="S2",  # consult originator
                )
            ],
            [],
        )
        # An OFFICIAL-cleared principal with no special permission at all
        # still sees the record — these fields are read-inert.
        assert await adapter.get_node(node_id, OFFICIAL) is not None


def test_subgraph_has_no_filtered_count_field(factory: GraphAdapterFactory) -> None:
    """ADR-124 decision 1: a read returns the nodes and links the principal may read and no figure
    for what it left out. `Subgraph.filtered_count` was reserved by `01_DOMAIN_MODEL.md` §8 and left
    at `0` by every adapter, a field that claims completeness and went to every response holding a
    `Subgraph`; it was removed, not held at 0. Pinned so a figure for what was filtered cannot come
    back as a field of what every read returns. (It takes the suite's `factory` only because the
    module is parametrised over it; it opens no store.)"""
    from schemas.domain import Subgraph

    assert "filtered_count" not in Subgraph.model_fields
    assert set(Subgraph.model_fields) == {"nodes", "edges"}


async def test_write_and_read_back_an_edge(factory: GraphAdapterFactory) -> None:
    async with factory.context() as adapter:
        (a, b), _ = await _write(
            adapter,
            [
                _node("Person", classification="OFFICIAL"),
                _node("Person", classification="OFFICIAL"),
            ],
            [],
        )
        _, (edge_id,) = await _write(
            adapter, [], [_edge("ASSOCIATE_OF", a, b, classification="OFFICIAL")]
        )
        stats = await adapter.neighbourhood_stats(a, CLEARED)
        assert stats.degree == 1
        assert stats.degree_by_type == {"ASSOCIATE_OF": 1}
        assert edge_id


# --- expand at depth 1-4 -----------------------------------------------------


async def test_expand_reaches_further_nodes_as_depth_increases(
    factory: GraphAdapterFactory,
) -> None:
    async with factory.context() as adapter:
        node_ids, _ = await _write(
            adapter, [_node("Person", classification="OFFICIAL") for _ in range(5)], []
        )
        edges = [
            _edge("ASSOCIATE_OF", node_ids[i], node_ids[i + 1], classification="OFFICIAL")
            for i in range(4)
        ]
        await _write(adapter, [], edges)

        for depth in (1, 2, 3, 4):
            subgraph = await adapter.expand(
                ExpandRequest(node_ids=[node_ids[0]], depth=depth), CLEARED
            )
            reached = {n.id for n in subgraph.nodes}
            assert reached == set(node_ids[: depth + 1])


async def test_expand_edge_types_filters_to_the_declared_type(
    factory: GraphAdapterFactory,
) -> None:
    """`ExpandRequest.edge_types` had no conformance test at all before
    this — a real gap, not a hypothetical one: the ArcadeDB adapter's own
    query builder rendered `.hasLabel(['a'])` (a single Groovy *list*
    argument), which `hasLabel` — a varargs step, `hasLabel('a','b')` — 500s
    on, with no clearer error than `CommandExecutionException`. Found by
    Phase 5's HMP fixture work asking `expand` to filter to `PRESENT_AT`
    specifically, not by this suite. Two edge types from the hub, filtered
    to one, proves both that the filter is real and that it is not merely
    "no filter, everything passes"."""
    async with factory.context() as adapter:
        (hub, via_present_at, via_uses), _ = await _write(
            adapter,
            [
                _node("Person", classification="OFFICIAL"),
                _node("Location", classification="OFFICIAL"),
                _node("Endpoint", classification="OFFICIAL"),
            ],
            [],
        )
        await _write(
            adapter,
            [],
            [
                _edge("PRESENT_AT", hub, via_present_at, classification="OFFICIAL"),
                _edge("USES", hub, via_uses, classification="OFFICIAL"),
            ],
        )

        subgraph = await adapter.expand(
            ExpandRequest(node_ids=[hub], depth=1, edge_types=["PRESENT_AT"]), CLEARED,
        )
        reached = {n.id for n in subgraph.nodes}
        assert reached == {hub, via_present_at}


async def test_both_sims_reach_their_device_in_one_expand(factory: GraphAdapterFactory) -> None:
    """`08_ACCEPTANCE_SCENARIOS.md` B15 / `06_DECISIONS.md` ADR-023: a SIM
    swap is one traversal, not a special case. Two distinct SIM `Endpoint`s
    (different source nodes) each carry their own `PAIRED_WITH` edge into
    the same `Device` — a single `expand` one hop out from the handset,
    default `direction="both"` since `PAIRED_WITH` runs `Endpoint -> Device`
    and the handset is the target, must return both, from one call. Also
    guards against `_merge_interval` collapsing them: they are different
    edges (different sources), unlike `test_upserting_the_same_pair_twice_
    merges_into_one_edge`'s same-pair case above, so both intervals must
    survive distinct and unmerged."""
    async with factory.context() as adapter:
        (handset, sim_a, sim_b), _ = await _write(
            adapter,
            [
                _node("Device", classification="OFFICIAL", imei="49015420323751"),
                _node(
                    "Endpoint",
                    classification="OFFICIAL",
                    value_normalised="234150123456781",
                    endpoint_kind="imsi",
                    imsi="234150123456781",
                ),
                _node(
                    "Endpoint",
                    classification="OFFICIAL",
                    value_normalised="234150123456782",
                    endpoint_kind="imsi",
                    imsi="234150123456782",
                ),
            ],
            [],
        )
        before_swap = Interval(
            valid_from=datetime(2026, 1, 1, tzinfo=UTC), valid_to=datetime(2026, 1, 20, tzinfo=UTC)
        )
        after_swap = Interval(valid_from=datetime(2026, 1, 21, tzinfo=UTC), valid_to=None)
        await _write(
            adapter,
            [],
            [
                _edge(
                    "PAIRED_WITH", sim_a, handset, classification="OFFICIAL", interval=before_swap
                ),
                _edge(
                    "PAIRED_WITH", sim_b, handset, classification="OFFICIAL", interval=after_swap
                ),
            ],
        )

        subgraph = await adapter.expand(
            ExpandRequest(node_ids=[handset], depth=1, edge_types=["PAIRED_WITH"]), CLEARED,
        )
        reached = {n.id for n in subgraph.nodes}
        assert reached == {handset, sim_a, sim_b}

        intervals = {e.source: e.interval for e in subgraph.edges}
        assert intervals[sim_a] == before_swap
        assert intervals[sim_b] == after_swap


async def test_msisdn_reaches_its_device_in_two_hops_not_one(
    factory: GraphAdapterFactory,
) -> None:
    """`06_DECISIONS.md` ADR-023's corrected answer to its own second
    question: an `Endpoint` of kind `msisdn` never carries `PAIRED_WITH`
    directly — only its `imsi` `Endpoint` does. Reaching the handset from
    the number `08_ACCEPTANCE_SCENARIOS.md` B5/B7 land an analyst on is
    `msisdn --SAME_AS--> imsi --PAIRED_WITH--> device`, exactly two graph
    hops. This is the test that would fail if that shape were ever
    collapsed — a future shortcut edge straight from an `msisdn` `Endpoint`
    to a `Device` would make `depth=1` below reach three nodes instead of
    two."""
    async with factory.context() as adapter:
        (handset, sim_imsi, sim_msisdn), _ = await _write(
            adapter,
            [
                _node("Device", classification="OFFICIAL", imei="49015420323751"),
                _node(
                    "Endpoint",
                    classification="OFFICIAL",
                    value_normalised="234150123456782",
                    endpoint_kind="imsi",
                    imsi="234150123456782",
                ),
                _node(
                    "Endpoint",
                    classification="OFFICIAL",
                    value_normalised="+447911123457",
                    endpoint_kind="msisdn",
                ),
            ],
            [],
        )
        # `{"score": 1.0}` only — the same shape `WorkingSetService.manual_link`
        # writes for a directly-known, non-Splink link: `model_version`/
        # `comparison_vector` are Splink's own output fields, left unset
        # rather than invented (`_edge()` has no `properties` parameter,
        # matching `test_edge_properties_and_distinct_interval_round_trip_
        # exactly`'s own precedent for constructing `EdgeWrite` directly
        # whenever a test needs edge properties `_edge()` doesn't expose).
        same_as = EdgeWrite(
            id=new_edge_id(),
            type="SAME_AS",
            source=sim_msisdn,
            target=sim_imsi,
            properties={"score": 1.0},
            provenance=_provenance(),
            handling=_handling("OFFICIAL"),  # type: ignore[arg-type]
            created_by="loader-1",
            created_at=now_utc(),
        )
        await _write(
            adapter,
            [],
            [
                same_as,
                _edge("PAIRED_WITH", sim_imsi, handset, classification="OFFICIAL"),
            ],
        )

        one_hop = await adapter.expand(
            ExpandRequest(
                node_ids=[sim_msisdn], depth=1, edge_types=["SAME_AS", "PAIRED_WITH"]
            ),
            CLEARED,
        )
        assert {n.id for n in one_hop.nodes} == {sim_msisdn, sim_imsi}

        two_hops = await adapter.expand(
            ExpandRequest(
                node_ids=[sim_msisdn], depth=2, edge_types=["SAME_AS", "PAIRED_WITH"]
            ),
            CLEARED,
        )
        assert {n.id for n in two_hops.nodes} == {sim_msisdn, sim_imsi, handset}


# --- expand leaves out what was retracted or replaced ---------------------------------------


@pytest.mark.parametrize("reader", [OFFICIAL, CLEARED], ids=["official", "cleared"])
async def test_expand_leaves_out_a_reverted_neighbour_and_a_superseded_one_for_any_clearance(
    factory: GraphAdapterFactory, reader: Principal
) -> None:
    """A reverted element (`revert_elements`) and a superseded revision (`supersede_node`,
    `supersede_edge`) are not principal-dependent exclusions (`01_DOMAIN_MODEL.md` §2.4): no
    clearance sees them in an expansion. The positive control is the same neighbours and links
    before they are reverted and superseded, which `expand` returns, so that their absence
    afterwards is the exclusion and not a missing link.

    **Each half is proven by the check it names, and the nodes keep a live link on purpose.**
    - A node is reverted *alone*, leaving the hub's link to it live: a node reverted by its load
      while a later load's link stays. Only the vertex-side check keeps it out (and the link with
      it, since a link whose far end is not in the view is not returned).
    - A node is superseded, and a link to the old revision is then written (`upsert_edges` finds
      endpoints by id and does not refuse a superseded one). `supersede_node` re-pointed the
      links that existed, so this later link is what makes the old node reachable, and only the
      vertex-side check keeps it out.
    - A link is superseded with `supersede_edge`, which leaves the old link stored and still
      joining the hub and `kept`: only the superseded step on the link keeps it out, and one link
      joins them afterwards (the successor)."""
    async with factory.context() as adapter:
        (hub, kept, reverted_nb, superseded_nb), _ = await _write(
            adapter,
            [
                _node("Person", classification="OFFICIAL"),
                _node("Endpoint", classification="OFFICIAL"),
                _node("Endpoint", classification="OFFICIAL"),
                _node("Endpoint", classification="OFFICIAL"),
            ],
            [],
        )
        _, (kept_edge, reverted_edge, superseded_edge) = await _write(
            adapter,
            [],
            [
                _edge("USES", hub, kept, classification="OFFICIAL"),
                _edge("USES", hub, reverted_nb, classification="OFFICIAL"),
                _edge("USES", hub, superseded_nb, classification="OFFICIAL"),
            ],
        )
        req = ExpandRequest(node_ids=[hub], depth=1)

        before = await adapter.expand(req, reader)
        assert {n.id for n in before.nodes} == {hub, kept, reverted_nb, superseded_nb}
        assert {e.id for e in before.edges} == {kept_edge, reverted_edge, superseded_edge}

        tx = await adapter.begin_transaction()
        await adapter.revert_elements([reverted_nb], [], tx)  # the node alone: its link stays live
        replacement = await adapter.supersede_node(
            superseded_nb, _node("Endpoint", classification="OFFICIAL"), tx
        )
        successor = await adapter.supersede_edge(
            kept_edge,
            EdgeWrite(
                id=new_edge_id(),
                type="USES",
                source=hub,
                target=kept,
                provenance=_provenance(),
                handling=_handling("OFFICIAL"),  # type: ignore[arg-type]
                created_by="reviewer-1",
                created_at=now_utc(),
            ),
            tx,
        )
        await adapter.commit_transaction(tx)
        _, (late_link,) = await _write(
            adapter, [], [_edge("USES", hub, superseded_nb, classification="OFFICIAL")]
        )

        after = await adapter.expand(req, reader)
        node_ids = {n.id for n in after.nodes}
        edge_ids = {e.id for e in after.edges}
        assert node_ids == {hub, kept, replacement}
        assert reverted_nb not in node_ids and superseded_nb not in node_ids
        assert reverted_edge not in edge_ids  # live, but its far end is not in the view
        assert late_link not in edge_ids  # to the superseded revision
        assert kept_edge not in edge_ids  # superseded, still stored
        assert [e.id for e in after.edges if {e.source, e.target} == {hub, kept}] == [successor]
        assert len(after.edges) == 2  # the successor and the one carried to the replacement


# --- k-shortest paths --------------------------------------------------------


async def test_paths_finds_the_chain_and_respects_max_hops(
    factory: GraphAdapterFactory,
) -> None:
    async with factory.context() as adapter:
        node_ids, _ = await _write(
            adapter, [_node("Person", classification="OFFICIAL") for _ in range(4)], []
        )
        edges = [
            _edge("ASSOCIATE_OF", node_ids[i], node_ids[i + 1], classification="OFFICIAL")
            for i in range(3)
        ]
        await _write(adapter, [], edges)

        found = await adapter.paths(
            PathRequest(source=node_ids[0], target=node_ids[3], max_hops=6, k=1), CLEARED
        )
        assert len(found) == 1
        assert found[0].length == 3

        too_short = await adapter.paths(
            PathRequest(source=node_ids[0], target=node_ids[3], max_hops=2, k=1), CLEARED
        )
        assert too_short == []


async def test_paths_edge_types_filters_to_the_declared_type(
    factory: GraphAdapterFactory,
) -> None:
    """The same `hasLabel` varargs-not-list bug
    `test_expand_edge_types_filters_to_the_declared_type` documents,
    `PathBuilder` had its own copy of. A path only exists through the
    `ASSOCIATE_OF` edge; filtering to `USES` must find nothing, not error
    and not silently ignore the filter."""
    async with factory.context() as adapter:
        (a, b), _ = await _write(
            adapter,
            [
                _node("Person", classification="OFFICIAL"),
                _node("Person", classification="OFFICIAL"),
            ],
            [],
        )
        await _write(adapter, [], [_edge("ASSOCIATE_OF", a, b, classification="OFFICIAL")])

        via_correct_type = await adapter.paths(
            PathRequest(source=a, target=b, max_hops=3, k=1, edge_types=["ASSOCIATE_OF"]), CLEARED,
        )
        assert len(via_correct_type) == 1

        via_wrong_type = await adapter.paths(
            PathRequest(source=a, target=b, max_hops=3, k=1, edge_types=["USES"]), CLEARED,
        )
        assert via_wrong_type == []


async def test_paths_returns_hydrated_nodes_and_edges_not_bare_ids(
    factory: GraphAdapterFactory,
) -> None:
    """`06_DECISIONS.md` ADR-033: `Path.nodes`/`.edges` carry full `Node`/`Edge` objects — the one
    real interactive caller (the pathfinder) needs a node's own `type` to render it at all, which
    a bare id cannot supply."""
    async with factory.context() as adapter:
        (a, b), _ = await _write(
            adapter,
            [
                _node("Person", classification="OFFICIAL"),
                _node("Endpoint", classification="OFFICIAL"),
            ],
            [],
        )
        _, (edge_id,) = await _write(
            adapter, [], [_edge("USES", a, b, classification="OFFICIAL")]
        )

        [found] = await adapter.paths(PathRequest(source=a, target=b, max_hops=3, k=1), CLEARED)

        assert [n.id for n in found.nodes] == [a, b]
        assert [n.type for n in found.nodes] == ["Person", "Endpoint"]
        assert [e.id for e in found.edges] == [edge_id]
        assert found.edges[0].type == "USES"


async def test_paths_never_walk_a_not_same_as_judgement(factory: GraphAdapterFactory) -> None:
    """ADR-116 Amendment 1, the owner's ruling of 13 October 2026: a judgement that two records are
    different people is no step on any route, in the Pathfinder as in Find connections."""
    async with factory.context() as adapter:
        (a, b, c), _ = await _write(
            adapter, [_node("Person", classification="OFFICIAL") for _ in "abc"], []
        )
        await _write(
            adapter,
            [],
            [
                _edge("NOT_SAME_AS", a, c, classification="OFFICIAL"),
                _edge("ASSOCIATE_OF", a, b, classification="OFFICIAL"),
                _edge("ASSOCIATE_OF", b, c, classification="OFFICIAL"),
            ],
        )
        found = await adapter.paths(PathRequest(source=a, target=c, max_hops=6, k=5), CLEARED)
        assert {p.length for p in found} == {2}
        assert all(e.type != "NOT_SAME_AS" for p in found for e in p.edges)
        asked = PathRequest(source=a, target=c, max_hops=6, k=5, edge_types=["NOT_SAME_AS"])
        assert await adapter.paths(asked, CLEARED) == []


# --- routes at one degree (ADR-116) ------------------------------------------


async def _fewest_degrees(adapter: GraphPort, a: str, b: str, principal: Principal) -> int | None:
    """What the Conduit works out from `paths_at_length`: the first degree with a route."""
    for length in range(1, 7):
        if (await adapter.paths_at_length(a, b, length, 1, principal)).paths:
            return length
    return None


async def test_routes_at_a_length_are_exactly_that_long_and_every_such_route_is_found(
    factory: GraphAdapterFactory,
) -> None:
    """a—d directly, a—x—d, and a—b—c—d: one simple route at each of 1, 2 and 3 links, none at 4."""
    async with factory.context() as adapter:
        (a, b, c, d, x), _ = await _write(
            adapter, [_node("Person", classification="OFFICIAL") for _ in "abcdx"], []
        )
        await _write(
            adapter,
            [],
            [
                _edge("ASSOCIATE_OF", a, d, classification="OFFICIAL"),
                _edge("ASSOCIATE_OF", a, x, classification="OFFICIAL"),
                _edge("ASSOCIATE_OF", x, d, classification="OFFICIAL"),
                _edge("ASSOCIATE_OF", a, b, classification="OFFICIAL"),
                _edge("ASSOCIATE_OF", b, c, classification="OFFICIAL"),
                _edge("ASSOCIATE_OF", c, d, classification="OFFICIAL"),
            ],
        )
        routes = {n: await adapter.paths_at_length(a, d, n, 10, CLEARED) for n in (1, 2, 3, 4)}
        assert [[node.id for node in p.nodes] for p in routes[1].paths] == [[a, d]]
        assert [[node.id for node in p.nodes] for p in routes[2].paths] == [[a, x, d]]
        assert [[node.id for node in p.nodes] for p in routes[3].paths] == [[a, b, c, d]]
        assert routes[4].paths == [] and routes[4].more is False
        assert all(p.length == n and len(p.edges) == n for n, r in routes.items() for p in r.paths)
        assert {r.length for r in routes.values()} == {1, 2, 3, 4}


async def test_no_route_passes_through_a_hidden_node_or_link_and_the_fewest_degrees_do_not_move(
    factory: GraphAdapterFactory,
) -> None:
    """Rule 3's path-length leak, for degrees: a SECRET link a—d and a route through a SECRET node
    are invisible to an OFFICIAL reader, who sees a and d three degrees apart, as if neither
    existed."""
    async with factory.context() as adapter:
        (a, b, c, d), _ = await _write(
            adapter, [_node("Person", classification="OFFICIAL") for _ in "abcd"], []
        )
        (hidden,), _ = await _write(adapter, [_node("Person", classification="SECRET")], [])
        await _write(
            adapter,
            [],
            [
                _edge("ASSOCIATE_OF", a, b, classification="OFFICIAL"),
                _edge("ASSOCIATE_OF", b, c, classification="OFFICIAL"),
                _edge("ASSOCIATE_OF", c, d, classification="OFFICIAL"),
                _edge("ASSOCIATE_OF", a, hidden, classification="OFFICIAL"),
                _edge("ASSOCIATE_OF", hidden, d, classification="OFFICIAL"),
                _edge("ASSOCIATE_OF", a, d, classification="SECRET"),
            ],
        )
        assert await _fewest_degrees(adapter, a, d, OFFICIAL) == 3
        assert await _fewest_degrees(adapter, a, d, CLEARED) == 1  # the filter is real
        through_hidden = await adapter.paths_at_length(a, d, 2, 10, OFFICIAL)
        assert through_hidden.paths == [] and through_hidden.more is False
        assert len((await adapter.paths_at_length(a, d, 2, 10, CLEARED)).paths) == 1
        # A hidden end has no route at all, the same answer as a node that does not exist.
        assert (await adapter.paths_at_length(a, hidden, 1, 10, OFFICIAL)).paths == []


async def test_routes_at_a_length_honour_the_limit_and_say_when_more_exist(
    factory: GraphAdapterFactory,
) -> None:
    """Four two-link routes a—m—d. Asked for three: three, and `more`. Asked for four: no `more`."""
    async with factory.context() as adapter:
        (a, d, *middle), _ = await _write(
            adapter, [_node("Person", classification="OFFICIAL") for _ in range(6)], []
        )
        edges = [_edge("ASSOCIATE_OF", a, m, classification="OFFICIAL") for m in middle]
        edges += [_edge("ASSOCIATE_OF", m, d, classification="OFFICIAL") for m in middle]
        await _write(adapter, [], edges)

        three = await adapter.paths_at_length(a, d, 2, 3, CLEARED)
        assert len(three.paths) == 3 and three.more is True
        four = await adapter.paths_at_length(a, d, 2, 4, CLEARED)
        assert len(four.paths) == 4 and four.more is False
        assert {p.nodes[1].id for p in four.paths} == set(middle)


async def test_a_not_same_as_judgement_is_never_a_step_on_a_route(
    factory: GraphAdapterFactory,
) -> None:
    """`NOT_SAME_AS` says two records are different people; it is not a connection between them."""
    async with factory.context() as adapter:
        (a, b), _ = await _write(
            adapter, [_node("Person", classification="OFFICIAL") for _ in "ab"], []
        )
        await _write(adapter, [], [_edge("NOT_SAME_AS", a, b, classification="OFFICIAL")])
        assert (await adapter.paths_at_length(a, b, 1, 10, CLEARED)).paths == []
        await _write(adapter, [], [_edge("ASSOCIATE_OF", a, b, classification="OFFICIAL")])
        [route] = (await adapter.paths_at_length(a, b, 1, 10, CLEARED)).paths
        assert route.edges[0].type == "ASSOCIATE_OF"


async def test_routes_at_a_length_follow_only_the_link_types_asked_for(
    factory: GraphAdapterFactory,
) -> None:
    async with factory.context() as adapter:
        (a, b), _ = await _write(
            adapter, [_node("Person", classification="OFFICIAL") for _ in "ab"], []
        )
        await _write(adapter, [], [_edge("ASSOCIATE_OF", a, b, classification="OFFICIAL")])
        typed = await adapter.paths_at_length(a, b, 1, 10, CLEARED, edge_types=["ASSOCIATE_OF"])
        assert len(typed.paths) == 1
        other = await adapter.paths_at_length(a, b, 1, 10, CLEARED, edge_types=["USES"])
        assert other.paths == []


async def test_routes_in_one_dataset_match_a_graph_without_the_other_datasets_link(
    factory: GraphAdapterFactory,
) -> None:
    """ADR-099: a case reads only its datasets, so a link of another dataset is no step for it."""
    async with factory.context() as adapter:
        both = ["enron", "fixture"]
        (a, b, target), _ = await _write(
            adapter, [_node("Person", classification="OFFICIAL", datasets=both) for _ in "abc"], []
        )
        await _write(
            adapter,
            [],
            [
                _edge("ASSOCIATE_OF", a, b, classification="OFFICIAL", datasets=["fixture"]),
                _edge("ASSOCIATE_OF", b, target, classification="OFFICIAL", datasets=["fixture"]),
                _edge("ASSOCIATE_OF", a, target, classification="OFFICIAL", datasets=["enron"]),
            ],
        )
        assert await _fewest_degrees(adapter, a, target, IN_FIXTURE) == 2
        assert await _fewest_degrees(adapter, a, target, IN_ENRON) == 1
        assert await _fewest_degrees(adapter, a, target, IN_NOTHING) is None


# --- pattern match ------------------------------------------------------------


async def test_match_finds_the_declared_pattern(factory: GraphAdapterFactory) -> None:
    async with factory.context() as adapter:
        (a, b), _ = await _write(
            adapter,
            [
                _node("Person", classification="OFFICIAL"),
                _node("Endpoint", classification="OFFICIAL"),
            ],
            [],
        )
        await _write(adapter, [], [_edge("USES", a, b, classification="OFFICIAL")])

        pattern = PatternQuery(
            nodes=[
                PatternNode(var="p", entity_type="Person"),
                PatternNode(var="e", entity_type="Endpoint"),
            ],
            edges=[PatternEdge(edge_type="USES", from_var="p", to_var="e")],
        )
        subgraph = await adapter.match(pattern, CLEARED)
        found_ids = {n.id for n in subgraph.nodes}
        assert {a, b} <= found_ids


async def test_match_finds_a_pattern_of_one_variable_with_no_edges(
    factory: GraphAdapterFactory,
) -> None:
    """**The simplest pattern the visual query builder can express, and it returned a 500.**
    One entity type, no edges — what a first-time user draws before adding anything to it.

    Found 26 September 2026 driving the query builder against a real stack (round 12). Gremlin's
    `select` changes the *shape* of its result with its arity: `select('a','b')` yields a map
    keyed by variable, `select('a')` yields the bare projected value. `match` reads every record
    as the keyed form, so a one-variable pattern made it iterate an element map's own values and
    call `node_from_element_map` on the string `'mx_Person'` —
    `TypeError: string indices must be integers`, surfacing as
    `500 Internal Server Error` from `POST /v1/patterns/run`.

    **Why nothing caught it**: every other case in this file, including
    `test_match_single_chain_pattern_compiles_to_the_same_gremlin_as_before` immediately below,
    binds two or more variables — so the single-variable arity, the only one whose wire shape
    differs, had never once been rendered and parsed end to end. `CLAUDE.md` rule 12's shape
    exactly, and rule 1's: the contract is what this suite says it is, and it did not say this.

    Deliberately a real round trip through `adapter.match`, not a check of the compiled Gremlin:
    the defect was entirely in how the *response* was read, so a compiled-string assertion would
    have passed against the broken code."""
    async with factory.context() as adapter:
        (person, endpoint), _ = await _write(
            adapter,
            [
                _node("Person", classification="OFFICIAL"),
                _node("Endpoint", classification="OFFICIAL"),
            ],
            [],
        )

        pattern = PatternQuery(nodes=[PatternNode(var="p", entity_type="Person")], edges=[])
        subgraph = await adapter.match(pattern, CLEARED)

        found_ids = {n.id for n in subgraph.nodes}
        assert person in found_ids
        # And the type filter still applies — a bare `project` that dropped the `hasLabel`
        # would also "pass" an assertion that only checked the Person came back.
        assert endpoint not in found_ids
        # Fully hydrated nodes, not bare ids: the bug produced a `Node` from the wrong level of
        # the response, so asserting the shape is what distinguishes a real fix from a coincidence.
        assert all(n.type == "Person" for n in subgraph.nodes)


def test_match_single_chain_pattern_compiles_to_the_same_gremlin_as_before(
    factory: GraphAdapterFactory,
) -> None:
    """`06_DECISIONS.md` ADR-030's widening (Phase 7 Stage 4) must not change one character of the
    Gremlin an existing single-chain pattern already compiled to — this is the no-regression
    proof, checked as a compiled-string comparison rather than only "the query still returns the
    right nodes," since the latter could pass even if the compiler now takes a slower or
    differently-shaped path to the same answer. This golden string was captured directly from the
    unmodified `MatchBuilder` before Stage 4's own widening. Since then the handling scheme gained
    `PUBLIC` (the access fragment, not the compiler) and ADR-100 Amendment 7 changed the result
    tail; the walk is as captured."""
    from adapters.graph_arcadedb.access_filter import AccessFilter
    from adapters.graph_arcadedb.builders import MatchBuilder
    from ontology.handling import load_uk_le_scheme

    access = AccessFilter(load_uk_le_scheme())
    pattern = PatternQuery(
        nodes=[
            PatternNode(var="p", entity_type="Person"),
            PatternNode(var="e", entity_type="Endpoint"),
        ],
        edges=[PatternEdge(edge_type="USES", from_var="p", to_var="e")],
    )
    rendered = MatchBuilder(pattern).render_gremlin(access, CLEARED)
    assert rendered == (
        "g.V().hasLabel('mx_Person').has(\"reverted\",false).hasNot(\"superseded_by\")"
        ".has(\"handling_classification\",within(['PUBLIC','OFFICIAL','OFFICIAL-SENSITIVE','SECRET']))"
        '.filter(or(has("handling_code",within([\'P\',\'C\'])),and(has("handling_code",within([])),'
        'or(has("owning_unit",\'unit-1\'),has("originator",\'unit-1\'))))).as(\'p\')'
        ".select('p').outE('mx_USES')"
        '.has("reverted",false).hasNot("superseded_by")'
        '.has("handling_classification",within([\'PUBLIC\',\'OFFICIAL\',\'OFFICIAL-SENSITIVE\',\'SECRET\']))'
        '.filter(or(has("handling_code",within([\'P\',\'C\'])),and(has("handling_code",within([])),'
        "or(has(\"owning_unit\",'unit-1'),has(\"originator\",'unit-1')))))"
        ".inV()"
        '.has("reverted",false).hasNot("superseded_by")'
        '.has("handling_classification",within([\'PUBLIC\',\'OFFICIAL\',\'OFFICIAL-SENSITIVE\',\'SECRET\']))'
        '.filter(or(has("handling_code",within([\'P\',\'C\'])),and(has("handling_code",within([])),'
        "or(has(\"owning_unit\",'unit-1'),has(\"originator\",'unit-1'))))).hasLabel('mx_Endpoint')"
        # The tail alone changed, on purpose: the nodes once each, so `limit` bounds nodes as
        # `match_count` counts them (ADR-100 Amendment 7,
        # `test_match_returns_every_node_it_counted_however_many_ways_they_match`).
        ".as('e').union(select('e'),select('p')).dedup().limit(1000).elementMap()"
    )


async def test_match_finds_the_intersection_across_two_independent_roots(
    factory: GraphAdapterFactory,
) -> None:
    """B19 (`08_ACCEPTANCE_SCENARIOS.md`): "Expand to common contacts across the two principal
    endpoints" — a diamond, not a chain: two independent starting nodes (`a`, `b`) converging on a
    shared third (`e`), which the pre-Stage-4 single-chain-only compiler could not express at all
    (`e`'s own second incoming edge referenced a `from_var` — `b` — the linear walk never bound).
    `06_DECISIONS.md` ADR-030's widening addresses exactly this pattern."""
    async with factory.context() as adapter:
        (a, b, e, other), _ = await _write(
            adapter,
            [
                _node("Person", classification="OFFICIAL"),
                _node("Person", classification="OFFICIAL"),
                _node("Endpoint", classification="OFFICIAL"),
                # A second Endpoint only `a` uses — proves the match is the real intersection,
                # not merely "everything either root can reach."
                _node("Endpoint", classification="OFFICIAL"),
            ],
            [],
        )
        await _write(
            adapter,
            [],
            [
                _edge("USES", a, e, classification="OFFICIAL"),
                _edge("USES", b, e, classification="OFFICIAL"),
                _edge("USES", a, other, classification="OFFICIAL"),
            ],
        )

        pattern = PatternQuery(
            nodes=[
                # Both principal endpoints pinned — B19's own real shape ("the two principal
                # endpoints" are nodes the analyst already selected); only `e`, the common
                # contact, is the variable this query actually discovers.
                PatternNode(var="a", entity_type="Person", node_id=a),
                PatternNode(var="b", entity_type="Person", node_id=b),
                PatternNode(var="e", entity_type="Endpoint"),
            ],
            edges=[
                PatternEdge(edge_type="USES", from_var="a", to_var="e"),
                PatternEdge(edge_type="USES", from_var="b", to_var="e"),
            ],
        )
        subgraph = await adapter.match(pattern, CLEARED)
        found_ids = {n.id for n in subgraph.nodes}
        # `e` (the actual discovered common contact) is always present. `b` — the *secondary*
        # pinned root, listed second in `nodes` — is never returned: it is never `.as()`-labelled
        # outside its own nested `.where()` check, so there is nothing to select in the first
        # place. `a`, the primary root (`MatchBuilder`'s own internal choice, `nodes[0]` here), is
        # returned even though it is also pinned — a real, disclosed asymmetry (see `builders.py`
        # own comment): dropping it would force a single-argument `select()`, which Gremlin gives
        # a different result shape than the multi-argument form the adapter's own parsing expects.
        assert {a, e} <= found_ids
        assert b not in found_ids
        assert other not in found_ids


async def test_match_intersection_never_leaks_a_hidden_common_endpoint(
    factory: GraphAdapterFactory,
) -> None:
    """Standing rule 3/4, applied to the new diamond-pattern join: a common endpoint neither root
    principal can see must not appear in the result, count toward it, or otherwise be detectable —
    the same existence-leak discipline this suite's own header names, now proven for a *join*
    across two independently-filtered fragments rather than a single chain. An unauthorised
    principal asking "what do these two people have in common" must get back nothing that reveals
    a SECRET-only common endpoint exists at all, not even by a non-empty result of the wrong
    shape."""
    async with factory.context() as adapter:
        (a, b, hidden), _ = await _write(
            adapter,
            [
                _node("Person", classification="OFFICIAL"),
                _node("Person", classification="OFFICIAL"),
                _node("Endpoint", classification="SECRET"),
            ],
            [],
        )
        await _write(
            adapter,
            [],
            [
                _edge("USES", a, hidden, classification="OFFICIAL"),
                _edge("USES", b, hidden, classification="OFFICIAL"),
            ],
        )

        pattern = PatternQuery(
            nodes=[
                # Both principal endpoints pinned — B19's own real shape, and the same fixture
                # design `test_match_finds_the_intersection_across_two_independent_roots` uses.
                PatternNode(var="a", entity_type="Person", node_id=a),
                PatternNode(var="b", entity_type="Person", node_id=b),
                PatternNode(var="e", entity_type="Endpoint"),
            ],
            edges=[
                PatternEdge(edge_type="USES", from_var="a", to_var="e"),
                PatternEdge(edge_type="USES", from_var="b", to_var="e"),
            ],
        )

        official_result = await adapter.match(pattern, OFFICIAL)
        assert official_result.nodes == []
        assert hidden not in {n.id for n in official_result.nodes}

        # The SECRET-cleared principal, by contrast, really does see the intersection — proving
        # the empty result above is `OFFICIAL`'s own filtering, not a bug that would hide it from
        # everyone.
        cleared_result = await adapter.match(pattern, CLEARED)
        assert hidden in {n.id for n in cleared_result.nodes}


# --- pattern match: cardinality estimate ------------------------------------


async def test_match_honours_a_pinned_node_in_a_single_chain(factory: GraphAdapterFactory) -> None:
    """A pin is the analyst's "this node", so a chain from it is that node's, not its type's. The
    single-chain compiler once dropped every pin, answering "this person's phones" with every
    person's (found building ADR-100 stage 8)."""
    async with factory.context() as adapter:
        (p1, p2, e1, e2), _ = await _write(
            adapter,
            [_node("Person", classification="OFFICIAL"), _node("Person", classification="OFFICIAL"),
             _node("Endpoint", classification="OFFICIAL"),
             _node("Endpoint", classification="OFFICIAL")],
            [],
        )
        await _write(adapter, [], [_edge("USES", p1, e1, classification="OFFICIAL"),
                                   _edge("USES", p2, e2, classification="OFFICIAL")])
        uses = [PatternEdge(edge_type="USES", from_var="p", to_var="e")]
        from_pin = PatternQuery(nodes=[PatternNode(var="p", entity_type="Person", node_id=p1),
                                       PatternNode(var="e", entity_type="Endpoint")], edges=uses)
        to_pin = PatternQuery(nodes=[PatternNode(var="p", entity_type="Person"),
                                     PatternNode(var="e", entity_type="Endpoint", node_id=e2)],
                              edges=uses)
        assert {n.id for n in (await adapter.match(from_pin, CLEARED)).nodes} == {p1, e1}
        assert {n.id for n in (await adapter.match(to_pin, CLEARED)).nodes} == {p2, e2}
        assert await adapter.match_count(from_pin, CLEARED, ceiling=100) == 2


async def test_match_returns_every_node_it_counted_however_many_ways_they_match(
    factory: GraphAdapterFactory,
) -> None:
    """Rule 2: `limit` bounds the nodes a match returns, as `match_count` counts them, never the
    ways of matching. Four people each using the same four phones match sixteen ways; a limit of
    ten once cut the ways, so `run_pattern`, told 8 < 10, returned seven nodes as the whole
    answer (found building ADR-100 stage 8, where a shared contact matches many ways)."""
    async with factory.context() as adapter:
        people = [_node("Person", classification="OFFICIAL") for _ in range(4)]
        phones = [_node("Endpoint", classification="OFFICIAL") for _ in range(4)]
        await _write(adapter, [*people, *phones], [])
        await _write(adapter, [], [_edge("USES", p.id, e.id, classification="OFFICIAL")
                                   for p in people for e in phones])
        pattern = PatternQuery(
            nodes=[PatternNode(var="p", entity_type="Person"),
                   PatternNode(var="e", entity_type="Endpoint")],
            edges=[PatternEdge(edge_type="USES", from_var="p", to_var="e")],
            limit=10,
        )
        assert await adapter.match_count(pattern, CLEARED, ceiling=10) == 8
        found = await adapter.match(pattern, CLEARED)
        assert {n.id for n in found.nodes} == {w.id for w in [*people, *phones]}
        # Past the limit, it stops at the limit in nodes too.
        fewer = pattern.model_copy(update={"limit": 5})
        assert len((await adapter.match(fewer, CLEARED)).nodes) == 5



def _shared_contacts_pattern(*, two: bool) -> PatternQuery:
    """ADR-100 Amendment 7: `a` and `b` use the same endpoint `x` (`b` reached backwards from
    `x`), and, when `two`, the same second endpoint `y` (the last link joining two bound
    variables)."""
    nodes = [PatternNode(var="a", entity_type="Person"),
             PatternNode(var="x", entity_type="Endpoint"),
             PatternNode(var="b", entity_type="Person")]
    edges = [PatternEdge(edge_type="USES", from_var="a", to_var="x"),
             PatternEdge(edge_type="USES", from_var="b", to_var="x")]
    if two:
        nodes.append(PatternNode(var="y", entity_type="Endpoint"))
        edges += [PatternEdge(edge_type="USES", from_var="a", to_var="y"),
                  PatternEdge(edge_type="USES", from_var="b", to_var="y")]
    return PatternQuery(nodes=nodes, edges=edges)


async def _shared_world(adapter: GraphPort) -> dict[str, str]:
    """`a` and `b` both use `x` and `y`; `c` uses `x` alone; `a` also uses `z`; `d` alone uses
    `w`."""
    kinds = {"a": "Person", "b": "Person", "c": "Person", "d": "Person", "x": "Endpoint",
             "y": "Endpoint", "z": "Endpoint", "w": "Endpoint"}
    writes = {name: _node(kind, classification="OFFICIAL") for name, kind in kinds.items()}
    await _write(adapter, list(writes.values()), [])
    ids = {name: w.id for name, w in writes.items()}
    await _write(adapter, [], [
        _edge("USES", ids[s], ids[t], classification="OFFICIAL")
        for s, t in [("a", "x"), ("a", "y"), ("b", "x"), ("b", "y"), ("c", "x"), ("a", "z"),
                     ("d", "w")]
    ])
    return ids


async def test_match_finds_two_who_share_two_contacts(factory: GraphAdapterFactory) -> None:
    """ADR-100 Amendment 7: a step may walk a link backwards to a new variable and the last may
    join two bound ones; two variables never bind the same node, so the second shared endpoint is
    not the first again and nobody shares a contact with themselves."""
    async with factory.context() as adapter:
        ids = await _shared_world(adapter)
        name = {v: k for k, v in ids.items()}
        two = _shared_contacts_pattern(two=True)
        found = {name[n.id] for n in (await adapter.match(two, CLEARED)).nodes}
        assert found == {"a", "b", "x", "y"}
        assert await adapter.match_count(two, CLEARED, ceiling=100) == 4
        # Drawn in another order, the same pattern: the next link is whichever touches what is
        # already reached.
        redrawn = two.model_copy(update={"edges": list(reversed(two.edges))})
        assert {name[n.id] for n in (await adapter.match(redrawn, CLEARED)).nodes} == found
        one = _shared_contacts_pattern(two=False)
        found = {name[n.id] for n in (await adapter.match(one, CLEARED)).nodes}
        assert found == {"a", "b", "c", "x", "y"}  # never `d` and `w`: `d` paired with itself


async def test_shared_contacts_never_rest_on_what_the_reader_cannot_see(
    factory: GraphAdapterFactory,
) -> None:
    """Rules 3 and 4 for the new steps: a second shared endpoint the reader cannot see, or a link
    to it they cannot see, or one in another dataset, makes no match and is in no count."""
    async with factory.context() as adapter:
        ids = await _shared_world(adapter)
        two = _shared_contacts_pattern(two=True)
        hidden_y = _node("Endpoint", classification="SECRET")
        elsewhere_y = _node("Endpoint", classification="OFFICIAL", datasets=["enron"])
        q = _node("Person", classification="OFFICIAL")
        await _write(adapter, [hidden_y, elsewhere_y, q], [])
        await _write(adapter, [], [
            # `c` and `q` share `x` and a SECRET endpoint; `c` and `d` share `w` and, by a SECRET
            # link, `x`.
            _edge("USES", ids["c"], hidden_y.id, classification="OFFICIAL"),
            _edge("USES", q.id, ids["x"], classification="OFFICIAL"),
            _edge("USES", q.id, hidden_y.id, classification="OFFICIAL"),
            _edge("USES", ids["c"], ids["w"], classification="OFFICIAL"),
            _edge("USES", ids["d"], ids["x"], classification="SECRET"),
        ])
        name = {v: k for k, v in ids.items()}
        seen = await adapter.match(two, OFFICIAL)
        assert {name.get(n.id, n.id) for n in seen.nodes} == {"a", "b", "x", "y"}
        assert await adapter.match_count(two, OFFICIAL, ceiling=100) == 4
        # The filter is real: cleared, `c` and `q` share two, and so do `c` and `d`.
        cleared = {n.id for n in (await adapter.match(two, CLEARED)).nodes}
        assert {ids["c"], q.id, hidden_y.id, ids["d"], ids["w"]} <= cleared
        # Another dataset's endpoint is no shared contact for a fixture case.
        await _write(adapter, [], [
            _edge("USES", ids["c"], elsewhere_y.id, classification="OFFICIAL", datasets=["enron"]),
            _edge("USES", q.id, elsewhere_y.id, classification="OFFICIAL", datasets=["enron"]),
        ])
        in_fixture = OFFICIAL.model_copy(update={"datasets": ["fixture"]})
        assert (await adapter.match(two, in_fixture)).nodes == []



async def test_match_intersection_never_rests_on_a_hidden_link(factory: GraphAdapterFactory) -> None:
    """Rule 3 for B19's join: a common endpoint reached by the second root over a link the reader
    cannot see is not common. The reverse walk once stepped over links with `.in()`, checking only
    the nodes, so a SECRET link made a visible endpoint a common contact for an OFFICIAL reader,
    which told them the link existed (found building ADR-100 Amendment 7)."""
    async with factory.context() as adapter:
        (a, b, e), _ = await _write(
            adapter,
            [_node("Person", classification="OFFICIAL"), _node("Person", classification="OFFICIAL"),
             _node("Endpoint", classification="OFFICIAL")],
            [],
        )
        await _write(adapter, [], [_edge("USES", a, e, classification="OFFICIAL"),
                                   _edge("USES", b, e, classification="SECRET")])
        pattern = PatternQuery(
            nodes=[PatternNode(var="a", entity_type="Person", node_id=a),
                   PatternNode(var="b", entity_type="Person", node_id=b),
                   PatternNode(var="e", entity_type="Endpoint")],
            edges=[PatternEdge(edge_type="USES", from_var="a", to_var="e"),
                   PatternEdge(edge_type="USES", from_var="b", to_var="e")],
        )
        assert (await adapter.match(pattern, OFFICIAL)).nodes == []
        assert await adapter.match_count(pattern, OFFICIAL, ceiling=100) == 0
        # The filter is real: cleared, the endpoint is common.
        assert e in {n.id for n in (await adapter.match(pattern, CLEARED)).nodes}



async def test_match_count_agrees_with_the_filtered_results_own_count(
    factory: GraphAdapterFactory,
) -> None:
    """`GraphPort.match_count` is `match()`'s own cheaper cousin, not a second, independently
    -filtered channel — `02_GLASS_FRONTEND.md` §3.3's estimate and the eventual run result must
    never disagree when nothing was capped."""
    async with factory.context() as adapter:
        (a, b), _ = await _write(
            adapter,
            [
                _node("Person", classification="OFFICIAL"),
                _node("Endpoint", classification="OFFICIAL"),
            ],
            [],
        )
        await _write(adapter, [], [_edge("USES", a, b, classification="OFFICIAL")])

        pattern = PatternQuery(
            nodes=[
                PatternNode(var="p", entity_type="Person"),
                PatternNode(var="e", entity_type="Endpoint"),
            ],
            edges=[PatternEdge(edge_type="USES", from_var="p", to_var="e")],
        )
        count = await adapter.match_count(pattern, CLEARED, ceiling=1_000)
        subgraph = await adapter.match(pattern, CLEARED)
        assert count == len(subgraph.nodes) == 2


async def test_match_count_never_leaks_a_hidden_node(factory: GraphAdapterFactory) -> None:
    """The Glass never sees an unfiltered count, and an unauthorised principal must not detect a
    filtered node's existence via an aggregate: applied to the visual query builder's own
    estimate, which is shown to the analyst directly. A principal who cannot see a matching node
    must get a *smaller* count, not the same one with the node itself merely missing from a
    list."""
    async with factory.context() as adapter:
        (a, hidden), _ = await _write(
            adapter,
            [
                _node("Person", classification="OFFICIAL"),
                _node("Endpoint", classification="SECRET"),
            ],
            [],
        )
        await _write(adapter, [], [_edge("USES", a, hidden, classification="OFFICIAL")])

        pattern = PatternQuery(
            nodes=[
                PatternNode(var="p", entity_type="Person"),
                PatternNode(var="e", entity_type="Endpoint"),
            ],
            edges=[PatternEdge(edge_type="USES", from_var="p", to_var="e")],
        )
        official_count = await adapter.match_count(pattern, OFFICIAL, ceiling=1_000)
        cleared_count = await adapter.match_count(pattern, CLEARED, ceiling=1_000)
        assert official_count < cleared_count
        assert official_count == len((await adapter.match(pattern, OFFICIAL)).nodes)


async def test_match_count_is_a_floor_at_the_ceiling(factory: GraphAdapterFactory) -> None:
    """A count equal to `ceiling` is a floor ("at least"), never a claim that `ceiling` is the
    exact total — proven by matching a population strictly larger than a deliberately small
    ceiling and confirming the reported count is exactly the ceiling, not the true, larger
    total."""
    async with factory.context() as adapter:
        people = [_node("Person", classification="OFFICIAL") for _ in range(5)]
        (*person_ids,), _ = await _write(adapter, people, [])

        pattern = PatternQuery(nodes=[PatternNode(var="p", entity_type="Person")], edges=[])
        capped = await adapter.match_count(pattern, CLEARED, ceiling=3)
        uncapped = await adapter.match_count(pattern, CLEARED, ceiling=1_000)
        assert capped == 3
        assert uncapped == len(person_ids) == 5


# --- temporal filtering on the vertex-centric index -------------------------


async def test_expand_temporal_window_filters_edges_by_valid_from(
    factory: GraphAdapterFactory,
) -> None:
    async with factory.context() as adapter:
        (a, b, c), _ = await _write(
            adapter, [_node("Endpoint", classification="OFFICIAL") for _ in range(3)], []
        )
        now = datetime.now(UTC)
        await _write(
            adapter,
            [],
            [
                _edge(
                    "COMMUNICATED_WITH",
                    a,
                    b,
                    classification="OFFICIAL",
                    interval=Interval(valid_from=now - timedelta(days=30)),
                ),
                _edge(
                    "COMMUNICATED_WITH",
                    a,
                    c,
                    classification="OFFICIAL",
                    interval=Interval(valid_from=now),
                ),
            ],
        )

        window = Interval(valid_from=now - timedelta(hours=1), valid_to=now + timedelta(hours=1))
        subgraph = await adapter.expand(
            ExpandRequest(node_ids=[a], depth=1, temporal_window=window), CLEARED
        )
        reached = {n.id for n in subgraph.nodes}
        assert reached == {a, c}


# --- transactions -------------------------------------------------------------


async def test_rollback_discards_every_write_made_under_the_transaction(
    factory: GraphAdapterFactory,
) -> None:
    async with factory.context() as adapter:
        tx = await adapter.begin_transaction()
        (node_id,) = await adapter.upsert_nodes(
            [_node("Person", classification="OFFICIAL")], tx
        )
        await adapter.rollback_transaction(tx)

        assert await adapter.get_node(node_id, CLEARED) is None


# --- schema migration up and down --------------------------------------------


async def test_schema_migration_is_idempotent_and_reversible(
    factory: GraphAdapterFactory,
) -> None:
    """"Up" twice is a no-op; "down" — `revert_schema` — is provable through
    `GraphPort` itself, not by reaching into an adapter's private client
    (the conformance suite is the contract; a second adapter cannot satisfy
    a contract it must reach past the Protocol to prove)."""
    from ontology.loader import load_default_ontology
    from schemas.domain import EntityTypeDef, PoleClass

    ontology = load_default_ontology()
    async with factory.context() as adapter:
        # `factory.context()` already applied `ontology` once (version 3).
        up_again = await adapter.apply_schema(ontology)
        assert set(up_again.applied_entity_types) == {e.name for e in ontology.entity_types}

        extra_type = EntityTypeDef(
            name="Widget", pole_class=PoleClass.OBJECT, channel="rose", shape="star"
        )
        widened = ontology.model_copy(
            update={
                "version": ontology.version + 1,
                "entity_types": [*ontology.entity_types, extra_type],
            }
        )
        await adapter.apply_schema(widened)
        (widget_id,), _ = await _write(adapter, [_node("Widget", classification="OFFICIAL")], [])
        assert await adapter.get_node(widget_id, CLEARED) is not None

        reverted = await adapter.revert_schema(ontology.version)
        assert "Widget" not in set(reverted.applied_entity_types)

        # The dropped type is genuinely gone from both the adapter's
        # tracked schema and the live store, not just unlisted.
        with pytest.raises(OntologyError):
            await _write(adapter, [_node("Widget", classification="OFFICIAL")], [])

        (node_id,), _ = await _write(adapter, [_node("Person", classification="OFFICIAL")], [])
        assert await adapter.get_node(node_id, CLEARED) is not None


# --- find by identifier (the recipe engine's match_on/on_match) -------------


async def test_find_node_locates_an_existing_node_by_its_identifier_field(
    factory: GraphAdapterFactory,
) -> None:
    async with factory.context() as adapter:
        (node_id,), _ = await _write(
            adapter,
            [_node("Endpoint", classification="OFFICIAL", value_normalised="+441621926368")],
            [],
        )
        found = await adapter.find_node("Endpoint", "value_normalised", "+441621926368", CLEARED)
        assert found is not None
        assert found.id == node_id

        no_match = await adapter.find_node(
            "Endpoint", "value_normalised", "+440000000000", CLEARED
        )
        assert no_match is None


async def test_unauthorised_find_node_matches_a_graph_where_the_node_never_existed(
    factory: GraphAdapterFactory,
) -> None:
    async with factory.context() as adapter:
        await _write(
            adapter,
            [_node("Endpoint", classification="SECRET", value_normalised="+441621926368")],
            [],
        )
        assert (
            await adapter.find_node("Endpoint", "value_normalised", "+441621926368", OFFICIAL)
            is None
        )


async def test_search_nodes_matches_an_identifier_declared_on_any_entity_type(
    factory: GraphAdapterFactory,
) -> None:
    """`search_nodes` is `find_node` generalised across every entity type's
    declared `identifiers` — the caller does not name a type or field, the
    way `find_node`'s caller must."""
    async with factory.context() as adapter:
        (person_id,), _ = await _write(
            adapter, [_node("Person", classification="OFFICIAL", nino="AB123456C")], []
        )
        person_hits = await adapter.search_nodes("AB123456C", CLEARED)
        assert [n.id for n in person_hits] == [person_id]

        assert await adapter.search_nodes("no-such-value", CLEARED) == []


async def test_search_nodes_finds_an_endpoint_in_the_shape_the_engine_actually_writes(
    factory: GraphAdapterFactory,
) -> None:
    """**The case this suite was missing, and the reason it mattered — round 13cd.**

    The test above used to assert this too, with an `Endpoint` written as
    `_node("Endpoint", e164="+441621926368")`. **Nothing in this repository has ever written an
    `e164` property.** The ingest engine, every seeder and every fixture write `value_raw`,
    `value_normalised` and `endpoint_kind`; `01_DOMAIN_MODEL.md`'s `identifiers: [e164, handle,
    email, imsi]` names identifier *kinds*, not property names, and `endpoint_kind`'s own enum
    disagrees with it (`msisdn` where that list says `e164`).

    So the suite proved `search_nodes` worked by handing it a node shape the system never
    creates, and the real consequence went unnoticed until it was measured over the wire
    (REPORT-13bf): after a Studio load that demonstrably created the `Endpoint`,
    `POST /v1/search` for its number returned **0 hits**, twice, twenty minutes apart. An analyst
    could ingest a number and then be unable to look at it.

    This case writes the shape the engine emits and is what fails if the fix regresses.
    `CLAUDE.md` rule 15, inverted: there the planted violation was too convenient, here the
    fixture was.
    """
    async with factory.context() as adapter:
        (endpoint_id,), _ = await _write(
            adapter,
            [
                _node(
                    "Endpoint",
                    classification="OFFICIAL",
                    value_raw="01621926368",
                    value_normalised="+441621926368",
                    endpoint_kind="msisdn",
                )
            ],
            [],
        )

        hits = await adapter.search_nodes("+441621926368", CLEARED)
        assert [n.id for n in hits] == [endpoint_id], (
            "an Endpoint written the way the ingest engine writes one is not findable by its own "
            "normalised value — the analyst can load a number and then not find it"
        )

        # The raw rendering is deliberately *not* searchable: `01_DOMAIN_MODEL.md` §7 makes
        # `value_normalised` the canonical form, and matching `value_raw` as well would make the
        # same number findable under renderings that the normaliser exists to collapse.
        assert await adapter.search_nodes("01621926368", CLEARED) == []


async def test_unauthorised_search_matches_a_graph_where_the_node_never_existed(
    factory: GraphAdapterFactory,
) -> None:
    """The existence-leak discipline `test_unauthorised_find_node_*` proves
    for one named field/type must hold for `search_nodes` too: a SECRET
    node whose identifier exactly matches the query is invisible to an
    OFFICIAL principal, not merely redacted."""
    async with factory.context() as adapter:
        await _write(
            adapter, [_node("Person", classification="SECRET", nino="AB123456C")], []
        )
        assert await adapter.search_nodes("AB123456C", OFFICIAL) == []


# --- suggest_nodes (ADR-059): the search box as the analyst types ----------------------
#
# A prefix read, separate from search_nodes's exact-match contract above. Written before the
# adapter (rule 1); the unit tests beside the adapter run the same behaviour against a store
# double, and these run it against the real store.


async def test_suggest_nodes_finds_an_account_by_the_start_of_its_normalised_value(
    factory: GraphAdapterFactory,
) -> None:
    """The case the Glass hit: the account is findable by the whole value, so it must be findable
    by the start of it. Written in the shape the PaySim seed writes (`value_normalised`)."""
    async with factory.context() as adapter:
        (account_id,), _ = await _write(
            adapter,
            [
                _node(
                    "Endpoint",
                    classification="OFFICIAL",
                    value_raw="C1305486145",
                    value_normalised="C1305486145",
                    endpoint_kind="account",
                )
            ],
            [],
        )
        found = await adapter.suggest_nodes("C13054", CLEARED)
        assert [n.id for n in found.nodes] == [account_id] and found.more is False
        assert (await adapter.suggest_nodes("C9999", CLEARED)).nodes == []


async def test_applying_the_schema_makes_a_name_findable_on_a_node_written_before_it_was_indexed(
    factory: GraphAdapterFactory,
) -> None:
    """Seen 3 October 2026 (ADR-074): `Petrenko` found nothing although the node existed, because
    `family_name` became `indexed` after the node was written and the top-level copy the search
    reads is made at write time. The write is made as it would have been before (the field is
    emptied by hand), the suggestion finds nothing, and applying the schema again must repair it.

    Written before the repair, and **not yet run** against a live ArcadeDB by the session that
    wrote it: the `UPDATE ... SET field = properties.field` it relies on is the unproven part."""
    from adapters.graph_arcadedb.naming import physical_type_name
    from ontology.loader import load_default_ontology

    async with factory.context() as adapter:
        (person_id,), _ = await _write(
            adapter,
            [
                _node(
                    "Person", classification="OFFICIAL", family_name="Petrenko", given_names="Illia"
                )
            ],
            [],
        )
        person = physical_type_name("Person")
        await adapter._client.sql(  # type: ignore[attr-defined]
            f"UPDATE {person} SET family_name = null WHERE id = '{person_id}'"
        )
        assert (await adapter.suggest_nodes("Petrenko", CLEARED)).nodes == []

        await adapter.apply_schema(load_default_ontology())

        found = await adapter.suggest_nodes("Petrenko", CLEARED)
        assert [n.id for n in found.nodes] == [person_id]
        assert found.nodes[0].properties["family_name"] == "Petrenko"


async def test_suggest_nodes_says_when_more_matched_and_never_returns_more_than_the_limit(
    factory: GraphAdapterFactory,
) -> None:
    """Rule 2: a cut-off list says it was cut off."""
    async with factory.context() as adapter:
        for n in range(5):
            await _write(
                adapter,
                [
                    _node(
                        "Endpoint",
                        classification="OFFICIAL",
                        value_raw=f"C77{n}",
                        value_normalised=f"C77{n}",
                        endpoint_kind="account",
                    )
                ],
                [],
            )
        page = await adapter.suggest_nodes("C77", CLEARED, limit=3)
        assert len(page.nodes) == 3 and page.more is True
        everything = await adapter.suggest_nodes("C77", CLEARED, limit=5)
        assert len(everything.nodes) == 5 and everything.more is False


async def test_unauthorised_suggestions_match_a_graph_where_the_node_never_existed(
    factory: GraphAdapterFactory,
) -> None:
    """Rule 3 and 4: a SECRET account whose value starts with the prefix is not returned to an
    OFFICIAL principal, does not count toward the limit, and does not set `more`."""
    async with factory.context() as adapter:
        await _write(
            adapter,
            [
                _node(
                    "Endpoint",
                    classification="SECRET",
                    value_raw="C5550001",
                    value_normalised="C5550001",
                    endpoint_kind="account",
                )
            ],
            [],
        )
        (visible_id,), _ = await _write(
            adapter,
            [
                _node(
                    "Endpoint",
                    classification="OFFICIAL",
                    value_raw="C5550002",
                    value_normalised="C5550002",
                    endpoint_kind="account",
                )
            ],
            [],
        )
        found = await adapter.suggest_nodes("C555", OFFICIAL, limit=1)
        assert [n.id for n in found.nodes] == [visible_id]
        assert found.more is False, "a hidden match must not be detectable through `more`"


# --- suggest_nodes options (ADR-061): ignore case, match mode, entity types -------------
#
# **These are the cases that prove `TextP.regex('(?iu)...')` on the real engine.** The unit tests
# run the same behaviour against a store double that interprets the query; only a live store can
# say whether ArcadeDB's Gremlin accepts the regular-expression predicate and its `(?iu)` flag.
# If the first one fails here, ignoring case needs another route (ADR-061 says which).


async def _suggest_account(
    adapter: GraphPort, value: str, classification: str = "OFFICIAL"
) -> str:
    (node_id,), _ = await _write(
        adapter,
        [
            _node(
                "Endpoint",
                classification=classification,
                value_raw=value,
                value_normalised=value,
                endpoint_kind="account",
            )
        ],
        [],
    )
    return node_id


async def test_suggest_nodes_ignoring_case_finds_either_case_and_the_default_does_not(
    factory: GraphAdapterFactory,
) -> None:
    async with factory.context() as adapter:
        upper = await _suggest_account(adapter, "Jeff.Sorensen@enron.com")
        lower = await _suggest_account(adapter, "jeff.danforth@enron.com")
        plain = await adapter.suggest_nodes("jeff", CLEARED)
        assert [n.id for n in plain.nodes] == [lower]
        folded = await adapter.suggest_nodes(
            "JEFF", CLEARED, options=SuggestOptions(ignore_case=True)
        )
        assert {n.id for n in folded.nodes} == {upper, lower}


async def test_suggest_nodes_contains_and_exact_modes(
    factory: GraphAdapterFactory,
) -> None:
    async with factory.context() as adapter:
        whole = await _suggest_account(adapter, "C13")
        longer = await _suggest_account(adapter, "C130")
        inside = await _suggest_account(adapter, "xC13y")
        contains = await adapter.suggest_nodes(
            "C13", CLEARED, options=SuggestOptions(mode="contains")
        )
        assert {n.id for n in contains.nodes} == {whole, longer, inside}
        exact = await adapter.suggest_nodes(
            "C13", CLEARED, options=SuggestOptions(mode="exact")
        )
        assert [n.id for n in exact.nodes] == [whole]
        exact_folded = await adapter.suggest_nodes(
            "c13", CLEARED, options=SuggestOptions(mode="exact", ignore_case=True)
        )
        assert [n.id for n in exact_folded.nodes] == [whole], (
            "exact must not match C130"
        )


async def test_suggest_nodes_typed_regex_characters_are_text_not_a_pattern(
    factory: GraphAdapterFactory,
) -> None:
    """Catches typed text read as a regular expression when ignoring case: `.` must not be any
    character, and `+` and `(` must not break the query."""
    async with factory.context() as adapter:
        dotted = await _suggest_account(adapter, "a.b")
        await _suggest_account(adapter, "axb")
        found = await adapter.suggest_nodes(
            "a.b", CLEARED, options=SuggestOptions(mode="contains", ignore_case=True)
        )
        assert [n.id for n in found.nodes] == [dotted]
        odd = await adapter.suggest_nodes(
            "a+(b", CLEARED, options=SuggestOptions(mode="contains", ignore_case=True)
        )
        assert odd.nodes == []


async def test_suggest_nodes_ignoring_case_still_hides_what_the_principal_may_not_see(
    factory: GraphAdapterFactory,
) -> None:
    """Rule 3 and 4 for the new predicate: a SECRET match is not returned to an OFFICIAL
    principal, does not count toward the limit and does not set `more`."""
    async with factory.context() as adapter:
        await _suggest_account(adapter, "Zed-secret-1", classification="SECRET")
        visible = await _suggest_account(adapter, "zed-open-2")
        found = await adapter.suggest_nodes(
            "ZED", OFFICIAL, limit=1, options=SuggestOptions(ignore_case=True)
        )
        assert [n.id for n in found.nodes] == [visible]
        assert found.more is False


# --- suggest_locations (a disclosed known-gaps closure) ---------------------
#
# The geocoder's own candidate retrieval — a coarse, bounded substring scan
# over Location.name, deliberately separate from search_nodes's exact-match
# contract above (see GraphPort.suggest_locations's own docstring).


async def test_suggest_locations_matches_a_substring_of_the_name(
    factory: GraphAdapterFactory,
) -> None:
    async with factory.context() as adapter:
        (cranford_id,), _ = await _write(
            adapter, [_node("Location", classification="OFFICIAL", name="Cranford")], []
        )
        (cranbrook_id,), _ = await _write(
            adapter, [_node("Location", classification="OFFICIAL", name="Cranbrook")], []
        )
        await _write(
            adapter, [_node("Location", classification="OFFICIAL", name="Oxford")], []
        )

        hits = await adapter.suggest_locations("Cran", CLEARED)

        assert {n.id for n in hits} == {cranford_id, cranbrook_id}


async def test_suggest_locations_respects_the_limit(factory: GraphAdapterFactory) -> None:
    async with factory.context() as adapter:
        for name in ("Cranford", "Cranbrook", "Cranleigh"):
            await _write(
                adapter, [_node("Location", classification="OFFICIAL", name=name)], []
            )

        hits = await adapter.suggest_locations("Cran", CLEARED, limit=2)

        assert len(hits) == 2


async def test_suggest_locations_with_no_match_returns_empty(
    factory: GraphAdapterFactory,
) -> None:
    async with factory.context() as adapter:
        await _write(
            adapter, [_node("Location", classification="OFFICIAL", name="Oxford")], []
        )
        assert await adapter.suggest_locations("Cran", CLEARED) == []


async def test_unauthorised_suggest_locations_matches_a_graph_where_the_node_never_existed(
    factory: GraphAdapterFactory,
) -> None:
    """Existence-leak discipline, same as `search_nodes`'s own: a SECRET
    Location whose name matches is invisible to an OFFICIAL principal, and
    does not shrink `limit`'s effective headroom for visible results."""
    async with factory.context() as adapter:
        await _write(
            adapter, [_node("Location", classification="SECRET", name="Cranford")], []
        )
        assert await adapter.suggest_locations("Cran", OFFICIAL) == []


# --- list_nodes (06_DECISIONS.md ADR-025's corpus-wide population read) ----


async def test_list_nodes_returns_every_node_of_a_type_paginated(
    factory: GraphAdapterFactory,
) -> None:
    """Write more than one page's worth of `Person` nodes, plus a decoy
    `Endpoint`, and page through with a small `limit` until `next_cursor`
    is `None` — the union must be exactly the `Person` population, no
    more, no fewer, no duplicates, regardless of how many pages it took."""
    async with factory.context() as adapter:
        person_ids: list[str] = []
        for i in range(5):
            (node_id,), _ = await _write(
                adapter, [_node("Person", classification="OFFICIAL", family_name=f"P{i}")], []
            )
            person_ids.append(node_id)
        await _write(
            adapter, [_node("Endpoint", classification="OFFICIAL", value_normalised="+440")], []
        )

        seen: list[str] = []
        cursor: str | None = None
        pages = 0
        while True:
            page = await adapter.list_nodes("Person", CLEARED, cursor=cursor, limit=2)
            seen.extend(n.id for n in page.nodes)
            pages += 1
            if page.next_cursor is None:
                break
            cursor = page.next_cursor
            assert pages <= 10, "list_nodes did not converge — cursor is not advancing"

        assert sorted(seen) == sorted(person_ids)
        assert len(seen) == len(set(seen))
        assert pages >= 3  # 5 Person nodes at limit=2 must take at least 3 pages


async def test_list_nodes_single_page_exhausts_immediately(
    factory: GraphAdapterFactory,
) -> None:
    async with factory.context() as adapter:
        (node_id,), _ = await _write(
            adapter, [_node("Person", classification="OFFICIAL", family_name="Solo")], []
        )
        page = await adapter.list_nodes("Person", CLEARED, limit=500)
        assert [n.id for n in page.nodes] == [node_id]
        assert page.next_cursor is None


async def test_list_nodes_a_full_page_that_exactly_exhausts_the_type_still_needs_a_final_call(
    factory: GraphAdapterFactory,
) -> None:
    """The caller must check `next_cursor`, never infer exhaustion from a
    page coming back shorter than `limit` (`ListNodesPage`'s own docstring):
    when the population is an exact multiple of `limit`, a full page still
    carries a non-`None` `next_cursor`, and only the following, empty call
    reports `next_cursor is None`. A caller that stops as soon as a page
    looks "full enough" rather than checking the field itself would silently
    drop this exact-boundary case."""
    async with factory.context() as adapter:
        ids: list[str] = []
        for i in range(2):
            (node_id,), _ = await _write(
                adapter, [_node("Person", classification="OFFICIAL", family_name=f"B{i}")], []
            )
            ids.append(node_id)

        first = await adapter.list_nodes("Person", CLEARED, limit=2)
        assert sorted(n.id for n in first.nodes) == sorted(ids)
        assert first.next_cursor is not None

        second = await adapter.list_nodes("Person", CLEARED, cursor=first.next_cursor, limit=2)
        assert second.nodes == []
        assert second.next_cursor is None


async def test_unauthorised_list_nodes_matches_a_graph_where_the_node_never_existed(
    factory: GraphAdapterFactory,
) -> None:
    """Existence-leak discipline, extended to a paginated result: an
    OFFICIAL principal paging over a type that also has a SECRET member
    must see exactly the OFFICIAL ones, with the same page shape (count,
    final `next_cursor`) a graph with no SECRET member at all would give."""
    async with factory.context() as adapter:
        (visible_id,), _ = await _write(
            adapter, [_node("Person", classification="OFFICIAL", family_name="Visible")], []
        )
        await _write(
            adapter, [_node("Person", classification="SECRET", family_name="Hidden")], []
        )

        page = await adapter.list_nodes("Person", OFFICIAL, limit=500)
        assert [n.id for n in page.nodes] == [visible_id]
        assert page.next_cursor is None

        control = await adapter.list_nodes("Person", OFFICIAL, limit=500, cursor=None)
        assert len(control.nodes) == 1
        assert control.next_cursor is None


async def test_list_nodes_cursor_excludes_already_returned_nodes(
    factory: GraphAdapterFactory,
) -> None:
    async with factory.context() as adapter:
        (first_id,), _ = await _write(
            adapter, [_node("Person", classification="OFFICIAL", family_name="First")], []
        )
        (second_id,), _ = await _write(
            adapter, [_node("Person", classification="OFFICIAL", family_name="Second")], []
        )

        first_page = await adapter.list_nodes("Person", CLEARED, limit=1)
        assert len(first_page.nodes) == 1
        assert first_page.next_cursor is not None

        second_page = await adapter.list_nodes(
            "Person", CLEARED, cursor=first_page.next_cursor, limit=10
        )
        assert [n.id for n in second_page.nodes] == [
            i for i in (first_id, second_id) if i != first_page.nodes[0].id
        ]
        assert second_page.next_cursor is None


# --- edge summarisation, weight, and the load-ledger stamp ------------------


async def test_upserting_the_same_pair_twice_merges_into_one_edge(
    factory: GraphAdapterFactory,
) -> None:
    """`01_DOMAIN_MODEL.md` §3: one summarised edge per pair per type. A
    second load touching the same pair extends the existing edge's
    `occurrences` and `interval` — it must never add a second edge."""
    async with factory.context() as adapter:
        (a, b), _ = await _write(
            adapter,
            [
                _node("Endpoint", classification="OFFICIAL", value_normalised="+441111111111"),
                _node("Endpoint", classification="OFFICIAL", value_normalised="+442222222222"),
            ],
            [],
        )
        day1 = datetime(2026, 1, 1, tzinfo=UTC)
        day2 = datetime(2026, 1, 5, tzinfo=UTC)
        _, (first_edge_id,) = await _write(
            adapter,
            [],
            [
                _edge(
                    "COMMUNICATED_WITH",
                    a,
                    b,
                    classification="OFFICIAL",
                    occurrences=3,
                    interval=Interval(valid_from=day1, valid_to=day1),
                )
            ],
        )
        _, (second_edge_id,) = await _write(
            adapter,
            [],
            [
                _edge(
                    "COMMUNICATED_WITH",
                    a,
                    b,
                    classification="OFFICIAL",
                    occurrences=2,
                    interval=Interval(valid_from=day2, valid_to=day2),
                )
            ],
        )

        assert first_edge_id == second_edge_id
        assert (await adapter.neighbourhood_stats(a, CLEARED)).degree == 1

        subgraph = await adapter.expand(ExpandRequest(node_ids=[a], depth=1), CLEARED)
        (edge,) = subgraph.edges
        assert edge.occurrences == 5
        assert edge.interval == Interval(valid_from=day1, valid_to=day2)


async def test_upserting_the_same_pair_twice_retains_both_source_references(
    factory: GraphAdapterFactory,
) -> None:
    """`01_DOMAIN_MODEL.md` §7: "retaining every source row reference on
    the surviving event" — the same requirement applies to the summarised
    edge two separate loads both touch."""
    async with factory.context() as adapter:
        (a, b), _ = await _write(
            adapter,
            [
                _node("Endpoint", classification="OFFICIAL", value_normalised="+441111111111"),
                _node("Endpoint", classification="OFFICIAL", value_normalised="+442222222222"),
            ],
            [],
        )
        first_write = _edge("COMMUNICATED_WITH", a, b, classification="OFFICIAL", occurrences=1)
        await _write(adapter, [], [first_write])
        second_write = _edge("COMMUNICATED_WITH", a, b, classification="OFFICIAL", occurrences=1)
        second_write.provenance.sources[0].locator = "row 2"
        await _write(adapter, [], [second_write])

        subgraph = await adapter.expand(ExpandRequest(node_ids=[a], depth=1), CLEARED)
        (edge,) = subgraph.edges
        assert {s.locator for s in edge.provenance.sources} == {"p.1", "row 2"}


async def test_upserting_the_same_node_id_twice_merges_into_one_node(
    factory: GraphAdapterFactory,
) -> None:
    """Round 01's own finding, reproduced directly: `upsert_nodes` was a bare `INSERT`, so a
    second seed of a fixture with fixed ids (Fixture Corp's own `corp-res-distinct-2`, e.g.) failed
    on a duplicate key rather than updating the existing node. A second write for the same `id`
    must find and update it — never insert a second node under the same declared id, and never
    silently drop what the first write already recorded: `01_DOMAIN_MODEL.md` §7's provenance
    retention applies to nodes exactly as `test_upserting_the_same_pair_twice_retains_both_source_
    references` above already proves it does for edges."""
    async with factory.context() as adapter:
        first_write = _node(
            "Endpoint", classification="OFFICIAL", value_normalised="+441111111111"
        )
        await _write(adapter, [first_write], [])

        second_write = first_write.model_copy(deep=True)
        second_write.provenance.sources[0].locator = "row 2"
        await _write(adapter, [second_write], [])

        node = await adapter.get_node(first_write.id, CLEARED)
        assert node is not None, "the second write did not update the same node id"
        assert {s.locator for s in node.provenance.sources} == {
            first_write.provenance.sources[0].locator,
            "row 2",
        }
        assert node.audit.revision == 2


async def test_edge_weight_is_derived_not_hardcoded_and_persists_its_components(
    factory: GraphAdapterFactory,
) -> None:
    """Phase 1 wrote a hardcoded `0.0`, fixed in Phase 2 —
    `weight` must now be a real, positive value, and `weight_components`
    must persist the counts behind it so a later recompute is arithmetic
    over stored numbers, not a corpus rescan (`01_DOMAIN_MODEL.md` §6.1)."""
    async with factory.context() as adapter:
        (a, b), _ = await _write(
            adapter,
            [
                _node("Endpoint", classification="OFFICIAL", value_normalised="+441111111111"),
                _node("Endpoint", classification="OFFICIAL", value_normalised="+442222222222"),
            ],
            [],
        )
        _, (edge_id,) = await _write(
            adapter,
            [],
            [_edge("COMMUNICATED_WITH", a, b, classification="OFFICIAL", occurrences=10)],
        )
        subgraph = await adapter.expand(ExpandRequest(node_ids=[a], depth=1), CLEARED)
        (edge,) = subgraph.edges
        assert edge.id == edge_id
        assert edge.weight > 0.0
        assert edge.weight_components is not None
        assert edge.weight_components.occurrences == 10
        assert edge.weight_components.corpus_pair_count == 10
        assert edge.weight_components.corpus_total_occurrences >= 10


async def _links_among(adapter: GraphPort, node_ids: list[str]) -> list[Edge]:
    """Every link among `node_ids`, a self-loop included. `expand` cannot return a link from a
    node to itself, by design: its walk is `repeat(...otherV().simplePath())`
    (`builders.py`, `ExpandBuilder._repeat_clause`), and the node a self-loop leads back to is
    already on the path. `edges_among` has no such step (an edge whose two ends are both in the
    set, which a self-loop's are), so the self-loop is read through it, and the links `expand`
    returns are added by id."""
    reached = await adapter.expand(ExpandRequest(node_ids=node_ids, depth=1), CLEARED)
    among = await adapter.edges_among(node_ids, CLEARED)
    return list({e.id: e for e in [*reached.edges, *among]}.values())


def _past_interval() -> Interval:
    """An interval that ended 120 days ago, so a link's recency is below 1 (about 0.4)."""
    now = now_utc()
    return Interval(valid_from=now - timedelta(days=200), valid_to=now - timedelta(days=120))


#: The occurrences the weight fixture's links carry: an ordinary link at `a`, and a self-loop at `a`
#: whose own degree is therefore the other link's plus its own, counted twice.
OTHER_OCCURRENCES = 7
LOOP_OCCURRENCES = 3


async def _weighted_edges_by_label(adapter: GraphPort) -> dict[str, Edge]:
    """Links of four kinds, written through `upsert_edges` with an interval that ended in the past
    and read back: a counted type (`COMMUNICATED_WITH`), a self-loop of that type at a node that
    has other occurrences (so its normalised PMI would not be 0), a structural (fixed-weight) type
    and a type no version of the weights file names (`ASSOCIATE_OF`: `USES` took the default rule
    until version 3 gave it a fixed one). Keyed by label: the type's name, and `SELF_LOOP`."""
    (a, b, p, q), _ = await _write(
        adapter,
        [
            _node("Endpoint", classification="OFFICIAL", value_normalised="+441111111111"),
            _node("Endpoint", classification="OFFICIAL", value_normalised="+442222222222"),
            _node("Person", classification="OFFICIAL"),
            _node("Person", classification="OFFICIAL"),
        ],
        [],
    )
    interval = _past_interval()
    await _write(
        adapter,
        [],
        [
            _edge(
                "COMMUNICATED_WITH",
                a,
                b,
                classification="OFFICIAL",
                occurrences=OTHER_OCCURRENCES,
                interval=interval,
            ),
            _edge("FAMILY_OF", p, q, classification="OFFICIAL", occurrences=2, interval=interval),
            _edge(
                "ASSOCIATE_OF", p, q, classification="OFFICIAL", occurrences=3, interval=interval
            ),
        ],
    )
    # Written after the other link at `a`, so the store already holds its occurrences.
    await _write(
        adapter,
        [],
        [
            _edge(
                "COMMUNICATED_WITH",
                a,
                a,
                classification="OFFICIAL",
                occurrences=LOOP_OCCURRENCES,
                interval=interval,
            )
        ],
    )
    edges = await _links_among(adapter, [a, b, p, q])
    labelled: dict[str, Edge] = {}
    for edge in edges:
        label = "SELF_LOOP" if edge.source == edge.target else edge.type
        assert label not in labelled, f"{label} read back twice"
        labelled[label] = edge
    return labelled


def _recomputed(edge: Edge, rules: Any, self_loop: bool) -> float:
    """The weight the rules give a stored link's own components, at the `now` the adapter took
    (stored as `computed_at`) and the interval it was written with."""
    from adapters.graph_arcadedb.weight import compute_weight

    components = edge.weight_components
    assert components is not None
    return compute_weight(
        components,
        edge_type=edge.type,
        valid_to=edge.interval.valid_to if edge.interval else None,
        now=components.computed_at,
        rules=rules,
        self_loop=self_loop,
    )


@pytest.mark.parametrize("weights_version", [1, 2, 3])
async def test_every_stored_weight_carries_the_current_parameter_set(
    factory: GraphAdapterFactory, monkeypatch: pytest.MonkeyPatch, weights_version: int
) -> None:
    """ADR-120 D3: a weight computed under one calibration is not comparable with another, so every
    stored component names the version and rule it was computed under. Catches a write path that
    stores components with no parameter set, or one naming the wrong rule: a counted type, a
    self-loop of it, a structural type and a type with no rule of its own (which takes
    `default`)."""
    from ontology.weights import load_weight_history

    rules = load_weight_history()[weights_version - 1]
    assert rules.version == weights_version
    _use_weights_version(monkeypatch, weights_version)
    async with factory.context() as adapter:
        by_label = await _weighted_edges_by_label(adapter)
        assert set(by_label) == {"COMMUNICATED_WITH", "SELF_LOOP", "FAMILY_OF", "ASSOCIATE_OF"}
        for edge in by_label.values():
            assert edge.weight_components is not None, edge.type
            assert edge.weight_components.parameter_set == rules.parameter_set(edge.type)
        assert by_label["ASSOCIATE_OF"].weight_components is not None
        assert (
            by_label["ASSOCIATE_OF"].weight_components.parameter_set == f"{rules.version}/default"
        )
        assert by_label["SELF_LOOP"].weight_components is not None
        assert (
            by_label["SELF_LOOP"].weight_components.parameter_set
            == f"{rules.version}/COMMUNICATED_WITH"
        )


@pytest.mark.parametrize("weights_version", [1, 2, 3])
async def test_the_stored_weight_is_what_the_rules_compute(
    factory: GraphAdapterFactory, monkeypatch: pytest.MonkeyPatch, weights_version: int
) -> None:
    """ADR-120 D3, the weight on the wire equal to the weight computed, at the `now` the adapter
    took (stored as the components' `computed_at`) and with an interval in the past, so a recency
    that was ignored or taken as 1 shows. Catches a stored weight that does not follow from the
    components stored beside it under the rules in force, for a counted, a structural and a
    default-rule type and a self-loop.

    ADR-123: run under versions 1 and 2, and under version 3 (Amendment 9 decision 9), each
    pinned by index and given to the adapter (`_use_weights_version`), not "latest". Only version 1
    (gamma 0.3) makes the flag matter: a caller that passed the wrong `self_loop` stores another
    weight there, and the assertion below proves the case is one that term moves. Under versions 2
    and 3 the flag changes nothing, which is asserted too, so each case is what it claims to be."""
    from ontology.weights import load_weight_history

    rules = load_weight_history()[weights_version - 1]
    assert rules.version == weights_version
    _use_weights_version(monkeypatch, weights_version)
    async with factory.context() as adapter:
        for label, edge in (await _weighted_edges_by_label(adapter)).items():
            components = edge.weight_components
            assert components is not None, label
            assert edge.interval is not None and edge.interval.valid_to is not None, label
            assert components.computed_at > edge.interval.valid_to + timedelta(days=100), label
            assert components.parameter_set == rules.parameter_set(edge.type), label

            is_loop = edge.source == edge.target
            assert edge.weight == pytest.approx(_recomputed(edge, rules, is_loop), abs=1e-9), label
            if label in ("COMMUNICATED_WITH", "SELF_LOOP", "ASSOCIATE_OF"):
                other_flag = _recomputed(edge, rules, not is_loop)
                if weights_version == 1:
                    # A caller that passed the wrong flag would store another weight: the counts
                    # here give a non-zero mutual-information term.
                    assert abs(edge.weight - other_flag) > 1e-3, label
                else:
                    assert edge.weight == pytest.approx(other_flag, abs=1e-12), label


async def test_a_self_loop_counts_its_occurrences_twice_in_its_nodes_degree(
    factory: GraphAdapterFactory,
) -> None:
    """ADR-120 Amendment 4: the store reads a self-loop back twice from its node, so the stored
    degree counts its occurrences twice on the upsert path as on the bulk path. Catches an upsert
    that adds them once."""
    async with factory.context() as adapter:
        loop = (await _weighted_edges_by_label(adapter))["SELF_LOOP"]
        components = loop.weight_components
        assert components is not None
        assert components.occurrences == LOOP_OCCURRENCES
        expected_degree = OTHER_OCCURRENCES + 2 * LOOP_OCCURRENCES
        assert components.corpus_source_degree == expected_degree
        assert components.corpus_target_degree == expected_degree
        assert components.corpus_total_occurrences >= OTHER_OCCURRENCES + LOOP_OCCURRENCES


async def test_a_second_write_of_the_same_self_loop_counts_both_writes_twice(
    factory: GraphAdapterFactory,
) -> None:
    """ADR-120 Amendment 4: a self-loop is in its node's degree twice per occurrence, whether it is
    already stored or being written. Catches an upsert that counts the stored loop twice but the
    new write once: 7 at the node from another link, a loop written at 3 and again at 2, leaves
    7 + 2 x 3 + 2 x 2 = 17 in the degree, 5 in the pair, 12 in the type's total."""
    async with factory.context() as adapter:
        labelled = await _weighted_edges_by_label(adapter)
        loop = labelled["SELF_LOOP"]
        await _write(
            adapter,
            [],
            [
                _edge(
                    "COMMUNICATED_WITH",
                    loop.source,
                    loop.source,
                    classification="OFFICIAL",
                    occurrences=2,
                    interval=_past_interval(),
                )
            ],
        )
        again = [
            e
            for e in await _links_among(
                adapter, [loop.source, labelled["COMMUNICATED_WITH"].target]
            )
            if e.source == e.target
        ]
        assert len(again) == 1, "the second write must merge into the stored self-loop"
        components = again[0].weight_components
        assert components is not None
        expected_degree = OTHER_OCCURRENCES + 2 * LOOP_OCCURRENCES + 2 * 2
        assert expected_degree == 17
        assert components.occurrences == components.corpus_pair_count == LOOP_OCCURRENCES + 2
        assert components.corpus_source_degree == components.corpus_target_degree == 17
        assert components.corpus_total_occurrences == OTHER_OCCURRENCES + LOOP_OCCURRENCES + 2


async def test_a_superseded_link_stores_the_current_parameter_set_and_the_rules_weight(
    factory: GraphAdapterFactory,
) -> None:
    """`supersede_edge` weighs its replacement like any write. Catches the replacement storing no
    parameter set, the default rule's, or a weight that is not the rules' for its own components:
    a counted type and a structural one."""
    from ontology.weights import load_weight_rules

    rules = load_weight_rules()
    async with factory.context() as adapter:
        (a, b, p, q), _ = await _write(
            adapter,
            [
                _node("Endpoint", classification="OFFICIAL", value_normalised="+441111111111"),
                _node("Endpoint", classification="OFFICIAL", value_normalised="+442222222222"),
                _node("Person", classification="OFFICIAL"),
                _node("Person", classification="OFFICIAL"),
            ],
            [],
        )
        _, (old_comm, old_family) = await _write(
            adapter,
            [],
            [
                _edge("COMMUNICATED_WITH", a, b, classification="OFFICIAL", occurrences=2),
                _edge("FAMILY_OF", p, q, classification="OFFICIAL", occurrences=2),
            ],
        )
        tx = await adapter.begin_transaction()
        await adapter.supersede_edge(
            old_comm,
            _edge(
                "COMMUNICATED_WITH",
                a,
                b,
                classification="OFFICIAL",
                occurrences=9,
                interval=_past_interval(),
            ),
            tx,
        )
        await adapter.supersede_edge(
            old_family,
            _edge("FAMILY_OF", p, q, classification="OFFICIAL", interval=_past_interval()),
            tx,
        )
        await adapter.commit_transaction(tx)

        subgraph = await adapter.expand(ExpandRequest(node_ids=[a, b, p, q], depth=1), CLEARED)
        by_type = {edge.type: edge for edge in subgraph.edges}
        assert set(by_type) == {"COMMUNICATED_WITH", "FAMILY_OF"}
        for edge_type, edge in by_type.items():
            components = edge.weight_components
            assert components is not None and edge.interval is not None, edge_type
            assert components.parameter_set == rules.parameter_set(edge_type), edge_type
            assert edge.weight == pytest.approx(_recomputed(edge, rules, False), abs=1e-9), (
                edge_type
            )
        assert by_type["FAMILY_OF"].weight == 0.75
        assert by_type["COMMUNICATED_WITH"].weight_components is not None
        assert by_type["COMMUNICATED_WITH"].weight_components.occurrences == 9


async def test_a_superseded_link_does_not_count_in_the_corpus(
    factory: GraphAdapterFactory,
) -> None:
    """ADR-120 Amendment 5 decision 1: a superseded link's occurrences live on in its successor, so
    the corpus counts leave the superseded link out, as every read does. Violated by a degree or
    total query that filters only `reverted`: the link written after the supersede then stores a
    degree and a type total that count the old link's 5 occurrences as well as the successor's 2
    (11 and 11 instead of 6 and 6), and the successor itself is weighed against counts that include
    the link it replaced (its degree 7, not 2).

    a -> b is written at 5, superseded by a link at 2, then a -> c is written at 4. The new link's
    degree at `a` is the successor's 2 plus its own 4, its type's total 2 + 4, and neither counts
    the superseded 5."""
    async with factory.context() as adapter:
        (a, b, c), _ = await _write(
            adapter,
            [
                _node("Endpoint", classification="OFFICIAL", value_normalised="+441111111111"),
                _node("Endpoint", classification="OFFICIAL", value_normalised="+442222222222"),
                _node("Endpoint", classification="OFFICIAL", value_normalised="+443333333333"),
            ],
            [],
        )
        _, (old_link,) = await _write(
            adapter,
            [],
            [
                _edge(
                    "COMMUNICATED_WITH",
                    a,
                    b,
                    classification="OFFICIAL",
                    occurrences=5,
                    interval=_past_interval(),
                )
            ],
        )
        tx = await adapter.begin_transaction()
        successor = await adapter.supersede_edge(
            old_link,
            _edge(
                "COMMUNICATED_WITH",
                a,
                b,
                classification="OFFICIAL",
                occurrences=2,
                interval=_past_interval(),
            ),
            tx,
        )
        await adapter.commit_transaction(tx)
        _, (later_link,) = await _write(
            adapter,
            [],
            [
                _edge(
                    "COMMUNICATED_WITH",
                    a,
                    c,
                    classification="OFFICIAL",
                    occurrences=4,
                    interval=_past_interval(),
                )
            ],
        )

        by_id = {e.id: e for e in await _links_among(adapter, [a, b, c])}
        assert set(by_id) == {successor, later_link}, "the superseded link must not be read"

        replaced = by_id[successor].weight_components
        assert replaced is not None
        assert replaced.occurrences == replaced.corpus_pair_count == 2
        assert replaced.corpus_source_degree == 2, "the successor is weighed against its own 2 only"
        assert replaced.corpus_total_occurrences == 2

        later = by_id[later_link].weight_components
        assert later is not None
        assert later.corpus_pair_count == 4
        assert later.corpus_source_degree == 2 + 4
        assert later.corpus_target_degree == 4
        assert later.corpus_total_occurrences == 2 + 4


async def test_load_ledger_stamp_is_recorded_on_every_written_element(
    factory: GraphAdapterFactory,
) -> None:
    """ADR-018: "every loaded element is stamped with the recipe version
    that produced it" — the point being that a month-six mapping error is a
    query against the graph itself, not an excavation through a ledger."""
    async with factory.context() as adapter:
        (node_id,), _ = await _write(
            adapter,
            [
                _node(
                    "Person",
                    classification="OFFICIAL",
                    load_id="load-abc",
                    recipe_id="cdr-carrier-a",
                    recipe_version=4,
                )
            ],
            [],
        )
        node = await adapter.get_node(node_id, CLEARED)
        assert node is not None
        assert node.audit.load_id == "load-abc"
        assert node.audit.recipe_id == "cdr-carrier-a"
        assert node.audit.recipe_version == 4


# --- revert ------------------------------------------------------------------


async def test_reverted_node_is_invisible_to_every_read_any_clearance(
    factory: GraphAdapterFactory,
) -> None:
    """A reverted element is a third, non-principal-dependent axis
    (`01_DOMAIN_MODEL.md` §2.4) — unlike a hidden `SECRET` record, even the
    most highly cleared principal must not see it, because it was
    retracted, not merely restricted."""
    async with factory.context() as adapter:
        (node_id,), _ = await _write(adapter, [_node("Person", classification="OFFICIAL")], [])
        assert await adapter.get_node(node_id, CLEARED) is not None

        tx = await adapter.begin_transaction()
        await adapter.revert_elements([node_id], [], tx)
        await adapter.commit_transaction(tx)

        assert await adapter.get_node(node_id, CLEARED) is None


async def test_reverted_edge_is_invisible_and_excluded_from_corpus_statistics(
    factory: GraphAdapterFactory,
) -> None:
    async with factory.context() as adapter:
        (a, b), _ = await _write(
            adapter,
            [
                _node("Endpoint", classification="OFFICIAL", value_normalised="+441111111111"),
                _node("Endpoint", classification="OFFICIAL", value_normalised="+442222222222"),
            ],
            [],
        )
        _, (edge_id,) = await _write(
            adapter,
            [],
            [_edge("COMMUNICATED_WITH", a, b, classification="OFFICIAL", occurrences=5)],
        )
        assert (await adapter.neighbourhood_stats(a, CLEARED)).degree == 1

        tx = await adapter.begin_transaction()
        await adapter.revert_elements([], [edge_id], tx)
        await adapter.commit_transaction(tx)

        assert (await adapter.neighbourhood_stats(a, CLEARED)).degree == 0
        subgraph = await adapter.expand(ExpandRequest(node_ids=[a], depth=1), CLEARED)
        assert subgraph.edges == []

        # A later load touching the same pair starts a fresh edge rather
        # than resurrecting the retracted one.
        _, (new_edge_id,) = await _write(
            adapter,
            [],
            [_edge("COMMUNICATED_WITH", a, b, classification="OFFICIAL", occurrences=1)],
        )
        assert new_edge_id != edge_id
        subgraph_after = await adapter.expand(ExpandRequest(node_ids=[a], depth=1), CLEARED)
        (live_edge,) = subgraph_after.edges
        # 1, not 6 — the reverted edge's occurrences do not carry over.
        assert live_edge.occurrences == 1


async def test_revert_elements_on_an_empty_or_unknown_id_is_a_safe_no_op(
    factory: GraphAdapterFactory,
) -> None:
    async with factory.context() as adapter:
        tx = await adapter.begin_transaction()
        await adapter.revert_elements([], [], tx)
        await adapter.revert_elements(["not-a-real-id"], ["not-a-real-id-either"], tx)
        await adapter.commit_transaction(tx)


# --- supersession (corrections) ------------------------------------------------


async def test_superseded_node_is_excluded_from_default_reads(
    factory: GraphAdapterFactory,
) -> None:
    """`01_DOMAIN_MODEL.md` §2.4: "Nodes are versioned, not overwritten. A
    correction writes a new revision and points the old one forward." The
    old revision must not appear in an ordinary read once superseded, any
    more than a reverted element does."""
    async with factory.context() as adapter:
        (old_id,), _ = await _write(
            adapter, [_node("Person", classification="OFFICIAL", family_name="Original")], []
        )
        tx = await adapter.begin_transaction()
        new_id = await adapter.supersede_node(
            old_id,
            _node("Person", classification="OFFICIAL", family_name="Corrected"),
            tx,
        )
        await adapter.commit_transaction(tx)

        assert new_id != old_id
        assert await adapter.get_node(old_id, CLEARED) is None
        new_node = await adapter.get_node(new_id, CLEARED)
        assert new_node is not None
        assert new_node.properties["family_name"] == "Corrected"


async def test_superseded_node_is_retrievable_by_explicit_revision(
    factory: GraphAdapterFactory,
) -> None:
    async with factory.context() as adapter:
        (old_id,), _ = await _write(
            adapter, [_node("Person", classification="OFFICIAL", family_name="Original")], []
        )
        tx = await adapter.begin_transaction()
        new_id = await adapter.supersede_node(
            old_id,
            _node("Person", classification="OFFICIAL", family_name="Corrected"),
            tx,
        )
        await adapter.commit_transaction(tx)

        old_revision = await adapter.get_node(old_id, CLEARED, include_superseded=True)
        assert old_revision is not None
        assert old_revision.properties["family_name"] == "Original"
        assert old_revision.audit.superseded_by == new_id
        assert old_revision.audit.revision == 1

        new_revision = await adapter.get_node(new_id, CLEARED, include_superseded=True)
        assert new_revision is not None
        assert new_revision.audit.revision == 2
        assert new_revision.audit.superseded_by is None


async def test_superseded_by_chain_is_traversable_across_two_corrections(
    factory: GraphAdapterFactory,
) -> None:
    async with factory.context() as adapter:
        (id_a,), _ = await _write(
            adapter, [_node("Person", classification="OFFICIAL", family_name="A")], []
        )
        tx1 = await adapter.begin_transaction()
        id_b = await adapter.supersede_node(
            id_a, _node("Person", classification="OFFICIAL", family_name="B"), tx1
        )
        await adapter.commit_transaction(tx1)

        tx2 = await adapter.begin_transaction()
        id_c = await adapter.supersede_node(
            id_b, _node("Person", classification="OFFICIAL", family_name="C"), tx2
        )
        await adapter.commit_transaction(tx2)

        # Walk the chain forward from the oldest revision.
        node_a = await adapter.get_node(id_a, CLEARED, include_superseded=True)
        node_b = await adapter.get_node(id_b, CLEARED, include_superseded=True)
        node_c = await adapter.get_node(id_c, CLEARED, include_superseded=True)
        assert node_a is not None and node_a.audit.superseded_by == id_b
        assert node_b is not None and node_b.audit.superseded_by == id_c
        assert node_c is not None and node_c.audit.superseded_by is None

        # Only the tip is visible by default.
        assert await adapter.get_node(id_a, CLEARED) is None
        assert await adapter.get_node(id_b, CLEARED) is None
        live = await adapter.get_node(id_c, CLEARED)
        assert live is not None
        assert live.properties["family_name"] == "C"


async def test_include_superseded_does_not_bypass_classification(
    factory: GraphAdapterFactory,
) -> None:
    """The escape hatch is for history, not for clearance. An
    OFFICIAL-cleared principal asking for a superseded revision must not
    see one that was — and remains — SECRET."""
    async with factory.context() as adapter:
        (old_id,), _ = await _write(
            adapter, [_node("Person", classification="SECRET", family_name="Hidden")], []
        )
        tx = await adapter.begin_transaction()
        await adapter.supersede_node(
            old_id, _node("Person", classification="SECRET", family_name="Still hidden"), tx
        )
        await adapter.commit_transaction(tx)

        assert await adapter.get_node(old_id, OFFICIAL, include_superseded=True) is None
        assert await adapter.get_node(old_id, CLEARED, include_superseded=True) is not None


async def test_supersede_node_carries_its_whole_network_to_the_replacement(
    factory: GraphAdapterFactory,
) -> None:
    """A correction must not silently disconnect the corrected node from
    its own network — `superseded_by` alone does nothing to the edges
    still recorded against the old id (see `_repoint_incident_edges`).
    Degree 3 on the old node (two outgoing, one incoming, so both
    directions are covered) must read as degree 3 on the replacement, and
    zero — not an error, not a partial count — on the now-hidden original."""
    async with factory.context() as adapter:
        (person, contact_a, contact_b, contact_c), _ = await _write(
            adapter,
            [
                _node("Person", classification="OFFICIAL", family_name="Original"),
                _node("Person", classification="OFFICIAL", family_name="Contact A"),
                _node("Person", classification="OFFICIAL", family_name="Contact B"),
                _node("Person", classification="OFFICIAL", family_name="Contact C"),
            ],
            [],
        )
        await _write(
            adapter,
            [],
            [
                _edge("ASSOCIATE_OF", person, contact_a, classification="OFFICIAL"),
                _edge("ASSOCIATE_OF", person, contact_b, classification="OFFICIAL"),
                _edge("ASSOCIATE_OF", contact_c, person, classification="OFFICIAL"),
            ],
        )
        assert (await adapter.neighbourhood_stats(person, CLEARED)).degree == 3

        tx = await adapter.begin_transaction()
        new_id = await adapter.supersede_node(
            person, _node("Person", classification="OFFICIAL", family_name="Corrected"), tx
        )
        await adapter.commit_transaction(tx)

        assert (await adapter.neighbourhood_stats(new_id, CLEARED)).degree == 3
        subgraph = await adapter.expand(ExpandRequest(node_ids=[new_id], depth=1), CLEARED)
        new_neighbours = {n.id for n in subgraph.nodes} - {new_id}
        assert new_neighbours == {contact_a, contact_b, contact_c}

        # The old node is unreachable by default — not merely hidden itself,
        # its former edges do not leave a trace either.
        assert await adapter.get_node(person, CLEARED) is None
        assert (await adapter.neighbourhood_stats(person, CLEARED)).degree == 0


async def test_a_links_own_basis_round_trips_and_survives_supersede_node(
    factory: GraphAdapterFactory,
) -> None:
    """ADR-081 step B. A link may carry a basis of its own (a link of a Direct type marked
    probabilistic); a link written without one carries none, and takes its type's basis when it is
    drawn. The store must hand back exactly what was written, and a correction to a node
    (`supersede_node`) must clone the mark onto the re-pointed edge rather than drop it: a link an
    analyst declared probabilistic must not turn solid because the person at one end was
    corrected."""
    async with factory.context() as adapter:
        (person, marked_contact, plain_contact), _ = await _write(
            adapter,
            [
                _node("Person", classification="OFFICIAL", family_name="Original"),
                _node("Person", classification="OFFICIAL", family_name="Marked"),
                _node("Person", classification="OFFICIAL", family_name="Plain"),
            ],
            [],
        )
        await _write(
            adapter,
            [],
            [
                _edge(
                    "ASSOCIATE_OF", person, marked_contact, classification="OFFICIAL",
                    basis="probabilistic",
                ),
                _edge("ASSOCIATE_OF", person, plain_contact, classification="OFFICIAL"),
            ],
        )

        def basis_by_target(subgraph) -> dict[str, str | None]:  # type: ignore[no-untyped-def]
            return {e.target: e.basis for e in subgraph.edges}

        before = await adapter.expand(ExpandRequest(node_ids=[person], depth=1), CLEARED)
        assert basis_by_target(before) == {marked_contact: "probabilistic", plain_contact: None}

        tx = await adapter.begin_transaction()
        new_id = await adapter.supersede_node(
            person, _node("Person", classification="OFFICIAL", family_name="Corrected"), tx
        )
        await adapter.commit_transaction(tx)

        after = await adapter.expand(ExpandRequest(node_ids=[new_id], depth=1), CLEARED)
        assert basis_by_target(after) == {marked_contact: "probabilistic", plain_contact: None}


async def test_supersede_node_retains_each_cloned_edges_original_provenance(
    factory: GraphAdapterFactory,
) -> None:
    """A cloned edge's evidence did not change because the node it points
    at was corrected — `_clone_edge_onto` must carry the exact original
    `Provenance` (state, every `SourceRef`, `extracted_by`,
    `extraction_confidence`) onto the new edge, not a fresh one. Losing it
    would break §5's judgement-review loop for any judgement citing that
    edge: the citation would still resolve, but to evidence that no
    longer says where it came from."""
    async with factory.context() as adapter:
        (person, contact), _ = await _write(
            adapter,
            [
                _node("Person", classification="OFFICIAL", family_name="Original"),
                _node("Person", classification="OFFICIAL", family_name="Contact"),
            ],
            [],
        )
        multi_source_edge = EdgeWrite(
            id=new_edge_id(),
            type="ASSOCIATE_OF",
            source=person,
            target=contact,
            provenance=Provenance(
                state=ProvenanceState.INFERRED,
                sources=[
                    SourceRef(document_id="doc-1", locator="p.1", excerpt_hash="a" * 64),
                    SourceRef(document_id="doc-2", locator="p.7", excerpt_hash="b" * 64),
                ],
                extracted_by="model:qwen2-vl:7b@2026-05-02",
                extraction_confidence=0.82,
                first_seen=datetime(2026, 1, 1, tzinfo=UTC),
            ),
            handling=_handling("OFFICIAL"),  # type: ignore[arg-type]
            created_by="loader-1",
            created_at=now_utc(),
        )
        _, (original_edge_id,) = await _write(adapter, [], [multi_source_edge])

        tx = await adapter.begin_transaction()
        new_id = await adapter.supersede_node(
            person, _node("Person", classification="OFFICIAL", family_name="Corrected"), tx
        )
        await adapter.commit_transaction(tx)

        subgraph = await adapter.expand(ExpandRequest(node_ids=[new_id], depth=1), CLEARED)
        (cloned_edge,) = subgraph.edges
        assert cloned_edge.id != original_edge_id
        assert cloned_edge.provenance.state == ProvenanceState.INFERRED
        assert cloned_edge.provenance.extracted_by == "model:qwen2-vl:7b@2026-05-02"
        assert cloned_edge.provenance.extraction_confidence == 0.82
        source_tuples = {
            (s.document_id, s.locator, s.excerpt_hash) for s in cloned_edge.provenance.sources
        }
        assert source_tuples == {
            ("doc-1", "p.1", "a" * 64),
            ("doc-2", "p.7", "b" * 64),
        }


async def test_supersede_node_rollback_leaves_zero_trace_of_the_partial_operation(
    factory: GraphAdapterFactory,
) -> None:
    """`supersede_node` is several separate writes under one transaction —
    the new node, the old node's `superseded_by`, a clone per incident
    edge, and marking the originals reverted. The recovery path for a
    failure partway through is the same as for any other write: the
    caller rolls back rather than commits, and everything done under that
    transaction is discarded, not left half-migrated. Proven here against
    the public API (rollback after a real, successful-but-uncommitted
    `supersede_node`), not by faking an internal failure an adapter's own
    implementation detail — a second `GraphPort` adapter must hold the
    same guarantee without sharing that detail."""
    async with factory.context() as adapter:
        (person, contact_a, contact_b), _ = await _write(
            adapter,
            [
                _node("Person", classification="OFFICIAL", family_name="Original"),
                _node("Person", classification="OFFICIAL", family_name="Contact A"),
                _node("Person", classification="OFFICIAL", family_name="Contact B"),
            ],
            [],
        )
        await _write(
            adapter,
            [],
            [
                _edge("ASSOCIATE_OF", person, contact_a, classification="OFFICIAL"),
                _edge("ASSOCIATE_OF", person, contact_b, classification="OFFICIAL"),
            ],
        )

        tx = await adapter.begin_transaction()
        new_id = await adapter.supersede_node(
            person, _node("Person", classification="OFFICIAL", family_name="Corrected"), tx
        )
        await adapter.rollback_transaction(tx)

        # The entire operation is undone: the original node, at its
        # original degree, with no trace of the replacement.
        original = await adapter.get_node(person, CLEARED)
        assert original is not None
        assert original.audit.superseded_by is None
        assert (await adapter.neighbourhood_stats(person, CLEARED)).degree == 2
        assert await adapter.get_node(new_id, CLEARED) is None


async def test_supersede_edge_replaces_it_in_default_reads(
    factory: GraphAdapterFactory,
) -> None:
    """`01_DOMAIN_MODEL.md` §3/§5: an edge carries `AuditStub` too, and a
    `Judgement` can cite one directly as evidence — a corrected edge must
    leave that citation resolvable to a `superseded_by` pointer, not just
    disappear. Exercises the same exclusion mechanism as node supersession,
    with no repointing needed (nothing else references an edge by id)."""
    async with factory.context() as adapter:
        (a, b), _ = await _write(
            adapter,
            [
                _node("Person", classification="OFFICIAL", family_name="A"),
                _node("Person", classification="OFFICIAL", family_name="B"),
            ],
            [],
        )
        _, (old_edge_id,) = await _write(
            adapter, [], [_edge("ASSOCIATE_OF", a, b, classification="OFFICIAL")]
        )

        tx = await adapter.begin_transaction()
        replacement_edge_id = await adapter.supersede_edge(
            old_edge_id,
            EdgeWrite(
                id=new_edge_id(),
                type="ASSOCIATE_OF",
                source=a,
                target=b,
                provenance=_provenance(),
                handling=_handling("OFFICIAL"),  # type: ignore[arg-type]
                created_by="reviewer-1",
                created_at=now_utc(),
            ),
            tx,
        )
        await adapter.commit_transaction(tx)

        assert replacement_edge_id != old_edge_id
        subgraph = await adapter.expand(ExpandRequest(node_ids=[a], depth=1), CLEARED)
        (edge,) = subgraph.edges
        assert edge.id == replacement_edge_id
        assert edge.audit.revision == 2
        assert edge.audit.superseded_by is None


async def test_a_write_after_supersede_merges_into_the_replacement_edge(
    factory: GraphAdapterFactory,
) -> None:
    """`01_DOMAIN_MODEL.md` §3: one summarised edge per pair — after `supersede_edge` (a
    confirmation, a recorded conflict) the pair's edge is the replacement. Catches a later write
    for the same pair being merged into the superseded edge instead, which every default read
    excludes, so the new evidence would vanish.

    The replacement is stored the other way round (an undirected type, so the same pair): ArcadeDB
    returns a vertex's out-edges before its in-edges, so the superseded `a`-to-`b` edge comes first
    from `a` and a lookup that does not exclude it finds it. Written the same way round, the newer
    replacement happens to come first and the defect does not show."""
    async with factory.context() as adapter:
        (a, b), _ = await _write(
            adapter,
            [
                _node("Person", classification="OFFICIAL", family_name="A"),
                _node("Person", classification="OFFICIAL", family_name="B"),
            ],
            [],
        )
        _, (old_edge_id,) = await _write(
            adapter, [], [_edge("ASSOCIATE_OF", a, b, classification="OFFICIAL")]
        )
        tx = await adapter.begin_transaction()
        replacement_edge_id = await adapter.supersede_edge(
            old_edge_id, _edge("ASSOCIATE_OF", b, a, classification="OFFICIAL"), tx
        )
        await adapter.commit_transaction(tx)

        later = _edge("ASSOCIATE_OF", a, b, classification="OFFICIAL", occurrences=2)
        later.provenance.sources[0].locator = "row 9"
        _, (merged_id,) = await _write(adapter, [], [later])

        assert merged_id == replacement_edge_id
        subgraph = await adapter.expand(ExpandRequest(node_ids=[a], depth=1), CLEARED)
        (edge,) = subgraph.edges
        assert edge.id == replacement_edge_id
        assert edge.occurrences == 3
        assert "row 9" in {s.locator for s in edge.provenance.sources}


async def test_an_inferred_write_never_lowers_an_asserted_same_as_link(
    factory: GraphAdapterFactory,
) -> None:
    """`01_DOMAIN_MODEL.md` §2.1 and §4: a manual link is a `SAME_AS` with score 1.0, `asserted`,
    and only an analyst changes it. Catches a later resolution run's inferred write for the same
    pair turning it back into `inferred` at the model's lower score — the link would quietly stop
    collapsing the pair at any τ above that score."""
    async with factory.context() as adapter:
        (a, b), _ = await _write(
            adapter,
            [
                _node("Person", classification="OFFICIAL", family_name="A"),
                _node("Person", classification="OFFICIAL", family_name="B"),
            ],
            [],
        )

        def same_as(score: float, provenance: Provenance, **extra: str) -> EdgeWrite:
            return EdgeWrite(
                id=new_edge_id(),
                type="SAME_AS",
                source=a,
                target=b,
                properties={"score": score, **extra},
                provenance=provenance,
                handling=_handling("OFFICIAL"),  # type: ignore[arg-type]
                created_by="writer-1",
                created_at=now_utc(),
            )

        manual = _provenance().model_copy(
            update={"confirmed_by": "analyst-1", "last_confirmed": now_utc()}
        )
        _, (link_id,) = await _write(adapter, [], [same_as(1.0, manual)])
        model_run = Provenance(
            state=ProvenanceState.INFERRED,
            sources=[SourceRef(document_id="splink:a:b", locator="model-2", excerpt_hash="")],
            first_seen=now_utc(),
            extraction_confidence=0.4,
        )
        await _write(adapter, [], [same_as(0.4, model_run, model_version="model-2")])

        subgraph = await adapter.expand(
            ExpandRequest(node_ids=[a], depth=1, edge_types=["SAME_AS"]), CLEARED
        )
        (edge,) = subgraph.edges
        assert edge.id == link_id
        assert edge.provenance.state is ProvenanceState.ASSERTED
        assert edge.provenance.confirmed_by == "analyst-1"
        assert edge.provenance.extraction_confidence is None
        assert edge.properties == {"score": 1.0}
        assert {s.locator for s in edge.provenance.sources} == {"p.1", "model-2"}


# --- existence-leak assertions ------------------------------------------------


async def test_unauthorised_get_node_matches_a_graph_where_the_node_never_existed(
    factory: GraphAdapterFactory,
) -> None:
    async with factory.context() as adapter:
        (hidden,), _ = await _write(adapter, [_node("Person", classification="SECRET")], [])
        assert await adapter.get_node(hidden, OFFICIAL) is None
        assert await adapter.get_node("not-a-real-id-at-all", OFFICIAL) is None


async def test_unauthorised_degree_count_matches_a_graph_without_the_hidden_neighbour(
    factory: GraphAdapterFactory,
) -> None:
    async with factory.context() as adapter:
        (hub,), _ = await _write(adapter, [_node("Person", classification="OFFICIAL")], [])
        (visible,), _ = await _write(adapter, [_node("Endpoint", classification="OFFICIAL")], [])
        await _write(adapter, [], [_edge("USES", hub, visible, classification="OFFICIAL")])
        before_hidden_edge = await adapter.neighbourhood_stats(hub, OFFICIAL)

        (secret_neighbour,), _ = await _write(
            adapter, [_node("Endpoint", classification="SECRET")], []
        )
        await _write(adapter, [], [_edge("USES", hub, secret_neighbour, classification="SECRET")])
        after_hidden_edge = await adapter.neighbourhood_stats(hub, OFFICIAL)

        # Adding a SECRET neighbour must not move the OFFICIAL-cleared
        # degree count by even one — the two observations are identical.
        assert before_hidden_edge == after_hidden_edge

        authorised_view = await adapter.neighbourhood_stats(hub, CLEARED)
        assert authorised_view.degree == 2  # proves the filter is real, not a no-op


async def test_unauthorised_path_length_matches_a_graph_without_the_hidden_hop(
    factory: GraphAdapterFactory,
) -> None:
    async with factory.context() as adapter:
        (a, b, target), _ = await _write(
            adapter,
            [
                _node("Person", classification="OFFICIAL"),
                _node("Person", classification="OFFICIAL"),
                _node("Person", classification="OFFICIAL"),
            ],
            [],
        )
        await _write(
            adapter,
            [],
            [
                _edge("ASSOCIATE_OF", a, b, classification="OFFICIAL"),
                _edge("ASSOCIATE_OF", b, target, classification="OFFICIAL"),
            ],
        )
        # A shorter, hidden route a->target directly, at SECRET.
        await _write(adapter, [], [_edge("ASSOCIATE_OF", a, target, classification="SECRET")])

        unauthorised = await adapter.paths(
            PathRequest(source=a, target=target, max_hops=6, k=5), OFFICIAL
        )
        authorised = await adapter.paths(
            PathRequest(source=a, target=target, max_hops=6, k=5), CLEARED
        )

        # The unauthorised principal only ever sees the 2-hop route — the
        # 1-hop SECRET shortcut is invisible, not merely deprioritised.
        assert {p.length for p in unauthorised} == {2}
        assert {p.length for p in authorised} == {1, 2}


async def test_unauthorised_match_never_returns_the_hidden_node(
    factory: GraphAdapterFactory,
) -> None:
    async with factory.context() as adapter:
        (person, secret_endpoint), _ = await _write(
            adapter,
            [
                _node("Person", classification="OFFICIAL"),
                _node("Endpoint", classification="SECRET"),
            ],
            [],
        )
        await _write(
            adapter, [], [_edge("USES", person, secret_endpoint, classification="SECRET")]
        )

        pattern = PatternQuery(
            nodes=[
                PatternNode(var="p", entity_type="Person"),
                PatternNode(var="e", entity_type="Endpoint"),
            ],
            edges=[PatternEdge(edge_type="USES", from_var="p", to_var="e")],
        )
        result = await adapter.match(pattern, OFFICIAL)
        assert secret_endpoint not in {n.id for n in result.nodes}


async def test_an_unrecognised_clearance_sees_nothing_rather_than_everything(
    factory: GraphAdapterFactory,
) -> None:
    async with factory.context() as adapter:
        (node_id,), _ = await _write(adapter, [_node("Person", classification="OFFICIAL")], [])
        assert await adapter.get_node(node_id, UNKNOWN_CLEARANCE) is None


# --- the second access axis: handling_code, scoped by owning_unit ----------
#
# `01_DOMAIN_MODEL.md` §2.2's field-by-field table: `classification` alone
# is a partial implementation — it passes every existence-leak test above
# and still discloses a recipient-restricted (`handling_code: R`) record to
# a principal outside its owning unit. Same three assertions as the
# classification axis (get_node, degree, path length), against a record
# that is fully within the OFFICIAL-cleared unauthorised principal's
# classification but restricted to a unit it doesn't belong to.


async def test_restricted_record_visible_only_to_the_owning_unit_and_receivable_set(
    factory: GraphAdapterFactory,
) -> None:
    async with factory.context() as adapter:
        (restricted,), _ = await _write(
            adapter,
            [
                _node(
                    "Person",
                    classification="OFFICIAL",
                    handling_code="R",
                    owning_unit="unit-restricted",
                )
            ],
            [],
        )

        in_unit_and_receives_r = Principal(
            id="a1",
            clearance="OFFICIAL",
            org_unit="unit-restricted",
            receivable_handling_codes=["R"],
        )
        wrong_unit_but_receives_r = Principal(
            id="a2",
            clearance="OFFICIAL",
            org_unit="unit-elsewhere",
            receivable_handling_codes=["R"],
        )
        right_unit_but_does_not_receive_r = Principal(
            id="a3", clearance="OFFICIAL", org_unit="unit-restricted"
        )

        assert (await adapter.get_node(restricted, in_unit_and_receives_r)) is not None
        assert (await adapter.get_node(restricted, wrong_unit_but_receives_r)) is None
        assert (await adapter.get_node(restricted, right_unit_but_does_not_receive_r)) is None
        # OFFICIAL's clearance dominates the record's classification, and it
        # is otherwise the same principal shape as every other test in this
        # suite — classification alone would have let it through.
        assert (await adapter.get_node(restricted, OFFICIAL)) is None


async def test_unauthorised_degree_count_matches_a_graph_without_the_wrong_unit_neighbour(
    factory: GraphAdapterFactory,
) -> None:
    async with factory.context() as adapter:
        (hub,), _ = await _write(adapter, [_node("Person", classification="OFFICIAL")], [])
        (visible,), _ = await _write(adapter, [_node("Endpoint", classification="OFFICIAL")], [])
        await _write(adapter, [], [_edge("USES", hub, visible, classification="OFFICIAL")])
        before = await adapter.neighbourhood_stats(hub, OFFICIAL)

        (restricted_neighbour,), _ = await _write(
            adapter,
            [
                _node(
                    "Endpoint",
                    classification="OFFICIAL",
                    handling_code="R",
                    owning_unit="unit-restricted",
                )
            ],
            [],
        )
        await _write(
            adapter,
            [],
            [
                _edge(
                    "USES",
                    hub,
                    restricted_neighbour,
                    classification="OFFICIAL",
                    handling_code="R",
                    owning_unit="unit-restricted",
                )
            ],
        )
        after = await adapter.neighbourhood_stats(hub, OFFICIAL)

        # OFFICIAL's clearance covers this record's classification
        # entirely — only the unit scoping on the restricted `handling_code`
        # hides it. A classification-only filter would have let this count
        # move.
        assert before == after

        in_unit = Principal(
            id="a1",
            clearance="OFFICIAL",
            org_unit="unit-restricted",
            receivable_handling_codes=["R"],
        )
        assert (await adapter.neighbourhood_stats(hub, in_unit)).degree == 2


async def test_edges_sharing_an_endpoint_written_in_one_batch_are_each_stored_once(
    factory: GraphAdapterFactory,
) -> None:
    """Seen, 30 September 2026, on the owner's machine: a load of 13,068 transactions stored 13,076,
    eight ids twice, each pair identical to the microsecond (one write, two records), and a hub
    account among the targets of two of the pairs. Every edge test here wrote its edges to a shared
    endpoint in *separate* transactions, so none could see a vertex that is reached twice inside
    one uncommitted batch. A batch is how every load writes (40 at a time), and a hub account is
    exactly what a real dataset is made of. Both ends are covered: a shared target, then a shared
    source. Each edge must be stored once and the shared endpoint's degree must be the number of
    edges written."""
    async with factory.context() as adapter:
        nodes, _ = await _write(
            adapter,
            [
                _node("Endpoint", classification="OFFICIAL", value_normalised=f"+4411111111{n:02d}")
                for n in range(8)
            ],
            [],
        )
        target, *sources = nodes[:4]
        source, *targets = nodes[4:]

        into_target = [
            _edge("COMMUNICATED_WITH", s, target, classification="OFFICIAL") for s in sources
        ]
        out_of_source = [
            _edge("COMMUNICATED_WITH", source, t, classification="OFFICIAL") for t in targets
        ]
        _, written_in = await _write(adapter, [], into_target)
        _, written_out = await _write(adapter, [], out_of_source)

        for hub, edges, written in (
            (target, into_target, written_in),
            (source, out_of_source, written_out),
        ):
            subgraph = await adapter.expand(ExpandRequest(node_ids=[hub], depth=1), CLEARED)
            assert sorted(e.id for e in subgraph.edges) == sorted(e.id for e in edges)
            assert sorted(written) == sorted(e.id for e in edges)
            assert (await adapter.neighbourhood_stats(hub, CLEARED)).degree == len(edges)


async def test_a_hub_receiving_many_edges_across_batches_stores_each_edge_once(
    factory: GraphAdapterFactory,
) -> None:
    """Seen, 30 September 2026: eight of 13,068 transactions were stored twice, rare, identical to
    the microsecond, and hub accounts were among their targets. The case above (three edges into a
    fresh hub) passed, so it does not reproduce it. This one is built like the real load: the
    directed `TRANSACTED` type with its properties and a timestamp, one hub that receives 300 edges
    and another that sends 100, written 40 to a transaction as the seed writes them, so a hub's edge
    list grows across many batches and inside them. Every edge must be stored once."""
    async with factory.context() as adapter:
        hub_in, hub_out, *others = [
            _node("Endpoint", classification="OFFICIAL", value_normalised=f"+44{n:010d}")
            for n in range(402)
        ]
        ids: list[str] = []
        for start in range(0, len(others) + 2, 40):
            batch = [hub_in, hub_out, *others][start : start + 40]
            written, _ = await _write(adapter, batch, [])
            ids.extend(written)
        hub_in_id, hub_out_id, *other_ids = ids
        sources, targets = other_ids[:300], other_ids[300:]

        day = datetime(2017, 1, 1, tzinfo=UTC)
        edges = [
            _edge(
                "TRANSACTED",
                s,
                hub_in_id,
                classification="OFFICIAL",
                interval=Interval(valid_from=day),
            )
            for s in sources
        ] + [
            _edge(
                "TRANSACTED",
                hub_out_id,
                t,
                classification="OFFICIAL",
                interval=Interval(valid_from=day),
            )
            for t in targets
        ]
        edges = [
            e.model_copy(
                update={"properties": {"amount": float(i + 1), "transaction_type": "CASH_IN"}}
            )
            for i, e in enumerate(edges)
        ]
        for start in range(0, len(edges), 40):
            await _write(adapter, [], edges[start : start + 40])

        for hub, expected in ((hub_in_id, edges[:300]), (hub_out_id, edges[300:])):
            subgraph = await adapter.expand(ExpandRequest(node_ids=[hub], depth=1), CLEARED)
            stored = [e.id for e in subgraph.edges]
            assert len(stored) == len(set(stored)), "an edge id is stored more than once"
            assert sorted(stored) == sorted(e.id for e in expected)
            assert (await adapter.neighbourhood_stats(hub, CLEARED)).degree == len(expected)


# --- edges_among: the links among a set of nodes (ADR-098 decision 1) -------------------------


async def test_edges_among_gives_the_links_between_leaves_that_an_expansion_leaves_out(
    factory: GraphAdapterFactory,
) -> None:
    """The owner's star (ADR-098): expanding a hub returns the hub's own links only, so the link
    between two of its leaves is never drawn. `edges_among` over the hub and its leaves returns it,
    and returns no link that leaves the set."""
    async with factory.context() as adapter:
        (hub, a, b, outside), _ = await _write(
            adapter, [_node("Person", classification="OFFICIAL") for _ in range(4)], []
        )
        _, (hub_a, hub_b, a_b, b_out) = await _write(
            adapter,
            [],
            [
                _edge("ASSOCIATE_OF", hub, a, classification="OFFICIAL"),
                _edge("ASSOCIATE_OF", hub, b, classification="OFFICIAL"),
                _edge("ASSOCIATE_OF", a, b, classification="OFFICIAL"),
                _edge("ASSOCIATE_OF", b, outside, classification="OFFICIAL"),
            ],
        )
        expanded = await adapter.expand(ExpandRequest(node_ids=[hub], depth=1), CLEARED)
        assert a_b not in {e.id for e in expanded.edges}

        among = await adapter.edges_among([hub, a, b], CLEARED)
        assert {e.id for e in among} == {hub_a, hub_b, a_b}
        assert b_out not in {e.id for e in among}


async def test_unauthorised_edges_among_shows_no_hidden_link_and_no_link_to_a_hidden_node(
    factory: GraphAdapterFactory,
) -> None:
    """Rule 3: a SECRET link between two OFFICIAL nodes, and an OFFICIAL link to a SECRET node,
    leave no trace for an OFFICIAL analyst; a SECRET-cleared one sees both."""
    async with factory.context() as adapter:
        (a, b, secret_node), _ = await _write(
            adapter,
            [
                _node("Person", classification="OFFICIAL"),
                _node("Person", classification="OFFICIAL"),
                _node("Person", classification="SECRET"),
            ],
            [],
        )
        _, (visible, hidden_link, to_hidden) = await _write(
            adapter,
            [],
            [
                _edge("ASSOCIATE_OF", a, b, classification="OFFICIAL"),
                _edge("FAMILY_OF", a, b, classification="SECRET"),
                _edge("ASSOCIATE_OF", b, secret_node, classification="OFFICIAL"),
            ],
        )
        seen = {e.id for e in await adapter.edges_among([a, b, secret_node], OFFICIAL)}
        assert seen == {visible}
        cleared = {e.id for e in await adapter.edges_among([a, b, secret_node], CLEARED)}
        assert cleared == {visible, hidden_link, to_hidden}


async def test_edges_among_filters_to_the_declared_edge_types(factory: GraphAdapterFactory) -> None:
    async with factory.context() as adapter:
        (a, b), _ = await _write(
            adapter, [_node("Person", classification="OFFICIAL") for _ in range(2)], []
        )
        _, (assoc, family) = await _write(
            adapter,
            [],
            [
                _edge("ASSOCIATE_OF", a, b, classification="OFFICIAL"),
                _edge("FAMILY_OF", a, b, classification="OFFICIAL"),
            ],
        )
        only = await adapter.edges_among([a, b], CLEARED, edge_types=["FAMILY_OF"])
        assert {e.id for e in only} == {family}
        assert assoc not in {e.id for e in only}


async def test_edges_among_an_empty_or_single_node_set_is_empty(
    factory: GraphAdapterFactory,
) -> None:
    async with factory.context() as adapter:
        (a,), _ = await _write(adapter, [_node("Person", classification="OFFICIAL")], [])
        assert await adapter.edges_among([], CLEARED) == []
        assert await adapter.edges_among([a], CLEARED) == []


# --- ADR-124 (U1): two reads by id, filtered in the adapter -------------------------------------
#
# `get_nodes` and `get_edges` look the given ids up and nothing else. Whatever the reason an id is
# not readable (above the reader's clearance, a restricted handling code, another dataset, a
# correction that replaced it, a revert, or no such id at all) it is left out the same way, so the
# result for a list is the result for the list without those ids. A link comes back only when it
# and both its ends are readable. Each reason below is its own case, so a plant that lifts one step
# of the access filter fails the case for that step by name; the mixed cases fail too, but alone
# they would not say which step it was. A link's two ends are checked separately in the query, so
# each axis is a case for the source end and for the target end. For every reason a principal can
# read past, a positive control reads the id with only that axis opened: without it, a lookup that
# finds nothing would pass every case here.

#: A reader for a case over one dataset: OFFICIAL, in `unit-1`, receiving no restricted code.
READER = Principal(id="reader-enron", clearance="OFFICIAL", org_unit="unit-1", datasets=["enron"])

_NODE_REASONS = ["clearance", "handling_code", "dataset", "superseded", "reverted", "absent"]
#: A reason ending `_source` or `_target` is an unreadable end of a readable link.
_EDGE_REASONS = [
    "clearance",
    "handling_code",
    "dataset",
    "hidden_source",
    "hidden_target",
    "reverted_source",
    "reverted_target",
    "dataset_source",
    "dataset_target",
    "restricted_source",
    "restricted_target",
    "superseded",
    "reverted",
    "absent",
]
#: Differs from `READER` in one axis each: a second dataset, and the restricted code `R` of the
#: unit that owns what the "restricted" cases write.
READER_BOTH = READER.model_copy(update={"datasets": ["enron", "fixture"]})
RESTRICTED_READER = Principal(
    id="reader-restricted",
    clearance="OFFICIAL",
    org_unit="unit-restricted",
    receivable_handling_codes=["R"],
    datasets=["enron"],
)


async def _unreadable_node(adapter: GraphPort, reason: str) -> str:
    """The id of one node `READER` cannot read, for `reason`; every other axis is open."""
    if reason == "absent":
        return new_node_id()
    if reason == "clearance":
        nodes = [_node("Person", classification="SECRET", datasets=["enron"])]
    elif reason == "handling_code":
        nodes = [
            _node(
                "Person",
                classification="OFFICIAL",
                handling_code="R",
                owning_unit="unit-restricted",
                datasets=["enron"],
            )
        ]
    elif reason == "dataset":
        nodes = [_node("Person", classification="OFFICIAL", datasets=["fixture"])]
    else:
        nodes = [_node("Person", classification="OFFICIAL", datasets=["enron"])]
    (node_id,), _ = await _write(adapter, nodes, [])
    if reason == "superseded":
        tx = await adapter.begin_transaction()
        await adapter.supersede_node(
            node_id, _node("Person", classification="OFFICIAL", datasets=["enron"]), tx
        )
        await adapter.commit_transaction(tx)
    elif reason == "reverted":
        tx = await adapter.begin_transaction()
        await adapter.revert_elements([node_id], [], tx)
        await adapter.commit_transaction(tx)
    return node_id


async def test_get_nodes_returns_readable_nodes_ordered_by_id(
    factory: GraphAdapterFactory,
) -> None:
    async with factory.context() as adapter:
        written, _ = await _write(
            adapter,
            [
                _node("Person", classification="OFFICIAL", datasets=["enron"], family_name=name)
                for name in ("A", "B", "C")
            ],
            [],
        )
        # Asked for out of order: the result is ordered by id, not by the order asked.
        nodes = await adapter.get_nodes([written[2], written[0], written[1]], READER)
        assert [n.id for n in nodes] == sorted(written)
        by_id = {n.id: n for n in nodes}
        assert by_id[written[0]].properties["family_name"] == "A"
        assert by_id[written[2]].datasets == ["enron"]


@pytest.mark.parametrize("reason", _NODE_REASONS)
async def test_get_nodes_leaves_out_an_unreadable_id_whatever_the_reason(
    factory: GraphAdapterFactory, reason: str
) -> None:
    async with factory.context() as adapter:
        (readable,), _ = await _write(
            adapter, [_node("Person", classification="OFFICIAL", datasets=["enron"])], []
        )
        unreadable = await _unreadable_node(adapter, reason)

        assert [n.id for n in await adapter.get_nodes([unreadable, readable], READER)] == [readable]
        # The one id on its own gives the empty list, not an error and not a marker.
        assert await adapter.get_nodes([unreadable], READER) == []
        # What the reason hides is real: a principal for whom it is open reads it (the filter
        # works, it is not a lookup that finds nothing).
        if reason in ("clearance", "dataset"):
            opener = CLEARED if reason == "clearance" else READER_BOTH
            assert [n.id for n in await adapter.get_nodes([unreadable], opener)] == [unreadable]
        if reason == "handling_code":
            opened = await adapter.get_nodes([unreadable], RESTRICTED_READER)
            assert [n.id for n in opened] == [unreadable]


async def test_get_nodes_of_a_mixed_list_is_exactly_the_readable_subset(
    factory: GraphAdapterFactory,
) -> None:
    async with factory.context() as adapter:
        readable, _ = await _write(
            adapter,
            [_node("Person", classification="OFFICIAL", datasets=["enron"]) for _ in range(3)],
            [],
        )
        unreadable = [await _unreadable_node(adapter, reason) for reason in _NODE_REASONS]
        # A correction's replacement is a readable node of its own: only the old revision goes.
        replacement_source = await _unreadable_node(adapter, "superseded")
        revision = await adapter.get_node(replacement_source, CLEARED, include_superseded=True)
        assert revision is not None and revision.audit.superseded_by is not None
        readable = [*readable, revision.audit.superseded_by]

        asked = [*unreadable, *readable, replacement_source]
        nodes = await adapter.get_nodes(asked, READER)
        assert [n.id for n in nodes] == sorted(readable)
        # The same as the list without the unreadable ids: nothing in the result says they exist.
        assert nodes == await adapter.get_nodes(readable, READER)


async def test_get_nodes_returns_a_duplicated_id_once(factory: GraphAdapterFactory) -> None:
    async with factory.context() as adapter:
        (a, b), _ = await _write(
            adapter,
            [_node("Person", classification="OFFICIAL", datasets=["enron"]) for _ in "ab"],
            [],
        )
        nodes = await adapter.get_nodes([b, a, b, a, a], READER)
        assert [n.id for n in nodes] == sorted([a, b])


async def test_get_nodes_of_no_ids_is_empty(factory: GraphAdapterFactory) -> None:
    async with factory.context() as adapter:
        await _write(adapter, [_node("Person", classification="OFFICIAL", datasets=["enron"])], [])
        assert await adapter.get_nodes([], READER) == []


async def test_get_nodes_past_one_chunk_returns_exactly_the_readable_ones(
    factory: GraphAdapterFactory,
) -> None:
    """The port chunks at 1,000 ids per query. 1,050 readable nodes, 50 hidden ones and 50 absent
    ids, mixed so that every chunk holds some of each and the last, partial chunk holds readable
    ones: a chunker that stops at the last full chunk, or that repeats or skips a boundary id,
    changes the count."""
    async with factory.context() as adapter:
        tx = await adapter.begin_transaction()
        readable = await adapter.upsert_nodes(
            [_node("Person", classification="OFFICIAL", datasets=["enron"]) for _ in range(1050)],
            tx,
        )
        hidden = await adapter.upsert_nodes(
            [_node("Person", classification="SECRET", datasets=["enron"]) for _ in range(50)], tx
        )
        await adapter.commit_transaction(tx)
        absent = [new_node_id() for _ in range(50)]

        asked: list[str] = []
        for i, node_id in enumerate(readable):
            asked.append(node_id)
            if i % 21 == 0 and absent:
                asked.append(absent.pop())
            if i % 21 == 10 and hidden:
                asked.append(hidden.pop())
        assert len(asked) > 1000
        assert asked[-1] in readable  # the last, partial chunk holds readable nodes

        nodes = await adapter.get_nodes(asked, READER)
        assert [n.id for n in nodes] == sorted(readable)


@dataclass(frozen=True)
class _Unreadable:
    """A link `READER` cannot read. `opener` is a principal who differs from `READER` in just the
    one axis that hides it and so can read it: the proof that the lookup finds the link and the
    filter is what leaves it out. `None` when no principal can (superseded, reverted, absent).
    `replacement` is the link that took a superseded one's place, which is readable."""

    id: str
    opener: Principal | None = None
    replacement: str | None = None


async def _readable_pair(adapter: GraphPort) -> tuple[str, str]:
    """Two fresh nodes `READER` can read, in the case's dataset. Every link below gets its own
    pair, so no two of them are the same pair and type, which the store would merge into one."""
    (a, b), _ = await _write(
        adapter,
        [_node("Person", classification="OFFICIAL", datasets=["enron"]) for _ in "ab"],
        [],
    )
    return a, b


async def _readable_link(adapter: GraphPort) -> str:
    a, b = await _readable_pair(adapter)
    _, (edge_id,) = await _write(
        adapter, [], [_edge("ASSOCIATE_OF", a, b, classification="OFFICIAL", datasets=["enron"])]
    )
    return edge_id


async def _unreadable_edge(adapter: GraphPort, reason: str) -> _Unreadable:
    """One link `READER` cannot read, for `reason`; every other axis is open. A reason ending
    `_source` or `_target` is one *end* that is unreadable while the link itself is readable: the
    query checks each end on its own, so each axis on each side is its own case."""
    if reason == "absent":
        return _Unreadable(new_edge_id())
    a, b = await _readable_pair(adapter)
    link: dict[str, Any] = {"classification": "OFFICIAL", "datasets": ["enron"]}
    opener: Principal | None = None
    revert_end: str | None = None  # reverted once the link is written to it, not before
    end_axis, _, side = reason.rpartition("_")
    if side in ("source", "target"):
        end = {
            "hidden": _node("Person", classification="SECRET", datasets=["enron"]),
            "reverted": _node("Person", classification="OFFICIAL", datasets=["enron"]),
            "dataset": _node("Person", classification="OFFICIAL", datasets=["fixture"]),
            "restricted": _node(
                "Person",
                classification="OFFICIAL",
                handling_code="R",
                owning_unit="unit-restricted",
                datasets=["enron"],
            ),
        }[end_axis]
        (end_id,), _ = await _write(adapter, [end], [])
        a, b = (end_id, b) if side == "source" else (a, end_id)
        opener = {
            "hidden": CLEARED,
            "reverted": None,
            "dataset": READER_BOTH,
            "restricted": RESTRICTED_READER,
        }[end_axis]
        if end_axis == "reverted":
            revert_end = end_id
    elif reason == "clearance":
        link["classification"], opener = "SECRET", CLEARED
    elif reason == "handling_code":
        link.update(handling_code="R", owning_unit="unit-restricted")
        opener = RESTRICTED_READER
    elif reason == "dataset":
        link["datasets"], opener = ["fixture"], READER_BOTH
    _, (edge_id,) = await _write(adapter, [], [_edge("ASSOCIATE_OF", a, b, **link)])
    if revert_end is not None:
        # Read before the end is reverted: the lookup finds the link, the revert takes it away.
        assert [e.id for e in await adapter.get_edges([edge_id], READER)] == [edge_id]
        tx = await adapter.begin_transaction()
        await adapter.revert_elements([revert_end], [], tx)
        await adapter.commit_transaction(tx)
    replacement = None
    if reason == "superseded":
        tx = await adapter.begin_transaction()
        replacement = await adapter.supersede_edge(
            edge_id,
            _edge("ASSOCIATE_OF", a, b, classification="OFFICIAL", datasets=["enron"]),
            tx,
        )
        await adapter.commit_transaction(tx)
    elif reason == "reverted":
        # Read before it is reverted: the lookup finds it, the revert is what takes it away.
        assert [e.id for e in await adapter.get_edges([edge_id], READER)] == [edge_id]
        tx = await adapter.begin_transaction()
        await adapter.revert_elements([], [edge_id], tx)
        await adapter.commit_transaction(tx)
    return _Unreadable(edge_id, opener, replacement)


async def test_get_edges_returns_readable_links_with_readable_ends_ordered_by_id(
    factory: GraphAdapterFactory,
) -> None:
    async with factory.context() as adapter:
        first = await _readable_link(adapter)
        second = await _readable_link(adapter)
        edges = await adapter.get_edges([second, first], READER)
        assert [e.id for e in edges] == sorted([first, second])
        for edge in edges:
            assert edge.type == "ASSOCIATE_OF"
            assert edge.datasets == ["enron"]
            assert edge.source != edge.target


@pytest.mark.parametrize("reason", _EDGE_REASONS)
async def test_get_edges_leaves_out_an_unreadable_id_whatever_the_reason(
    factory: GraphAdapterFactory, reason: str
) -> None:
    async with factory.context() as adapter:
        readable = await _readable_link(adapter)
        unreadable = await _unreadable_edge(adapter, reason)

        assert [e.id for e in await adapter.get_edges([unreadable.id, readable], READER)] == [
            readable
        ]
        # The one id on its own gives the empty list, not an error and not a marker.
        assert await adapter.get_edges([unreadable.id], READER) == []
        # What the reason hides is real: a principal who differs only on that axis reads it.
        if unreadable.opener is not None:
            opened = await adapter.get_edges([unreadable.id], unreadable.opener)
            assert [e.id for e in opened] == [unreadable.id]
        if unreadable.replacement is not None:
            # The correction's replacement is a link of its own, and readable.
            replaced = await adapter.get_edges([unreadable.replacement], READER)
            assert [e.id for e in replaced] == [unreadable.replacement]


async def test_get_edges_of_a_mixed_list_is_exactly_the_readable_subset(
    factory: GraphAdapterFactory,
) -> None:
    async with factory.context() as adapter:
        readable = [await _readable_link(adapter) for _ in range(2)]
        unreadable = [await _unreadable_edge(adapter, reason) for reason in _EDGE_REASONS]
        # A superseded link's replacement is a readable link of its own: only the old one goes.
        replacements = [u.replacement for u in unreadable if u.replacement is not None]
        assert len(replacements) == 1
        readable = [*readable, *replacements]
        assert await adapter.get_edges([u.id for u in unreadable], READER) == []
        edges = await adapter.get_edges([*(u.id for u in unreadable), *readable], READER)
        assert [e.id for e in edges] == sorted(readable)
        # The same as the list without the unreadable ids: nothing in the result says they exist.
        assert edges == await adapter.get_edges(readable, READER)


async def test_get_edges_of_several_link_types_in_one_call(factory: GraphAdapterFactory) -> None:
    """Links of different types in one lookup come back as the types they are. The lookup asks
    each stored link type for the ids and so filters on no type; the label each link is stored
    under is read back as its type."""
    async with factory.context() as adapter:
        (p1, p2), _ = await _write(
            adapter,
            [_node("Person", classification="OFFICIAL", datasets=["enron"]) for _ in "ab"],
            [],
        )
        (phone,), _ = await _write(
            adapter,
            [_node("Endpoint", classification="OFFICIAL", datasets=["enron"])],
            [],
        )
        wanted = {"ASSOCIATE_OF": (p1, p2), "FAMILY_OF": (p1, p2), "USES": (p1, phone)}
        _, ids = await _write(
            adapter,
            [],
            [
                _edge(t, s, d, classification="OFFICIAL", datasets=["enron"])
                for t, (s, d) in wanted.items()
            ],
        )
        edges = await adapter.get_edges(list(reversed(ids)), READER)
        assert [e.id for e in edges] == sorted(ids)
        assert {e.type for e in edges} == set(wanted)
        for edge in edges:
            assert (edge.source, edge.target) == wanted[edge.type]


async def test_get_edges_returns_a_duplicated_id_once(factory: GraphAdapterFactory) -> None:
    async with factory.context() as adapter:
        first = await _readable_link(adapter)
        second = await _readable_link(adapter)
        edges = await adapter.get_edges([second, first, second, first], READER)
        assert [e.id for e in edges] == sorted([first, second])


async def test_get_edges_of_no_ids_is_empty(factory: GraphAdapterFactory) -> None:
    async with factory.context() as adapter:
        await _readable_link(adapter)
        assert await adapter.get_edges([], READER) == []


async def test_get_edges_past_one_chunk_returns_exactly_the_readable_ones(
    factory: GraphAdapterFactory,
) -> None:
    """As the nodes' chunk case, for links: 1,050 readable links from one hub to 1,050 readable
    nodes, 50 links to a hidden node and 50 absent ids, the last chunk holding readable links."""
    async with factory.context() as adapter:
        tx = await adapter.begin_transaction()
        hub, *spokes = await adapter.upsert_nodes(
            [_node("Person", classification="OFFICIAL", datasets=["enron"]) for _ in range(1051)],
            tx,
        )
        hidden_ends = await adapter.upsert_nodes(
            [_node("Person", classification="SECRET", datasets=["enron"]) for _ in range(50)], tx
        )
        readable = await adapter.upsert_edges(
            [
                _edge("ASSOCIATE_OF", hub, spoke, classification="OFFICIAL", datasets=["enron"])
                for spoke in spokes
            ],
            tx,
        )
        hidden = await adapter.upsert_edges(
            [
                _edge("ASSOCIATE_OF", hub, end, classification="OFFICIAL", datasets=["enron"])
                for end in hidden_ends
            ],
            tx,
        )
        await adapter.commit_transaction(tx)
        absent = [new_edge_id() for _ in range(50)]

        asked: list[str] = []
        for i, edge_id in enumerate(readable):
            asked.append(edge_id)
            if i % 21 == 0 and absent:
                asked.append(absent.pop())
            if i % 21 == 10 and hidden:
                asked.append(hidden.pop())
        assert len(asked) > 1000
        assert asked[-1] in readable

        edges = await adapter.get_edges(asked, READER)
        assert [e.id for e in edges] == sorted(readable)


async def test_get_nodes_of_several_node_types_in_one_call(factory: GraphAdapterFactory) -> None:
    """Nodes of different types in one lookup come back as the types they are. The lookup asks
    each stored vertex type for the ids and so filters on no type; the type each node is stored
    under is read back."""
    types = ["Person", "Endpoint", "Location", "Alert"]
    async with factory.context() as adapter:
        ids, _ = await _write(
            adapter,
            [_node(t, classification="OFFICIAL", datasets=["enron"]) for t in types],
            [],
        )
        wanted = dict(zip(ids, types, strict=True))
        nodes = await adapter.get_nodes(list(reversed(ids)), READER)
        assert [n.id for n in nodes] == sorted(ids)
        assert {n.id: n.type for n in nodes} == wanted


async def _many_readable_nodes(adapter: GraphPort, count: int) -> list[str]:
    tx = await adapter.begin_transaction()
    ids = await adapter.upsert_nodes(
        [_node("Person", classification="OFFICIAL", datasets=["enron"]) for _ in range(count)], tx
    )
    await adapter.commit_transaction(tx)
    return ids


async def _many_readable_edges(adapter: GraphPort, count: int) -> list[str]:
    """`count` links from one hub to as many readable nodes."""
    tx = await adapter.begin_transaction()
    hub, *spokes = await adapter.upsert_nodes(
        [_node("Person", classification="OFFICIAL", datasets=["enron"]) for _ in range(count + 1)],
        tx,
    )
    ids = await adapter.upsert_edges(
        [
            _edge("ASSOCIATE_OF", hub, spoke, classification="OFFICIAL", datasets=["enron"])
            for spoke in spokes
        ],
        tx,
    )
    await adapter.commit_transaction(tx)
    return ids


async def test_get_nodes_asked_in_descending_order_across_a_chunk_comes_back_ascending(
    factory: GraphAdapterFactory,
) -> None:
    async with factory.context() as adapter:
        ids = await _many_readable_nodes(adapter, 1100)
        nodes = await adapter.get_nodes(sorted(ids, reverse=True), READER)
        assert [n.id for n in nodes] == sorted(ids)


async def test_get_edges_asked_in_descending_order_across_a_chunk_comes_back_ascending(
    factory: GraphAdapterFactory,
) -> None:
    async with factory.context() as adapter:
        ids = await _many_readable_edges(adapter, 1100)
        edges = await adapter.get_edges(sorted(ids, reverse=True), READER)
        assert [e.id for e in edges] == sorted(ids)


async def test_get_nodes_asked_for_an_id_in_the_first_and_the_last_chunk_returns_it_once(
    factory: GraphAdapterFactory,
) -> None:
    async with factory.context() as adapter:
        ids = await _many_readable_nodes(adapter, 1100)
        asked = [ids[0], *ids[1:], ids[0]]  # 1,101 asked: the same id leads and trails
        nodes = await adapter.get_nodes(asked, READER)
        assert [n.id for n in nodes] == sorted(ids)


async def test_get_edges_asked_for_an_id_in_the_first_and_the_last_chunk_returns_it_once(
    factory: GraphAdapterFactory,
) -> None:
    async with factory.context() as adapter:
        ids = await _many_readable_edges(adapter, 1100)
        asked = [ids[0], *ids[1:], ids[0]]
        edges = await adapter.get_edges(asked, READER)
        assert [e.id for e in edges] == sorted(ids)


@pytest.mark.parametrize("awkward", ["a\nb", "c\rd"])
async def test_a_line_break_in_a_property_and_in_a_dataset_name_round_trips_through_get_nodes(
    factory: GraphAdapterFactory, awkward: str
) -> None:
    """A line feed or carriage return in a stored value comes back equal, and a dataset name with
    one reads: the name is in the query's literal (`within(['a\\nb'])`), which a raw line break
    would make a compile error."""
    reader = Principal(id="reader", clearance="OFFICIAL", org_unit="unit-1", datasets=[awkward])
    async with factory.context() as adapter:
        (node_id,), _ = await _write(
            adapter,
            [_node("Person", classification="OFFICIAL", datasets=[awkward], family_name=awkward)],
            [],
        )
        (node,) = await adapter.get_nodes([node_id], reader)
        assert node.id == node_id
        assert node.properties["family_name"] == awkward
        assert node.datasets == [awkward]
        # The same name is a different dataset from one without the line break.
        plain = awkward.replace("\n", "").replace("\r", "")
        elsewhere = reader.model_copy(update={"datasets": [plain]})
        assert await adapter.get_nodes([node_id], elsewhere) == []


# --- ADR-099: a case sees only its own datasets ------------------------------
#
# The third axis, built like the other two: in the traversal, never after it. Each case below is
# the dataset twin of a handling one above (get_node, degree, path length, match, its count,
# edges_among), plus what only datasets have: an element in two datasets, the union on a second
# write, search and suggestions, and an expansion, which must not reach another dataset's
# neighbours (what lies outside a case's datasets is not in its world).


async def test_a_node_of_another_dataset_matches_a_graph_where_it_never_existed(
    factory: GraphAdapterFactory,
) -> None:
    async with factory.context() as adapter:
        (enron,), _ = await _write(
            adapter, [_node("Person", classification="OFFICIAL", datasets=["enron"])], []
        )
        assert await adapter.get_node(enron, IN_FIXTURE) is None
        assert await adapter.get_node("not-a-real-id-at-all", IN_FIXTURE) is None
        found = await adapter.get_node(enron, IN_ENRON)
        assert found is not None and found.datasets == ["enron"]  # the filter is real
        # Unlimited background work (resolution, a load lookup) sees it; a case over none does not.
        assert await adapter.get_node(enron, CLEARED) is not None
        assert await adapter.get_node(enron, IN_NOTHING) is None


async def test_a_node_written_by_two_datasets_belongs_to_both_and_a_rewrite_never_drops_one(
    factory: GraphAdapterFactory,
) -> None:
    async with factory.context() as adapter:
        first = _node("Person", classification="OFFICIAL", datasets=["enron"])
        await _write(adapter, [first], [])
        await _write(adapter, [first.model_copy(update={"datasets": ["fixture"]})], [])
        await _write(adapter, [first.model_copy(update={"datasets": ["enron"]})], [])
        node = await adapter.get_node(first.id, IN_FIXTURE)
        assert node is not None and sorted(node.datasets) == ["enron", "fixture"]
        assert await adapter.get_node(first.id, IN_ENRON) is not None


async def test_a_link_written_by_two_datasets_belongs_to_both(factory: GraphAdapterFactory) -> None:
    async with factory.context() as adapter:
        (a, b), _ = await _write(
            adapter,
            [
                _node("Person", classification="OFFICIAL", datasets=["enron", "fixture"])
                for _ in "ab"
            ],
            [],
        )
        link = _edge("ASSOCIATE_OF", a, b, classification="OFFICIAL", datasets=["enron"])
        await _write(adapter, [], [link])
        assert await adapter.edges_among([a, b], IN_FIXTURE) == []
        await _write(adapter, [], [link.model_copy(update={"datasets": ["fixture"]})])
        (seen,) = await adapter.edges_among([a, b], IN_FIXTURE)
        assert sorted(seen.datasets) == ["enron", "fixture"]


async def test_degree_in_one_dataset_matches_a_graph_without_the_other_datasets_neighbour(
    factory: GraphAdapterFactory,
) -> None:
    async with factory.context() as adapter:
        both = ["enron", "fixture"]
        (hub,), _ = await _write(
            adapter, [_node("Person", classification="OFFICIAL", datasets=both)], []
        )
        (visible,), _ = await _write(
            adapter, [_node("Endpoint", classification="OFFICIAL", datasets=["fixture"])], []
        )
        await _write(
            adapter,
            [],
            [_edge("USES", hub, visible, classification="OFFICIAL", datasets=["fixture"])],
        )
        before = await adapter.neighbourhood_stats(hub, IN_FIXTURE)

        (elsewhere,), _ = await _write(
            adapter, [_node("Endpoint", classification="OFFICIAL", datasets=["enron"])], []
        )
        (shared,), _ = await _write(
            adapter, [_node("Endpoint", classification="OFFICIAL", datasets=both)], []
        )
        await _write(
            adapter,
            [],
            [
                _edge("USES", hub, elsewhere, classification="OFFICIAL", datasets=["enron"]),
                # A link of the other dataset to a node this case sees is not in its world either.
                _edge("USES", hub, shared, classification="OFFICIAL", datasets=["enron"]),
            ],
        )
        assert await adapter.neighbourhood_stats(hub, IN_FIXTURE) == before
        assert (await adapter.neighbourhood_stats(hub, IN_ENRON)).degree == 2


async def test_path_length_in_one_dataset_matches_a_graph_without_the_other_datasets_hop(
    factory: GraphAdapterFactory,
) -> None:
    async with factory.context() as adapter:
        both = ["enron", "fixture"]
        (a, b, target), _ = await _write(
            adapter, [_node("Person", classification="OFFICIAL", datasets=both) for _ in "abc"], []
        )
        await _write(
            adapter,
            [],
            [
                _edge("ASSOCIATE_OF", a, b, classification="OFFICIAL", datasets=["fixture"]),
                _edge("ASSOCIATE_OF", b, target, classification="OFFICIAL", datasets=["fixture"]),
                _edge("ASSOCIATE_OF", a, target, classification="OFFICIAL", datasets=["enron"]),
            ],
        )
        req = PathRequest(source=a, target=target, max_hops=6, k=5)
        assert {p.length for p in await adapter.paths(req, IN_FIXTURE)} == {2}
        assert {p.length for p in await adapter.paths(req, IN_ENRON)} == {1}


async def test_expansion_stays_within_the_cases_datasets(
    factory: GraphAdapterFactory,
) -> None:
    async with factory.context() as adapter:
        (hub,), _ = await _write(
            adapter,
            [_node("Person", classification="OFFICIAL", datasets=["enron", "fixture"])],
            [],
        )
        (mine, theirs), _ = await _write(
            adapter,
            [
                _node("Endpoint", classification="OFFICIAL", datasets=["fixture"]),
                _node("Endpoint", classification="OFFICIAL", datasets=["enron"]),
            ],
            [],
        )
        await _write(
            adapter,
            [],
            [
                _edge("USES", hub, mine, classification="OFFICIAL", datasets=["fixture"]),
                _edge("USES", hub, theirs, classification="OFFICIAL", datasets=["enron"]),
            ],
        )
        req = ExpandRequest(node_ids=[hub], depth=1)
        expanded = await adapter.expand(req, IN_FIXTURE)
        assert {n.id for n in expanded.nodes} == {hub, mine}
        assert len(expanded.edges) == 1


async def test_match_and_its_count_never_reach_another_dataset(
    factory: GraphAdapterFactory,
) -> None:
    async with factory.context() as adapter:
        (person, theirs), _ = await _write(
            adapter,
            [
                _node("Person", classification="OFFICIAL", datasets=["enron", "fixture"]),
                _node("Endpoint", classification="OFFICIAL", datasets=["enron"]),
            ],
            [],
        )
        await _write(
            adapter,
            [],
            [_edge("USES", person, theirs, classification="OFFICIAL", datasets=["enron"])],
        )
        pattern = PatternQuery(
            nodes=[
                PatternNode(var="p", entity_type="Person"),
                PatternNode(var="e", entity_type="Endpoint"),
            ],
            edges=[PatternEdge(edge_type="USES", from_var="p", to_var="e")],
        )
        assert (await adapter.match(pattern, IN_FIXTURE)).nodes == []
        assert await adapter.match_count(pattern, IN_FIXTURE, ceiling=100) == 0
        matched = await adapter.match(pattern, IN_ENRON)
        assert {n.id for n in matched.nodes} == {person, theirs}
        # The count is the matched subgraph's nodes, as
        # `test_match_count_agrees_with_the_filtered_results_own_count` has it.
        assert await adapter.match_count(pattern, IN_ENRON, ceiling=100) == 2


async def test_search_suggestions_and_lookups_find_only_the_cases_datasets(
    factory: GraphAdapterFactory,
) -> None:
    """The owner's report: `vol` in Fixture Corp suggested an Enron address."""
    async with factory.context() as adapter:
        address = "volume.management@enron.com"
        (theirs,), _ = await _write(
            adapter,
            [
                _node(
                    "Endpoint",
                    classification="OFFICIAL",
                    datasets=["enron"],
                    value_normalised=address,
                )
            ],
            [],
        )
        assert await adapter.search_nodes(address, IN_FIXTURE) == []
        assert [n.id for n in await adapter.search_nodes(address, IN_ENRON)] == [theirs]
        assert (await adapter.suggest_nodes("volume", IN_FIXTURE)).nodes == []
        assert [n.id for n in (await adapter.suggest_nodes("volume", IN_ENRON)).nodes] == [theirs]
        assert await adapter.find_node("Endpoint", "value_normalised", address, IN_FIXTURE) is None
        assert (await adapter.list_nodes("Endpoint", IN_FIXTURE)).nodes == []
        assert [n.id for n in (await adapter.list_nodes("Endpoint", IN_ENRON)).nodes] == [theirs]



async def test_a_correction_keeps_the_nodes_datasets_and_its_links_stay_in_theirs(
    factory: GraphAdapterFactory,
) -> None:
    """A confirmed or corrected node is a new revision, and its links are cloned onto it
    (`supersede_node`). Neither may lose its datasets: the case that confirmed it would lose the
    node and its links as it confirmed them. The replacement is written as a caller builds it,
    naming no dataset, which is what a confirm does."""
    async with factory.context() as adapter:
        (old, neighbour), _ = await _write(
            adapter,
            [
                _node("Person", classification="OFFICIAL", datasets=["fixture"]),
                _node("Endpoint", classification="OFFICIAL", datasets=["fixture"]),
            ],
            [],
        )
        await _write(
            adapter,
            [],
            [_edge("USES", old, neighbour, classification="OFFICIAL", datasets=["fixture"])],
        )
        tx = await adapter.begin_transaction()
        new = await adapter.supersede_node(old, _node("Person", classification="OFFICIAL"), tx)
        await adapter.commit_transaction(tx)

        corrected = await adapter.get_node(new, IN_FIXTURE)
        assert corrected is not None and corrected.datasets == ["fixture"]
        expanded = await adapter.expand(ExpandRequest(node_ids=[new], depth=1), IN_FIXTURE)
        assert {n.id for n in expanded.nodes} == {new, neighbour}
        (link,) = expanded.edges
        assert link.datasets == ["fixture"]


async def test_a_changed_link_keeps_its_datasets(factory: GraphAdapterFactory) -> None:
    """A link changed by an analyst (ADR-080) is a new revision written as the caller builds it,
    naming no dataset; it stays in the case's world."""
    async with factory.context() as adapter:
        (a, b), _ = await _write(
            adapter,
            [_node("Person", classification="OFFICIAL", datasets=["fixture"]) for _ in "ab"],
            [],
        )
        _, (link,) = await _write(
            adapter,
            [],
            [_edge("ASSOCIATE_OF", a, b, classification="OFFICIAL", datasets=["fixture"])],
        )
        tx = await adapter.begin_transaction()
        changed = await adapter.supersede_edge(
            link, _edge("FAMILY_OF", a, b, classification="OFFICIAL"), tx
        )
        await adapter.commit_transaction(tx)
        (seen,) = await adapter.edges_among([a, b], IN_FIXTURE)
        assert seen.id == changed and seen.datasets == ["fixture"]


# --- A value changed in place leaves every other record findable ---------------
#
# ArcadeDB 25.5.1 lost every other record from a NOTUNIQUE index key when one record's value under
# that key changed (measured in plain SQL: three records share a key, one changes, a lookup finds 0
# of the other 2). Every write that changes an indexed value in place is a trigger: a revert, a
# correction (the old revision's `superseded_by`), a re-write with new handling. Each case below
# changes one of three and reads the type back by a read whose entry point is that type.


async def _three_people(adapter: GraphPort) -> list[NodeWrite]:
    people = [_node("Person", classification="OFFICIAL") for _ in range(3)]
    await _write(adapter, people, [])
    return people


async def _listed(adapter: GraphPort) -> set[str]:
    page = await adapter.list_nodes("Person", CLEARED, limit=100)
    return {n.id for n in page.nodes}


async def test_reverting_one_node_leaves_the_others_of_its_type_listed(
    factory: GraphAdapterFactory,
) -> None:
    async with factory.context() as adapter:
        people = await _three_people(adapter)
        tx = await adapter.begin_transaction()
        await adapter.revert_elements([people[0].id], [], tx)
        await adapter.commit_transaction(tx)
        assert await _listed(adapter) == {people[1].id, people[2].id}


async def test_correcting_one_node_leaves_the_others_of_its_type_listed(
    factory: GraphAdapterFactory,
) -> None:
    async with factory.context() as adapter:
        people = await _three_people(adapter)
        replacement = _node("Person", classification="OFFICIAL")
        tx = await adapter.begin_transaction()
        await adapter.supersede_node(people[0].id, replacement, tx)
        await adapter.commit_transaction(tx)
        assert await _listed(adapter) == {people[1].id, people[2].id, replacement.id}


async def test_rewriting_one_node_with_new_handling_leaves_the_others_listed(
    factory: GraphAdapterFactory,
) -> None:
    async with factory.context() as adapter:
        people = await _three_people(adapter)
        handling = people[0].handling.model_copy(update={"handling_code": "C"})
        changed = people[0].model_copy(update={"handling": handling})
        await _write(adapter, [changed], [])
        assert await _listed(adapter) == {p.id for p in people}


# --- ADR-100: what the Explore panel reads ----------------------------------
#
# Counts and rankings an analyst starts from. Each is checked twice: right on its own, and equal to
# itself once hidden and other-dataset nodes and links are added beside it (rule 3: a ranking or a
# degree that moved because of them would disclose them).

#: OFFICIAL, so the SECRET contacts below are hidden from it by clearance, not only by dataset.
EXPLORER = Principal(id="analyst-explore", clearance="OFFICIAL", org_unit="unit-1",
                     datasets=["fixture"])
EXPLORER_ENRON = EXPLORER.model_copy(update={"datasets": ["enron"]})


async def _explore_world(adapter: GraphPort) -> dict[str, str]:
    """A hub with three visible contacts, a second with two, and a lone Endpoint, all in fixture."""
    fixture = ["fixture"]
    nodes = {
        name: _node(node_type, classification="OFFICIAL", datasets=fixture)
        for name, node_type in [
            ("hub", "Person"),
            ("second", "Person"),
            ("c1", "Person"),
            ("c2", "Person"),
            ("c3", "Person"),
            ("phone", "Endpoint"),
        ]
    }
    await _write(adapter, list(nodes.values()), [])
    links = [
        _edge("ASSOCIATE_OF", nodes["hub"].id, nodes[c].id, classification="OFFICIAL",
              datasets=fixture)
        for c in ("c1", "c2", "c3")
    ] + [
        _edge("ASSOCIATE_OF", nodes["second"].id, nodes[c].id, classification="OFFICIAL",
              datasets=fixture)
        for c in ("c1", "c2")
    ]
    await _write(adapter, [], links)
    return {name: node.id for name, node in nodes.items()}


async def _add_what_must_not_count(adapter: GraphPort, ids: dict[str, str]) -> None:
    """Around `second`: SECRET contacts, contacts in another dataset, a link of another dataset to
    a node the case sees, and a reverted contact. Enough of them to lift `second` above `hub` if
    any were counted."""
    secret = [_node("Person", classification="SECRET", datasets=["fixture"]) for _ in range(3)]
    elsewhere = [_node("Person", classification="OFFICIAL", datasets=["enron"]) for _ in range(3)]
    reverted = _node("Person", classification="OFFICIAL", datasets=["fixture"])
    await _write(adapter, [*secret, *elsewhere, reverted], [])
    await _write(
        adapter,
        [],
        [
            *(
                _edge("ASSOCIATE_OF", ids["second"], n.id, classification="OFFICIAL",
                      datasets=["fixture"])
                for n in secret
            ),
            *(
                _edge("ASSOCIATE_OF", ids["second"], n.id, classification="OFFICIAL",
                      datasets=["enron"])
                for n in elsewhere
            ),
            _edge("ASSOCIATE_OF", ids["second"], ids["c3"], classification="OFFICIAL",
                  datasets=["enron"]),
            _edge("USES", ids["second"], ids["phone"], classification="SECRET",
                  datasets=["fixture"]),
            _edge("ASSOCIATE_OF", ids["second"], reverted.id, classification="OFFICIAL",
                  datasets=["fixture"]),
        ],
    )
    tx = await adapter.begin_transaction()
    await adapter.revert_elements([reverted.id], [], tx)
    await adapter.commit_transaction(tx)


async def test_type_counts_are_of_what_the_case_can_see(factory: GraphAdapterFactory) -> None:
    async with factory.context() as adapter:
        ids = await _explore_world(adapter)
        before = await adapter.type_counts(EXPLORER)
        assert before.nodes == {"Person": 5, "Endpoint": 1}
        assert before.edges == {"ASSOCIATE_OF": 5}
        await _add_what_must_not_count(adapter, ids)
        assert await adapter.type_counts(EXPLORER) == before
        # The filter is real: the other dataset's case counts its own.
        assert (await adapter.type_counts(EXPLORER_ENRON)).nodes == {"Person": 3}
        assert await adapter.type_counts(IN_NOTHING) == type(before)()


async def test_most_connected_ranks_by_visible_links_and_says_of_how_many(
    factory: GraphAdapterFactory,
) -> None:
    async with factory.context() as adapter:
        ids = await _explore_world(adapter)
        first = await adapter.most_connected(EXPLORER, limit=2)
        assert [(r.node.id, r.degree) for r in first.nodes] == [(ids["hub"], 3), (ids["second"], 2)]
        assert first.total == 6 and first.offset == 0
        await _add_what_must_not_count(adapter, ids)
        again = await adapter.most_connected(EXPLORER, limit=2)
        assert [(r.node.id, r.degree) for r in again.nodes] == [(ids["hub"], 3), (ids["second"], 2)]
        assert again.total == 6


async def test_most_connected_pages_without_gaps_or_repeats(factory: GraphAdapterFactory) -> None:
    async with factory.context() as adapter:
        ids = await _explore_world(adapter)
        pages = [await adapter.most_connected(EXPLORER, limit=2, offset=o) for o in (0, 2, 4, 6)]
        seen = [r.node.id for p in pages for r in p.nodes]
        assert sorted(seen) == sorted(ids.values())
        assert [len(p.nodes) for p in pages] == [2, 2, 2, 0]
        degrees = [r.degree for p in pages for r in p.nodes]
        assert degrees == sorted(degrees, reverse=True)
        # Ties are in id order, so a page boundary is stable.
        tied = [r.node.id for p in pages for r in p.nodes if r.degree == 2]
        assert tied == sorted(tied)


async def test_most_connected_of_one_type_counts_only_that_type(
    factory: GraphAdapterFactory,
) -> None:
    async with factory.context() as adapter:
        ids = await _explore_world(adapter)
        await _add_what_must_not_count(adapter, ids)
        people = await adapter.most_connected(EXPLORER, entity_type="Person", limit=10)
        assert people.total == 5 and len(people.nodes) == 5
        assert {r.node.type for r in people.nodes} == {"Person"}
        phones = await adapter.most_connected(EXPLORER, entity_type="Endpoint", limit=10)
        assert [(r.node.id, r.degree) for r in phones.nodes] == [(ids["phone"], 0)]
        assert phones.total == 1


async def _busy_world(adapter: GraphPort) -> dict[str, str]:
    """Four people in fixture, linked by three links of 9, 4 and 4 records, and one person apart."""
    fixture = ["fixture"]
    people = {n: _node("Person", classification="OFFICIAL", datasets=fixture) for n in "abcde"}
    await _write(adapter, list(people.values()), [])
    links = {
        "ab": _edge("ASSOCIATE_OF", people["a"].id, people["b"].id, classification="OFFICIAL",
                    occurrences=9, datasets=fixture),
        "bc": _edge("ASSOCIATE_OF", people["b"].id, people["c"].id, classification="OFFICIAL",
                    occurrences=4, datasets=fixture),
        "cd": _edge("ASSOCIATE_OF", people["c"].id, people["d"].id, classification="OFFICIAL",
                    occurrences=4, datasets=fixture),
    }
    await _write(adapter, [], list(links.values()))
    return {**{n: p.id for n, p in people.items()}, **{n: e.id for n, e in links.items()}}


async def _add_busy_links_that_must_not_count(adapter: GraphPort, ids: dict[str, str]) -> None:
    """Busier than any above: a SECRET link, a link of another dataset, a link to a SECRET person,
    and a reverted link. Ranked, any of them would come first."""
    secret_person = _node("Person", classification="SECRET", datasets=["fixture"])
    await _write(adapter, [secret_person], [])
    reverted = _edge("ASSOCIATE_OF", ids["d"], ids["e"], classification="OFFICIAL", occurrences=99,
                     datasets=["fixture"])
    await _write(adapter, [], [
        _edge("ASSOCIATE_OF", ids["a"], ids["e"], classification="SECRET", occurrences=50,
              datasets=["fixture"]),
        _edge("ASSOCIATE_OF", ids["b"], ids["e"], classification="OFFICIAL", occurrences=50,
              datasets=["enron"]),
        _edge("ASSOCIATE_OF", ids["c"], secret_person.id, classification="OFFICIAL", occurrences=50,
              datasets=["fixture"]),
        reverted,
    ])
    tx = await adapter.begin_transaction()
    await adapter.revert_elements([], [reverted.id], tx)
    await adapter.commit_transaction(tx)


async def test_busiest_links_rank_by_records_and_say_of_how_many(factory: GraphAdapterFactory) -> None:
    async with factory.context() as adapter:
        ids = await _busy_world(adapter)
        first = await adapter.busiest_links(EXPLORER, limit=2)
        tied = sorted([ids["bc"], ids["cd"]])
        assert [r.edge.id for r in first.links] == [ids["ab"], tied[0]]
        assert [r.edge.occurrences for r in first.links] == [9, 4]
        assert first.total == 3 and first.offset == 0
        # Each comes with both its ends, so the panel can name the pair.
        top = first.links[0]
        assert {top.source.id, top.target.id} == {ids["a"], ids["b"]}
        await _add_busy_links_that_must_not_count(adapter, ids)
        again = await adapter.busiest_links(EXPLORER, limit=10)
        assert [r.edge.id for r in again.links] == [ids["ab"], *tied]
        assert again.total == 3


async def test_busiest_links_of_one_node_rank_only_its_own_visible_links(
    factory: GraphAdapterFactory,
) -> None:
    """ADR-100 Amendment 9 (the owner, 9 October 2026): a dense node is brought to the canvas with
    its N busiest links, not all or nothing — so the ranking takes `node_id`. Access control is the
    same as the whole-case ranking's: after `_add_busy_links_that_must_not_count`, node `b` carries
    an other-dataset link busier (50) than anything it may show; ranked, it would come first."""
    async with factory.context() as adapter:
        ids = await _busy_world(adapter)
        mine = await adapter.busiest_links(EXPLORER, node_id=ids["b"])
        assert [r.edge.id for r in mine.links] == [ids["ab"], ids["bc"]]
        assert mine.total == 2
        first = await adapter.busiest_links(EXPLORER, node_id=ids["b"], limit=1)
        assert [r.edge.id for r in first.links] == [ids["ab"]] and first.total == 2
        await _add_busy_links_that_must_not_count(adapter, ids)
        again = await adapter.busiest_links(EXPLORER, node_id=ids["b"], limit=10)
        assert [r.edge.id for r in again.links] == [ids["ab"], ids["bc"]]
        assert again.total == 2


async def test_busiest_links_page_and_filter_by_type(factory: GraphAdapterFactory) -> None:
    async with factory.context() as adapter:
        ids = await _busy_world(adapter)
        pages = [await adapter.busiest_links(EXPLORER, limit=2, offset=o) for o in (0, 2, 4)]
        assert [len(p.links) for p in pages] == [2, 1, 0]
        assert {r.edge.id for p in pages for r in p.links} == {ids["ab"], ids["bc"], ids["cd"]}
        none = await adapter.busiest_links(EXPLORER, edge_type="FAMILY_OF")
        assert none.links == [] and none.total == 0
        some = await adapter.busiest_links(EXPLORER, edge_type="ASSOCIATE_OF")
        assert some.total == 3


async def test_the_link_structure_is_what_the_case_can_see(factory: GraphAdapterFactory) -> None:
    """ADR-100 Amendment 5: the case's groups are found from its structure; a hidden, other-dataset
    or reverted node or link in it would put something the reader cannot see into a group."""
    async with factory.context() as adapter:
        ids = await _explore_world(adapter)
        before = await adapter.link_structure(EXPLORER, max_nodes=100, max_edges=100)
        await _add_what_must_not_count(adapter, ids)
        after = await adapter.link_structure(EXPLORER, max_nodes=100, max_edges=100)
        for structure in (before, after):
            assert {n.id for n in structure.nodes} == set(ids.values())
            assert {n.type for n in structure.nodes} == {"Person", "Endpoint"}
            assert len(structure.edges) == 5
            ends = {(e.source, e.target) for e in structure.edges}
            assert ends <= {(a, b) for a in ids.values() for b in ids.values()}


async def test_a_link_structure_past_its_caps_is_refused_with_only_what_is_seen_counted(
    factory: GraphAdapterFactory,
) -> None:
    async with factory.context() as adapter:
        ids = await _explore_world(adapter)
        await _add_what_must_not_count(adapter, ids)
        with pytest.raises(SubgraphTooLarge) as nodes:
            await adapter.link_structure(EXPLORER, max_nodes=5, max_edges=100)
        assert nodes.value.nodes == 6  # never the SECRET, other-dataset or reverted ones
        with pytest.raises(SubgraphTooLarge) as edges:
            await adapter.link_structure(EXPLORER, max_nodes=100, max_edges=4)
        assert edges.value.edges == 5


# --- ADR-100 decision 7 (Amendment 6): what is new ---------------------------

_T0 = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)


def _at(write: NodeWrite | EdgeWrite, hours: int) -> NodeWrite | EdgeWrite:
    return write.model_copy(update={"created_at": _T0 + timedelta(hours=hours)})


def _confirmed(write: NodeWrite, hours: int, by: str = "colleague-1") -> NodeWrite:
    provenance = write.provenance.model_copy(
        update={"last_confirmed": _T0 + timedelta(hours=hours), "confirmed_by": by}
    )
    return write.model_copy(update={"provenance": provenance})


async def _loads_world(adapter: GraphPort) -> dict[str, str]:
    """Load `old` (two people and their link, at 1h and 2h), load `new` (one person, at 5h) and a
    person no load wrote (at 3h), all in fixture."""
    fixture = ["fixture"]

    def person(load: str | None, hours: int) -> NodeWrite:
        return _at(_node("Person", classification="OFFICIAL", datasets=fixture, load_id=load,
                         recipe_id="recipe-a" if load else None,
                         recipe_version=2 if load else None), hours)

    nodes = {"a": person("old", 1), "b": person("old", 2), "c": person("new", 5),
             "d": person(None, 3)}
    await _write(adapter, list(nodes.values()), [])
    link = _at(_edge("ASSOCIATE_OF", nodes["a"].id, nodes["b"].id, classification="OFFICIAL",
                     datasets=fixture, load_id="old"), 2)
    await _write(adapter, [], [link])
    return {name: n.id for name, n in nodes.items()}


async def _add_loads_that_must_not_count(adapter: GraphPort, ids: dict[str, str]) -> None:
    """Later than everything above: a SECRET node in `old` and in a load of its own, an
    other-dataset node in `new`, a reverted node in `old`, and links in `old` to the hidden ones.
    Any of them counted would change a count, a `latest` or the order."""
    secret_old = _at(_node("Person", classification="SECRET", datasets=["fixture"],
                           load_id="old"), 9)
    secret_own = _at(_node("Person", classification="SECRET", datasets=["fixture"],
                           load_id="hidden"), 9)
    elsewhere = _at(_node("Person", classification="OFFICIAL", datasets=["enron"],
                          load_id="new"), 9)
    reverted = _at(_node("Person", classification="OFFICIAL", datasets=["fixture"],
                         load_id="old"), 9)
    await _write(adapter, [secret_old, secret_own, elsewhere, reverted], [])
    await _write(adapter, [], [
        _at(_edge("ASSOCIATE_OF", ids["a"], secret_old.id, classification="OFFICIAL",
                  datasets=["fixture"], load_id="old"), 9),
        _at(_edge("ASSOCIATE_OF", ids["a"], ids["c"], classification="SECRET",
                  datasets=["fixture"], load_id="new"), 9),
        # A pair of its own: a link written again for the same pair takes the latest write's
        # handling and adds its dataset (`schemas.merge`), which is a different case.
        _at(_edge("ASSOCIATE_OF", ids["b"], ids["c"], classification="OFFICIAL",
                  datasets=["enron"], load_id="new"), 9),
    ])
    tx = await adapter.begin_transaction()
    await adapter.revert_elements([reverted.id], [], tx)
    await adapter.commit_transaction(tx)


async def test_recent_loads_are_the_latest_first_and_only_what_the_case_can_see(
    factory: GraphAdapterFactory,
) -> None:
    async with factory.context() as adapter:
        ids = await _loads_world(adapter)
        before = await adapter.recent_loads(EXPLORER)
        assert [load.load_id for load in before.loads] == ["new", None, "old"]
        assert before.total == 3
        new, outside, old = before.loads
        assert (new.nodes, new.links, new.latest) == (1, 0, _T0 + timedelta(hours=5))
        assert (outside.nodes, outside.links, outside.recipe_id) == (1, 0, None)
        assert (old.nodes, old.links, old.latest) == (2, 1, _T0 + timedelta(hours=2))
        assert (old.recipe_id, old.recipe_version) == ("recipe-a", 2)
        await _add_loads_that_must_not_count(adapter, ids)
        assert await adapter.recent_loads(EXPLORER) == before
        # The filter is real: the other dataset's case sees its own part of `new`.
        enron = await adapter.recent_loads(EXPLORER_ENRON)
        assert [(load.load_id, load.nodes) for load in enron.loads] == [("new", 1)]
        assert await adapter.recent_loads(IN_NOTHING) == type(before)(loads=[], total=0)


async def test_recent_loads_say_how_many_beyond_the_ones_shown(
    factory: GraphAdapterFactory,
) -> None:
    async with factory.context() as adapter:
        await _loads_world(adapter)
        first = await adapter.recent_loads(EXPLORER, limit=2)
        assert [load.load_id for load in first.loads] == ["new", None]
        assert first.total == 3


async def test_recently_confirmed_is_the_latest_first_and_only_what_the_case_can_see(
    factory: GraphAdapterFactory,
) -> None:
    async with factory.context() as adapter:
        fixture = ["fixture"]
        early = _confirmed(_node("Person", classification="OFFICIAL", datasets=fixture), 1)
        late = _confirmed(_node("Person", classification="OFFICIAL", datasets=fixture), 4,
                          by="colleague-2")
        plain = _node("Person", classification="OFFICIAL", datasets=fixture)
        await _write(adapter, [early, late, plain], [])
        before = await adapter.recently_confirmed(EXPLORER)
        assert [c.node.id for c in before.nodes] == [late.id, early.id]
        assert [c.confirmed_by for c in before.nodes] == ["colleague-2", "colleague-1"]
        assert before.nodes[0].confirmed_at == _T0 + timedelta(hours=4)
        assert before.total == 2

        # Later confirmations it must not see: SECRET, another dataset, reverted.
        hidden = [
            _confirmed(_node("Person", classification="SECRET", datasets=fixture), 9),
            _confirmed(_node("Person", classification="OFFICIAL", datasets=["enron"]), 9),
        ]
        reverted = _confirmed(_node("Person", classification="OFFICIAL", datasets=fixture), 9)
        await _write(adapter, [*hidden, reverted], [])
        tx = await adapter.begin_transaction()
        await adapter.revert_elements([reverted.id], [], tx)
        await adapter.commit_transaction(tx)
        assert await adapter.recently_confirmed(EXPLORER) == before

        # A confirmed node corrected since: only its current revision is listed.
        tx = await adapter.begin_transaction()
        replacement = _confirmed(_node("Person", classification="OFFICIAL", datasets=fixture), 6)
        current = await adapter.supersede_node(late.id, replacement, tx)
        await adapter.commit_transaction(tx)
        after = await adapter.recently_confirmed(EXPLORER, limit=1)
        assert [c.node.id for c in after.nodes] == [current]
        assert after.total == 2
        assert (await adapter.recently_confirmed(IN_NOTHING)).total == 0


# --- ADR-100 Amendment 7 decision 4: who shares contacts with one node ---------


async def test_shared_contacts_are_counted_most_first_and_only_what_the_reader_sees(
    factory: GraphAdapterFactory,
) -> None:
    async with factory.context() as adapter:
        ids = await _shared_world(adapter)  # a and b share x and y; c shares x alone
        name = {v: k for k, v in ids.items()}
        found = await adapter.shared_contacts(ids["a"], CLEARED, edge_type="USES")
        assert [(name[c.node.id], c.shared) for c in found.contacts] == [("b", 2)]
        assert found.total == 1
        one = await adapter.shared_contacts(ids["a"], CLEARED, edge_type="USES", min_shared=1)
        assert [(name[c.node.id], c.shared) for c in one.contacts] == [("b", 2), ("c", 1)]

        # c gains a SECRET third contact with a, and a link to y the reader cannot see.
        hidden = _node("Endpoint", classification="SECRET")
        await _write(adapter, [hidden], [])
        await _write(adapter, [], [
            _edge("USES", ids["a"], hidden.id, classification="OFFICIAL"),
            _edge("USES", ids["c"], hidden.id, classification="OFFICIAL"),
            _edge("USES", ids["c"], ids["y"], classification="SECRET"),
        ])
        seen = await adapter.shared_contacts(ids["a"], OFFICIAL, edge_type="USES")
        assert [(name.get(c.node.id), c.shared) for c in seen.contacts] == [("b", 2)]
        assert seen.total == 1
        # A case reading another dataset sees no `a`, so nobody shares with it.
        elsewhere = OFFICIAL.model_copy(update={"datasets": ["enron"]})
        assert (await adapter.shared_contacts(ids["a"], elsewhere, edge_type="USES")).total == 0
        # The filter is real: cleared, c shares three.
        cleared = await adapter.shared_contacts(ids["a"], CLEARED, edge_type="USES")
        assert (name[cleared.contacts[0].node.id], cleared.contacts[0].shared) == ("c", 3)
        # A node the reader cannot see shares with nobody.
        assert (await adapter.shared_contacts(hidden.id, OFFICIAL, edge_type="USES")).total == 0


async def test_shared_contacts_page_and_say_how_many(factory: GraphAdapterFactory) -> None:
    async with factory.context() as adapter:
        hub = _node("Person", classification="OFFICIAL")
        phones = [_node("Endpoint", classification="OFFICIAL") for _ in range(2)]
        others = [_node("Person", classification="OFFICIAL") for _ in range(4)]
        await _write(adapter, [hub, *phones, *others], [])
        await _write(adapter, [], [
            _edge("USES", p.id, e.id, classification="OFFICIAL")
            for p in [hub, *others] for e in phones
        ])
        first = await adapter.shared_contacts(hub.id, CLEARED, edge_type="USES", limit=3)
        assert len(first.contacts) == 3 and first.total == 4
        assert [c.node.id for c in first.contacts] == sorted(o.id for o in others)[:3]


# --- ADR-102: a repeated write never lowers handling ----------------------------


async def test_a_link_written_again_lower_keeps_its_higher_handling(
    factory: GraphAdapterFactory,
) -> None:
    """Writing the same pair again at OFFICIAL once made a SECRET link OFFICIAL: the latest write's
    handling won. Now the merged link keeps the most restrictive of each part, in either order."""
    async with factory.context() as adapter:
        (a, b), _ = await _write(adapter, [_node("Person", classification="OFFICIAL"),
                                           _node("Person", classification="OFFICIAL")], [])
        await _write(adapter, [], [_edge("ASSOCIATE_OF", a, b, classification="SECRET",
                                         handling_code="C")])
        await _write(adapter, [], [_edge("ASSOCIATE_OF", a, b, classification="OFFICIAL")])
        req = ExpandRequest(node_ids=[a], depth=1)
        assert (await adapter.expand(req, OFFICIAL)).edges == []
        (merged,) = (await adapter.expand(req, CLEARED)).edges
        assert (merged.handling.classification, merged.handling.handling_code) == ("SECRET", "C")
        assert merged.occurrences == 2


async def test_a_node_written_again_lower_keeps_its_higher_handling(
    factory: GraphAdapterFactory,
) -> None:
    async with factory.context() as adapter:
        secret = _node("Person", classification="SECRET")
        await _write(adapter, [secret], [])
        lower = secret.model_copy(
            update={"handling": secret.handling.model_copy(update={"classification": "OFFICIAL"})}
        )
        await _write(adapter, [lower], [])
        assert await adapter.get_node(secret.id, OFFICIAL) is None
        kept = await adapter.get_node(secret.id, CLEARED)
        assert kept is not None and kept.handling.classification == "SECRET"


# --- ADR-123: a link's weight comes from the link alone ------------------------------------------
#
# A visible link K's stored weight must not move because of a link L the viewer cannot see. Each
# case builds two stores that differ only by L, writes K the same way into both, and compares K's
# weight as the viewer reads it. `now_utc` is pinned where the adapter and the bulk loader import
# it (two bindings), so recency is equal and only the counts can differ. Each case is shown red
# under weights version 1 by `test_the_two_store_case_is_red_under_weights_version_1` (and, for
# the bulk path, `test_the_bulk_two_store_case_is_red_under_weights_version_1`): the same two
# stores, the adapter handed version 1's rules, must give K two different weights, so a green
# under the latest version is not a case whose counts never reached the weight.
#
# The paths are how K gets its weight: `upsert_edges`, `supersede_edge` (K is the replacement),
# `supersede_node` (K is re-pointed and keeps the weight it had) and the bulk loader
# (`test_bulk_loader.py`). L is written before K is weighed, except in the three cases that raise
# L's handling after K was weighed (an edge correction, a same-pair merge that raises handling, a
# node correction): there L is visible when K is weighed and hidden afterwards, which is the
# route a weight stored once at write would otherwise keep.

#: The clock the adapter and the bulk loader read, so recency is equal in both stores.
PINNED_NOW = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
#: Sees K, and sees none of the links the cases hide from it.
VIEWER = Principal(
    id="analyst-viewer", clearance="OFFICIAL", org_unit="unit-1", datasets=["fixture"]
)
#: Sees everything the cases write, to prove each hidden link is stored and is hidden from VIEWER.
EVERYTHING = Principal(
    id="analyst-all",
    clearance="SECRET",
    org_unit="unit-restricted",
    receivable_handling_codes=["R"],
)
#: L is hidden when it is written, in turn: above the viewer's clearance, under a restricted
#: handling code, to a node the viewer cannot see, and in a dataset outside the viewer's case.
HIDING_CASES = ("secret", "restricted", "hidden_node", "other_dataset")
#: L is visible when K is weighed and raised afterwards.
RAISING_CASES = ("raised_by_supersede_edge", "raised_by_merge", "raised_by_supersede_node")
ALL_CASES = (*HIDING_CASES, *RAISING_CASES)
K_OCCURRENCES = 3
L_OCCURRENCES = 12
_NODE_DATASETS = ["fixture", "enron"]


def _pin_now(monkeypatch: pytest.MonkeyPatch) -> None:
    """Both places the clock is imported: the adapter's (`upsert_edges`, `supersede_edge`,
    `supersede_node`) and the bulk loader's."""
    import adapters.graph_arcadedb.adapter as adapter_module
    import adapters.graph_arcadedb.bulk as bulk_module

    monkeypatch.setattr(adapter_module, "now_utc", lambda: PINNED_NOW)
    monkeypatch.setattr(bulk_module, "now_utc", lambda: PINNED_NOW)


def _use_weights_version(monkeypatch: pytest.MonkeyPatch, version: int | None) -> None:
    """The conformance factory builds the adapter itself (`arcadedb_adapter`) and takes no rules,
    and the adapter reads the weights file by `load_weight_rules()` where it is constructed and
    hands the result to its bulk loader. So a version is chosen by pointing that name, in the
    adapter's module, at the version by index; `None` leaves the latest in force."""
    if version is None:
        return
    import adapters.graph_arcadedb.adapter as adapter_module
    from ontology.weights import load_weight_history

    rules = load_weight_history()[version - 1]
    assert rules.version == version
    monkeypatch.setattr(adapter_module, "load_weight_rules", lambda: rules)


def _k_interval() -> Interval:
    return Interval(
        valid_from=PINNED_NOW - timedelta(days=200), valid_to=PINNED_NOW - timedelta(days=120)
    )


def _link_k(source: str, target: str, *, occurrences: int = K_OCCURRENCES) -> EdgeWrite:
    return _edge(
        "COMMUNICATED_WITH",
        source,
        target,
        classification="OFFICIAL",
        occurrences=occurrences,
        interval=_k_interval(),
        datasets=["fixture"],
    )


def _link_l(case: str, source: str, target: str) -> EdgeWrite:
    """L, of K's type and at K's source node, so it can move K's degree and its type's total."""
    base: dict[str, Any] = {
        "classification": "OFFICIAL",
        "occurrences": L_OCCURRENCES,
        "interval": _k_interval(),
        "datasets": ["fixture"],
    }
    if case == "secret":
        base["classification"] = "SECRET"
    elif case == "restricted":
        base.update(handling_code="R", owning_unit="unit-restricted")
    elif case == "other_dataset":
        base["datasets"] = ["enron"]
    # "hidden_node": the link is ordinary, its far end is not (see `_two_store_nodes`). The
    # raising cases write the visible form here and raise it afterwards.
    return _edge("COMMUNICATED_WITH", source, target, **base)


async def _two_store_nodes(adapter: GraphPort, case: str) -> tuple[str, str, str]:
    """K's two ends and L's far end: the same in both stores. Only the hidden-node case makes
    the far end one the viewer cannot see."""
    (ka, kb, lx), _ = await _write(
        adapter,
        [
            _node(
                "Endpoint",
                classification="OFFICIAL",
                datasets=_NODE_DATASETS,
                value_normalised="+441000000001",
            ),
            _node(
                "Endpoint",
                classification="OFFICIAL",
                datasets=_NODE_DATASETS,
                value_normalised="+441000000002",
            ),
            _node(
                "Endpoint",
                classification="SECRET" if case == "hidden_node" else "OFFICIAL",
                datasets=_NODE_DATASETS,
                value_normalised="+441000000003",
            ),
        ],
        [],
    )
    return ka, kb, lx


async def _replace_node(
    adapter: GraphPort, node_id: str, *, classification: str, value: str
) -> str:
    tx = await adapter.begin_transaction()
    new_id = await adapter.supersede_node(
        node_id,
        _node(
            "Endpoint",
            classification=classification,
            datasets=_NODE_DATASETS,
            value_normalised=value,
        ),
        tx,
    )
    await adapter.commit_transaction(tx)
    return new_id


async def _build_store(
    adapter: GraphPort, *, case: str, path: str, with_link: bool, same_call: bool = False
) -> tuple[str, str, str]:
    """One of the two stores. Returns K's two ends as they stand at the end (a node correction
    replaces one) and L's far end."""
    from ports.graph import BulkGraphLoader

    ka, kb, lx = await _two_store_nodes(adapter, case)
    link_l = _link_l(case, ka, lx)
    link_k = _link_k(ka, kb)
    l_id: str | None = None
    if with_link and not same_call:
        _, (l_id,) = await _write(adapter, [], [link_l])

    kb_end = kb
    if path == "upsert":
        await _write(adapter, [], [link_k])
    elif path == "edge_supersede":
        _, (first,) = await _write(adapter, [], [_link_k(ka, kb, occurrences=1)])
        tx = await adapter.begin_transaction()
        await adapter.supersede_edge(first, link_k, tx)
        await adapter.commit_transaction(tx)
    elif path == "node_supersede":
        await _write(adapter, [], [link_k])
        kb_end = await _replace_node(
            adapter, kb, classification="OFFICIAL", value="+441000000002"
        )
    elif path == "bulk":
        if not isinstance(adapter, BulkGraphLoader):
            pytest.skip("this adapter does not declare BulkGraphLoader")
        await adapter.bulk_load_edges([link_l, link_k] if with_link and same_call else [link_k])
    else:
        raise AssertionError(f"unknown path {path!r}")

    lx_end = lx
    if with_link and case == "raised_by_supersede_edge":
        assert l_id is not None
        raised = _link_l("secret", ka, lx)
        tx = await adapter.begin_transaction()
        await adapter.supersede_edge(l_id, raised, tx)
        await adapter.commit_transaction(tx)
    elif with_link and case == "raised_by_merge":
        await _write(
            adapter,
            [],
            [_link_l("secret", ka, lx).model_copy(update={"occurrences": 1})],
        )
    elif with_link and case == "raised_by_supersede_node":
        lx_end = await _replace_node(
            adapter, lx, classification="SECRET", value="+441000000003"
        )
    return ka, kb_end, lx_end


async def _visible_k_weight(
    adapter: GraphPort, *, case: str, path: str, with_link: bool, same_call: bool = False
) -> float:
    """K's weight as the viewer reads it. With L present, proves L is stored and is hidden from
    the viewer, so the comparison is between stores that differ by a link the viewer cannot see
    (not by one that is absent, or one the viewer can see)."""
    ka, kb, lx = await _build_store(
        adapter, case=case, path=path, with_link=with_link, same_call=same_call
    )
    seen = await adapter.edges_among([ka, kb], VIEWER)
    assert len(seen) == 1, f"the viewer must see exactly K, saw {len(seen)}"
    (link_k,) = seen
    assert link_k.weight_components is not None
    assert link_k.weight_components.occurrences == K_OCCURRENCES
    if with_link:
        assert len(await adapter.edges_among([ka, lx], EVERYTHING)) == 1, "L must be stored"
        assert await adapter.edges_among([ka, lx], VIEWER) == [], "L must be hidden from the viewer"
    return link_k.weight


async def two_store_weights(
    factory: GraphAdapterFactory,
    monkeypatch: pytest.MonkeyPatch,
    *,
    case: str,
    path: str,
    version: int | None = None,
    same_call: bool = False,
) -> tuple[float, float]:
    """K's weight without L and with L, each in a fresh database, under the weights version chosen
    (`None` is the latest) and a pinned clock. Shared with `test_bulk_loader.py`."""
    _pin_now(monkeypatch)
    _use_weights_version(monkeypatch, version)
    weights: dict[bool, float] = {}
    for with_link in (False, True):
        async with factory.context() as adapter:
            weights[with_link] = await _visible_k_weight(
                adapter, case=case, path=path, with_link=with_link, same_call=same_call
            )
    return weights[False], weights[True]


@pytest.mark.parametrize("path", ["upsert", "edge_supersede", "node_supersede"])
@pytest.mark.parametrize("case", ALL_CASES)
async def test_a_visible_links_weight_is_the_same_in_two_stores_that_differ_by_a_hidden_link(
    factory: GraphAdapterFactory, monkeypatch: pytest.MonkeyPatch, case: str, path: str
) -> None:
    """ADR-123 decisions 1 and 2, `01_DOMAIN_MODEL.md` §6.1, rule 3: a link the viewer cannot see
    (above their clearance, under a restricted handling code, to a node they cannot see, in another
    dataset, or raised after K was weighed by a correction, a merge or a node correction) must not
    move the stored weight of a link they can. Run under the latest weights version; the same cases
    are shown red under version 1 by the test below."""
    without, with_link = await two_store_weights(factory, monkeypatch, case=case, path=path)
    assert with_link == without, (case, path, without, with_link)


@pytest.mark.parametrize("path", ["upsert", "edge_supersede", "node_supersede"])
@pytest.mark.parametrize("case", ALL_CASES)
async def test_the_two_store_case_is_red_under_weights_version_1(
    factory: GraphAdapterFactory, monkeypatch: pytest.MonkeyPatch, case: str, path: str
) -> None:
    """Rule 15 for the test above: the same two stores with the adapter handed version 1's rules
    (gamma 0.3) give K two different weights, in every case and by every path. A green above is
    therefore not a pair of stores whose counts never reached K's weight."""
    without, with_link = await two_store_weights(
        factory, monkeypatch, case=case, path=path, version=1
    )
    assert abs(with_link - without) > 1e-6, (case, path, without, with_link)


async def test_a_same_pair_merge_carries_another_datasets_occurrences_today(
    factory: GraphAdapterFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ADR-123 decision 4 RECORDS an open route; it does not close it. A write to a pair the store
    already holds is merged into the stored link whatever dataset wrote it (`_find_existing_edge`
    does not filter by dataset), so a case reading one dataset sees the occurrences another wrote,
    in the link's count and so in its weight.

    This asserts today's behaviour. It is the defect logged in `07_BUILD_PLAN.md` as "a same-pair
    merge carries another dataset's occurrences", for the owner to decide: when that is fixed,
    this test changes with it (and must then assert the opposite). Here an `enron` write of 5 and a
    `fixture` write of 2 to one pair give a viewer of `fixture` alone one link of 7, weighed as a
    link of 7 and not as one of 2."""
    _pin_now(monkeypatch)

    async def stored_link(writes: list[tuple[list[str], int]]) -> Edge:
        async with factory.context() as adapter:
            (a, b), _ = await _write(
                adapter,
                [
                    _node(
                        "Endpoint",
                        classification="OFFICIAL",
                        datasets=_NODE_DATASETS,
                        value_normalised=f"+44100000000{n}",
                    )
                    for n in (1, 2)
                ],
                [],
            )
            for datasets, occurrences in writes:
                link = _link_k(a, b, occurrences=occurrences).model_copy(
                    update={"datasets": datasets}
                )
                await _write(adapter, [], [link])
            (seen,) = await adapter.edges_among([a, b], IN_FIXTURE)
            return seen

    merged = await stored_link([(["enron"], 5), (["fixture"], 2)])
    seven = await stored_link([(["fixture"], 7)])
    two = await stored_link([(["fixture"], 2)])

    assert merged.datasets == ["enron", "fixture"]
    assert merged.occurrences == 7, "the viewer of `fixture` alone sees enron's 5 in the count"
    assert merged.weight_components is not None and merged.weight_components.occurrences == 7
    assert merged.weight == pytest.approx(seven.weight, abs=1e-9)
    assert abs(merged.weight - two.weight) > 1e-3, "and in the weight"

