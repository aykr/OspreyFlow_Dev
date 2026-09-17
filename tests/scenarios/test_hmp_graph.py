"""Proves the HMP fixture's graph side (`tests/scenarios/fixtures/
hmp_graph.py`) — `08_ACCEPTANCE_SCENARIOS.md` Scenario A, `07_BUILD_PLAN.md`
Phase 5. `test_hmp_fixture_shape.py` already proves the untouched
analytics-only shape; this proves the graph side built on top of it: real
`Location`/`Person`/`Organisation` nodes, `PRESENT_AT`/`FAMILY_OF`/
`MEMBER_OF`/`ASSOCIATE_OF`/`MENTIONED_IN` edges, and that
`current_window_events` still carries the exact statistical shape
`test_hmp_fixture_shape.py` proves for `generate_hmp_events()` — the id
substitution must not have quietly changed it.

One test function, not many: `build_hmp_graph()` runs six recipes plus 266
direct edge writes against a live ArcadeDB — expensive enough that paying
for it once and asserting everything in sequence is the right trade
against nine separate `arcadedb_adapter` contexts each repeating the whole
build. Each section below is labelled with what it checks, so a failure's
location is still legible from the assertion message and traceback.
"""

from __future__ import annotations

from tests.scenarios.fixtures.hmp import HOTSPOT_YARDS, PEAK_HOURS, TOTAL_INCIDENTS
from tests.scenarios.fixtures.hmp_graph import PRIOR_PERIOD_YARD, build_hmp_graph
from tests.scenarios.fixtures.hmp_population import (
    PRINCIPAL_SUBJECT_INDEX,
    RELAY_GROUP_INDICES,
    RELAY_ORG_REF,
    SECOND_SUBJECT_INDEX,
    STRUCTURED_REPORTS,
    TOTAL_PERSONS,
    TOTAL_REPORTS,
    YARD_LETTERS,
    generate_persons,
)

from adapters.analytics_duckdb.testing import duckdb_adapter
from adapters.graph_arcadedb.testing import arcadedb_adapter
from ontology.handling import load_uk_le_scheme
from ontology.loader import load_default_ontology
from schemas.analytics import EventFilter, HistogramBucketing, HistogramRequest
from schemas.domain import ExpandRequest, Principal

CLEARED = Principal(id="analyst-1", clearance="OFFICIAL", org_unit="hmp-hollywood")


async def test_hmp_graph_side() -> None:
    ontology = load_default_ontology()
    scheme = load_uk_le_scheme()

    async with arcadedb_adapter(ontology, scheme) as graph:
        result = await build_hmp_graph(graph=graph, ontology=ontology, principal=CLEARED)

        # --- yards and persons exist -----------------------------------
        assert set(result.yard_node_ids) == set(YARD_LETTERS)
        assert len(result.person_node_ids) == TOTAL_PERSONS
        for letter in YARD_LETTERS:
            node = await graph.get_node(result.yard_node_ids[letter], CLEARED)
            assert node is not None
            assert node.properties["name"] == f"Yard {letter}"
        principal_node = await graph.get_node(result.principal_subject_id, CLEARED)
        assert principal_node is not None
        assert principal_node.type == "Person"

        # --- every person has a PRESENT_AT edge to their own cell -------
        # (spot-checked, not exhaustive over 400). Checked for *presence*,
        # not exclusivity: the principal and second subject also carry
        # PRESENT_AT edges to incident/prior-period yards
        # (`hmp_graph.py`'s own deliberate design — the same edge type
        # models both residency and incident presence), so "exactly one
        # neighbour" is not the right assertion for these two specifically.
        principal_cell_ref = generate_persons()[PRINCIPAL_SUBJECT_INDEX].cell_site_ref
        second_cell_ref = generate_persons()[SECOND_SUBJECT_INDEX].cell_site_ref
        for person_id, expected_cell_ref in (
            (result.principal_subject_id, principal_cell_ref),
            (result.second_subject_id, second_cell_ref),
        ):
            subgraph = await graph.expand(
                ExpandRequest(node_ids=[person_id], depth=1, edge_types=["PRESENT_AT"]), CLEARED,
            )
            locations = [n for n in subgraph.nodes if n.id != person_id and n.type == "Location"]
            assert any(loc.properties.get("site_ref") == expected_cell_ref for loc in locations)

        # --- the principal and second subject are family (A10) ---------
        family_subgraph = await graph.expand(
            ExpandRequest(
                node_ids=[result.principal_subject_id], depth=1, edge_types=["FAMILY_OF"],
            ),
            CLEARED,
        )
        related_ids = {n.id for n in family_subgraph.nodes} - {result.principal_subject_id}
        assert result.second_subject_id in related_ids

        # --- the relay group is a near-complete subgraph sharing one ---
        # Organisation: each member is ASSOCIATE_OF every other member (a
        # full 8-clique, 7 internal edges each) plus one external bridge.
        for member_id in result.relay_group_ids:
            stats = await graph.neighbourhood_stats(member_id, CLEARED)
            assert stats.degree_by_type.get("ASSOCIATE_OF", 0) == len(RELAY_GROUP_INDICES)
            org_subgraph = await graph.expand(
                ExpandRequest(node_ids=[member_id], depth=1, edge_types=["MEMBER_OF"]), CLEARED,
            )
            orgs = [n for n in org_subgraph.nodes if n.type == "Organisation"]
            assert len(orgs) == 1
            assert orgs[0].properties["org_ref"] == RELAY_ORG_REF

        # --- reports: structured mentions land on the right people ------
        principal_mentions = await graph.expand(
            ExpandRequest(
                node_ids=[result.principal_subject_id], depth=1, edge_types=["MENTIONED_IN"],
            ),
            CLEARED,
        )
        documents = [n for n in principal_mentions.nodes if n.type == "Document"]
        # hmp_population.generate_report_rows gives the principal 12 of
        # the 68 structured mentions.
        assert len(documents) == 12

        # --- current-window events carry real graph ids, not placeholders --
        assert len(result.current_window_events) == TOTAL_INCIDENTS
        real_person_ids = set(result.person_node_ids.values())
        real_yard_ids = set(result.yard_node_ids.values())
        for event in result.current_window_events:
            assert event.source_id in real_person_ids
            assert event.target_id in real_yard_ids
            assert not event.source_id.startswith("hmp-subject-")
            assert not event.target_id.startswith("hmp-location-")

        # --- the principal subject leads the hotspot/peak intersection (A8) --
        intersection = [
            e for e in result.current_window_events
            if e.properties["yard"] in HOTSPOT_YARDS and e.occurred_at.hour in PEAK_HOURS
        ]
        counts: dict[str, int] = {}
        for e in intersection:
            counts[e.source_id] = counts.get(e.source_id, 0) + 1
        assert counts
        assert max(counts, key=lambda k: counts[k]) == result.principal_subject_id

        # --- prior-period events belong to the second subject, before the --
        # window (A10/A11)
        assert result.prior_period_events
        for event in result.prior_period_events:
            assert event.source_id == result.second_subject_id
            assert event.target_id == result.yard_node_ids[PRIOR_PERIOD_YARD]
            assert event.occurred_at.date().isoformat() < "2026-01-05"

    # --- the id substitution preserved the proved statistical shape ----
    # (test_hmp_fixture_shape.py proves it for generate_hmp_events() itself;
    # this re-checks it for the graph-linked events, against a fresh
    # DuckDB instance since the ArcadeDB context above has closed)
    async with duckdb_adapter(result.current_window_events, scheme) as analytics:
        hist = await analytics.histogram(
            HistogramRequest(
                filter=EventFilter(investigation_scope="case-hmp-fixture"),
                bucketing=HistogramBucketing.CATEGORICAL,
                field="yard",
            ),
            CLEARED,
        )
    by_yard = {b.label: b.count for b in hist.buckets}
    hotspot_share = sum(by_yard[y] for y in HOTSPOT_YARDS) / hist.total
    assert 0.50 <= hotspot_share <= 0.54


def test_report_and_incident_counts_match_scenario_as_own_numbers() -> None:
    assert TOTAL_REPORTS == 229
    assert STRUCTURED_REPORTS == 68
