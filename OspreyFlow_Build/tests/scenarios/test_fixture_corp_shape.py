"""Proves Fixture Corp (`packages/demo_fixtures/fixture_corp.py`) actually exercises the four
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

from adapters.compute_rustworkx.testing import compute_rustworkx_adapter
from adapters.graph_arcadedb.testing import arcadedb_adapter
from demo_fixtures.fixture_corp import (
    build_path_spokes,
    generate_community_rings,
    generate_resolution_persons,
)
from demo_fixtures.fixture_corp_resolution import (
    ADR_035_C5_SCORES,
    resolve_fixture_corp_pairs,
    scores_by_pair_label,
)
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


def test_every_fixture_corp_entity_carries_the_identifier_search_matches_on() -> None:
    """**Owner ruling R4, 26 September 2026.** Round 12 found Fixture Corp could not be
    demonstrated in the Glass at all: the working set's one entry point is the search box,
    `search_nodes` matches only the identifier fields the ontology declares, and this fixture set
    none of them — 0 of its 65 Persons, against 400 of 400 for HMP. Three of ADR-035 §C5's four
    interactive checks were impossible rather than merely undone.

    This is the test that fails if that regresses. Asserted over *every* node the fixture builds,
    not a sample: one Person without a `nino` is one the presenter cannot reach, and the failure
    would show up as "the demo doesn't work" long after the change that caused it.

    The values must also be **deterministic** — a presenter types one from `DEMO_GUIDE.md` and
    `apps/workspace/live/fixture-corp.spec.ts` asserts on it, so a per-process value (a salted
    `hash()`, a random id) would break both while every other test still passed."""
    pairs = generate_resolution_persons()
    rings = generate_community_rings()

    persons = [p.node_a for p in pairs] + [p.node_b for p in pairs]
    persons += [n for n in rings.nodes if n.type == "Person"]
    organisations = [n for n in rings.nodes if n.type == "Organisation"]

    assert persons and organisations, "fixture built no Persons or no Organisations"

    for node in persons:
        nino = node.properties.get("nino")
        assert isinstance(nino, str) and nino, f"{node.id} carries no nino — unsearchable"
        # `QQ` is a prefix HMRC never issues, so no value here can collide with a real person's
        # NINO. This is the assertion that keeps the fixture synthetic *by construction*
        # (`CLAUDE.md` rule 9), not by anyone remembering to keep it so.
        assert nino.startswith("QQ"), (node.id, nino)
        assert len(nino) == 9, (node.id, nino)

    for node in organisations:
        org_ref = node.properties.get("org_ref")
        assert isinstance(org_ref, str) and org_ref, f"{node.id} carries no org_ref"
        assert org_ref.startswith("FIXTURE-"), (node.id, org_ref)

    # Unique, so a search for one names one node rather than silently returning several.
    ninos = [n.properties["nino"] for n in persons]
    assert len(set(ninos)) == len(ninos), "two Persons share a nino"

    # Deterministic: a second call to the generators produces the same values.
    again = [p.node_a for p in generate_resolution_persons()]
    for before, after in zip(persons[: len(again)], again, strict=False):
        assert before.properties["nino"] == after.properties["nino"], (
            f"{before.id}'s nino changed between two calls in the same process — it must be "
            "derived from the node id, never generated per call"
        )


def test_the_live_resolution_pass_reproduces_adr_035_c5s_recorded_scores() -> None:
    """**ADR-035 §C5's recorded scores, checked rather than trusted** (round 12e).

    §C5 records five numbers in prose, and prose cannot be checked — so for three rounds nothing
    would have noticed them drifting. Round 12d then read the wrong field off the store (the
    edge's `weight`, `01_DOMAIN_MODEL.md` §6.1's load-time strength formula, rather than
    `properties["score"]`, which is what `services/resolve/projection.py` actually collapses on)
    and concluded the fixture had diverged from the ADR. It had not: every score matches to the
    sixth decimal, measured off a real seeded store.

    This is the assertion that makes that checkable from now on, against the *same* pass the seed
    runs (`fixture_corp_resolution.py`). It fails if the resolver, the ontology's comparisons, the
    fixture's own names/dates, or the ADR's recorded figures move apart from each other."""
    measured = scores_by_pair_label()

    for label, recorded in ADR_035_C5_SCORES.items():
        score = measured[label]
        assert score is not None, (
            f"{label} was not scored at all — §C5 records {recorded}, and a pair the resolver "
            "never emits a candidate for cannot produce the projection §C5 describes"
        )
        assert round(score, 4) == round(recorded, 4), (
            f"{label}: ADR-035 §C5 records {recorded}, the live pass produced {score}. "
            "Note this is the match *score*, not the edge weight — they are different "
            "quantities and only the score drives resolution."
        )


def test_fixture_corp_entity_resolution_projections_differ_by_threshold() -> None:
    """ADR-035 §C5, property 1: "entity resolution at τ 0.99, 0.95 and 0.80 producing visibly
    different projections." Runs the real, untrained `resolve_entity_type` against the fixture's
    four resolution pairs, then the real, pure `compute_clusters` at each of the three detents —
    the same τ Strict/Balanced/Broad the Glass itself offers (`01_DOMAIN_MODEL.md` §4)."""
    pairs = generate_resolution_persons()
    # The same pass the seed runs — `fixture_corp_resolution.py` owns it, so the test and the
    # demo cannot come to measure different populations (round 12e; STANDING.md's rule of
    # 27 September).
    candidates = resolve_fixture_corp_pairs()
    nodes = [p.node_a for p in pairs] + [p.node_b for p in pairs]

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
