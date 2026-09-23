"""Proves Fixture Corp (`tests/scenarios/fixtures/fixture_corp.py`) actually exercises the four
properties `06_DECISIONS.md` ADR-035 §C5 pins, against real adapters — not a docstring claim
nobody checks, the same "fixture-shape-proven-early" discipline `test_hmp_fixture_shape.py`
already established for Scenario A's own fixture.

Properties 1 and 2 need no live service — `resolve_entity_type`/`compute_clusters` and
`ComputeRustworkxAdapter` are both pure, in-process functions. Properties 3 and 4 need a real
ArcadeDB, via the same `arcadedb_adapter` context manager the `GraphPort` conformance suite uses.
"""

from __future__ import annotations

from datetime import UTC, datetime

from services.resolve.projection import (
    THRESHOLD_BALANCED,
    THRESHOLD_BROAD,
    THRESHOLD_STRICT,
    compute_clusters,
)
from services.resolve.resolver import resolve_entity_type
from tests.scenarios.fixtures.fixture_corp import (
    build_path_spokes,
    generate_community_rings,
    generate_resolution_persons,
)

from adapters.compute_rustworkx.testing import compute_rustworkx_adapter
from adapters.graph_arcadedb.testing import arcadedb_adapter
from ontology.handling import load_uk_le_scheme
from ontology.loader import load_default_ontology
from schemas.compute import CommunityRequest
from schemas.domain import (
    AuditStub,
    Edge,
    Handling,
    PathRequest,
    Principal,
    Provenance,
    ProvenanceState,
    SourceRef,
    Subgraph,
)

PERSON_TYPE = next(e for e in load_default_ontology().entity_types if e.name == "Person")

OFFICIAL = Principal(id="fixture-corp-official", clearance="OFFICIAL", org_unit="fixture-corp")
CLEARED = Principal(id="fixture-corp-cleared", clearance="SECRET", org_unit="fixture-corp")


def _same_as_edge(source: str, target: str, score: float) -> Edge:
    return Edge(
        id=f"{source}-{target}",
        type="SAME_AS",
        source=source,
        target=target,
        properties={"score": score},
        provenance=Provenance(
            state=ProvenanceState.INFERRED,
            sources=[SourceRef(document_id="fixture-corp", locator="resolution", excerpt_hash="")],
            first_seen=datetime.now(UTC),
        ),
        handling=Handling(
            classification="OFFICIAL", handling_code="P", originator="u", owning_unit="u"
        ),
        audit=AuditStub(created_at=datetime.now(UTC), created_by="fixture-corp-generator"),
    )


def test_fixture_corp_entity_resolution_projections_differ_by_threshold() -> None:
    """ADR-035 §C5, property 1: "entity resolution at τ 0.99, 0.95 and 0.80 producing visibly
    different projections." Runs the real, untrained `resolve_entity_type` against the fixture's
    four resolution pairs, then the real, pure `compute_clusters` at each of the three detents —
    the same τ Strict/Balanced/Broad the Glass itself offers (`01_DOMAIN_MODEL.md` §4)."""
    pairs = generate_resolution_persons()
    nodes = [p.node_a for p in pairs] + [p.node_b for p in pairs]
    candidates = resolve_entity_type(nodes, PERSON_TYPE)

    score_by_label: dict[str, float | None] = {}
    for pair in pairs:
        ids = {pair.node_a.id, pair.node_b.id}
        score = next((c.score for c in candidates if {c.node_a, c.node_b} == ids), None)
        score_by_label[pair.label] = score

    # Every pair with a claimed merge threshold really did score high enough to cross it, and
    # the "never merges" pair really did score below even the laxest detent — the fixture's own
    # docstring numbers, re-checked live rather than trusted.
    for pair in pairs:
        score = score_by_label[pair.label]
        if pair.merges_from_tau is None:
            assert score is None or score < THRESHOLD_BROAD, (pair.label, score)
        else:
            assert score is not None and score >= pair.merges_from_tau, (pair.label, score)

    same_as_edges = [
        _same_as_edge(pair.node_a.id, pair.node_b.id, score)
        for pair in pairs
        if (score := score_by_label[pair.label]) is not None
    ]
    node_ids = [n.id for n in nodes]

    def merged_pair_labels(tau: float) -> set[str]:
        clusters = compute_clusters(node_ids, same_as_edges, [], tau=tau)
        return {p.label for p in pairs if clusters[p.node_a.id] == clusters[p.node_b.id]}

    strict, balanced, broad = (
        merged_pair_labels(THRESHOLD_STRICT),
        merged_pair_labels(THRESHOLD_BALANCED),
        merged_pair_labels(THRESHOLD_BROAD),
    )

    assert strict == {"identical", "identical_non_latin_script"}
    assert balanced == {"identical", "identical_non_latin_script", "close_given_name"}
    assert broad == {
        "identical",
        "identical_non_latin_script",
        "close_given_name",
        "close_surname_and_given",
    }
    # Visibly different at every one of the three detents, not merely "some difference somewhere."
    assert strict < balanced < broad


async def test_fixture_corp_exhibits_louvain_community_structure() -> None:
    """ADR-035 §C5, property 2: "community structure the selected algorithm (Louvain, per
    ADR-029) actually finds." Three dense, disjoint rings; Louvain must recover exactly three
    communities, each matching one ring's own membership exactly — not merely find *some*
    structure."""
    result = generate_community_rings(rings=3, members_per_ring=6)
    subgraph = Subgraph(nodes=result.nodes, edges=result.edges)

    async with compute_rustworkx_adapter() as compute:
        partition = await compute.communities(CommunityRequest(subgraph=subgraph))

    assert len({partition[n.id] for n in result.nodes}) == 3

    for a in result.nodes:
        for b in result.nodes:
            same_ring = result.ring_of_node_id[a.id] == result.ring_of_node_id[b.id]
            same_community = partition[a.id] == partition[b.id]
            assert same_ring == same_community, (a.id, b.id)


async def test_fixture_corp_path_lengths_span_the_pathfinders_max_hops_range() -> None:
    """ADR-035 §C5, property 3: "path lengths across the pathfinder's own supported range
    (`max_hops<=8`)." The hub-and-spokes fixture has exactly one route of each length 1..8;
    every one of them is found, at exactly its own length, by a real `GraphPort.paths`."""
    ontology = load_default_ontology()
    scheme = load_uk_le_scheme()
    async with arcadedb_adapter(ontology, scheme) as graph:
        result = await build_path_spokes(graph, max_length=8)
        assert set(result.terminal_by_length) == set(range(1, 9))

        for length, terminal in result.terminal_by_length.items():
            paths = await graph.paths(
                PathRequest(source=result.hub_id, target=terminal, max_hops=8, k=5), OFFICIAL
            )
            assert {p.length for p in paths} == {length}, length


async def test_fixture_corp_hidden_hop_lengthens_rather_than_removes_the_path() -> None:
    """ADR-035 §C5, property 4: "an access-control boundary where a hidden hop lengthens the
    path rather than removing it" — the same property
    `test_unauthorised_path_length_matches_a_graph_without_the_hidden_hop`
    (`tests/conformance/graph_port/test_suite.py`) already proves generically, demonstrated here
    against Fixture Corp's own rendered data. An OFFICIAL-cleared principal only ever finds the
    honest 3-hop route to the shortcut spoke's own terminal; a SECRET-cleared principal also
    finds the 1-hop SECRET shortcut — the 3-hop route never disappears for either."""
    ontology = load_default_ontology()
    scheme = load_uk_le_scheme()
    async with arcadedb_adapter(ontology, scheme) as graph:
        result = await build_path_spokes(graph, max_length=8)
        terminal = result.terminal_by_length[result.shortcut_spoke_length]

        official_paths = await graph.paths(
            PathRequest(source=result.hub_id, target=terminal, max_hops=8, k=5), OFFICIAL
        )
        cleared_paths = await graph.paths(
            PathRequest(source=result.hub_id, target=terminal, max_hops=8, k=5), CLEARED
        )

        assert {p.length for p in official_paths} == {result.shortcut_spoke_length}
        assert {p.length for p in cleared_paths} == {1, result.shortcut_spoke_length}
