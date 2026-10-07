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

from datetime import UTC, datetime, timedelta

import pytest

from conduit_common.identity import new_edge_id, new_node_id, now_utc
from ontology.errors import OntologyError
from ports.graph import GraphPort, SuggestOptions
from schemas.domain import (
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


async def test_subgraph_filtered_count_is_the_declared_placeholder_zero(
    factory: GraphAdapterFactory,
) -> None:
    """`01_DOMAIN_MODEL.md` §8: `filtered_count` is reserved and left at
    `0` until Phase 3's Working-Set Service computes it — a declared gap,
    not a silent one. Pinned here so a future change either keeps the
    declaration honest or updates it deliberately, rather than drifting
    unnoticed."""
    async with factory.context() as adapter:
        (hub,), _ = await _write(adapter, [_node("Person", classification="OFFICIAL")], [])
        await _write(adapter, [_node("Person", classification="SECRET")], [])
        subgraph = await adapter.expand(ExpandRequest(node_ids=[hub], depth=1), OFFICIAL)
        assert subgraph.filtered_count == 0


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


# --- expand_candidate_count (01_DOMAIN_MODEL.md §8.2 / filtered_count) ------


async def test_expand_candidate_count_matches_expand_when_nothing_is_hidden(
    factory: GraphAdapterFactory,
) -> None:
    async with factory.context() as adapter:
        (hub, visible), _ = await _write(
            adapter,
            [
                _node("Person", classification="OFFICIAL"),
                _node("Endpoint", classification="OFFICIAL"),
            ],
            [],
        )
        await _write(adapter, [], [_edge("USES", hub, visible, classification="OFFICIAL")])

        req = ExpandRequest(node_ids=[hub], depth=1)
        subgraph = await adapter.expand(req, CLEARED)
        candidate_count = await adapter.expand_candidate_count(req)

        assert candidate_count == len(subgraph.nodes) == 2


async def test_expand_candidate_count_includes_nodes_an_unauthorised_expand_excludes(
    factory: GraphAdapterFactory,
) -> None:
    """The unfiltered half of `filtered_count`'s comparison
    (`01_DOMAIN_MODEL.md` §8.2): a SECRET neighbour an OFFICIAL principal's
    `expand()` cannot see must still be in `expand_candidate_count`'s
    reckoning, since that reckoning carries no principal at all — proving
    it is genuinely unfiltered, not a second filtered call in disguise."""
    async with factory.context() as adapter:
        (hub,), _ = await _write(adapter, [_node("Person", classification="OFFICIAL")], [])
        (visible,), _ = await _write(adapter, [_node("Endpoint", classification="OFFICIAL")], [])
        (secret_neighbour,), _ = await _write(
            adapter, [_node("Endpoint", classification="SECRET")], []
        )
        await _write(
            adapter,
            [],
            [
                _edge("USES", hub, visible, classification="OFFICIAL"),
                _edge("USES", hub, secret_neighbour, classification="SECRET"),
            ],
        )

        req = ExpandRequest(node_ids=[hub], depth=1)
        unauthorised = await adapter.expand(req, OFFICIAL)
        authorised = await adapter.expand(req, CLEARED)
        candidate_count = await adapter.expand_candidate_count(req)

        assert len(unauthorised.nodes) == 2  # hub + visible only
        assert len(authorised.nodes) == 3  # hub + visible + secret_neighbour
        assert candidate_count == 3
        assert candidate_count - len(unauthorised.nodes) == 1  # what filtered_count must report


async def test_expand_candidate_count_excludes_reverted_and_superseded_nodes(
    factory: GraphAdapterFactory,
) -> None:
    """Structural exclusion (reverted, superseded) is not what
    `filtered_count` means — those elements were never real data to begin
    with, the same as for every other read — so `expand_candidate_count`
    must drop them exactly as `expand()` does, even though it applies
    neither access axis."""
    async with factory.context() as adapter:
        (hub,), _ = await _write(adapter, [_node("Person", classification="OFFICIAL")], [])
        (reverted_neighbour,), _ = await _write(
            adapter, [_node("Endpoint", classification="OFFICIAL")], []
        )
        _, (touched_edge_id,) = await _write(
            adapter, [], [_edge("USES", hub, reverted_neighbour, classification="OFFICIAL")]
        )
        tx = await adapter.begin_transaction()
        await adapter.revert_elements([reverted_neighbour], [touched_edge_id], tx)
        await adapter.commit_transaction(tx)

        req = ExpandRequest(node_ids=[hub], depth=1)
        candidate_count = await adapter.expand_candidate_count(req)

        assert candidate_count == 1  # hub only — the reverted neighbour never counts


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
    unmodified `MatchBuilder` before Stage 4's own widening."""
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
        ".has(\"handling_classification\",within(['OFFICIAL','OFFICIAL-SENSITIVE','SECRET']))"
        '.filter(or(has("handling_code",within([\'P\',\'C\'])),and(has("handling_code",within([])),'
        'or(has("owning_unit",\'unit-1\'),has("originator",\'unit-1\'))))).as(\'p\')'
        ".select('p').outE('mx_USES')"
        '.has("reverted",false).hasNot("superseded_by")'
        '.has("handling_classification",within([\'OFFICIAL\',\'OFFICIAL-SENSITIVE\',\'SECRET\']))'
        '.filter(or(has("handling_code",within([\'P\',\'C\'])),and(has("handling_code",within([])),'
        "or(has(\"owning_unit\",'unit-1'),has(\"originator\",'unit-1')))))"
        ".inV()"
        '.has("reverted",false).hasNot("superseded_by")'
        '.has("handling_classification",within([\'OFFICIAL\',\'OFFICIAL-SENSITIVE\',\'SECRET\']))'
        '.filter(or(has("handling_code",within([\'P\',\'C\'])),and(has("handling_code",within([])),'
        "or(has(\"owning_unit\",'unit-1'),has(\"originator\",'unit-1'))))).hasLabel('mx_Endpoint')"
        ".as('e').select('p','e').by(elementMap()).dedup().limit(1000)"
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
    """The Glass never sees an unfiltered count, and an unauthorised
    principal must not detect a filtered node's existence via an aggregate) — applied to the
    visual query builder's own estimate, which is shown to the analyst directly rather than
    reconciled by an authorised caller the way `expand_candidate_count` is. A principal who
    cannot see a matching node must get a *smaller* count, not the same one with the node itself
    merely missing from a list."""
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
        upper = await _suggest_account(adapter, "Jeff.Skilling@enron.com")
        lower = await _suggest_account(adapter, "jeff.dasovich@enron.com")
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


# --- ADR-099: a case sees only its own datasets ------------------------------
#
# The third axis, built like the other two: in the traversal, never after it. Each case below is
# the dataset twin of a handling one above (get_node, degree, path length, match, its count,
# edges_among), plus what only datasets have: an element in two datasets, the union on a second
# write, search and suggestions, and the candidate count, which must not count another dataset's
# neighbours as "hidden" (what lies outside a case's datasets is not in its world).


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


async def test_expansion_and_its_candidate_count_stay_within_the_cases_datasets(
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
        # Nothing is "hidden" from the case: the other dataset's neighbour is not counted at all.
        assert await adapter.expand_candidate_count(req, datasets=["fixture"]) == 2
        assert await adapter.expand_candidate_count(req) == 3  # unlimited, as before


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

