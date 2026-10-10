"""Operation Ledger's own proof (ADR-108 Amendment 4) — `build_ledger_graph` against a live
ArcadeDB with the deployment ontology, the same one-expensive-build-many-assertions shape
`test_hmp_graph.py` set. What a mistake would do, and the section that catches it:

- a FIBO `Account` failing to load, or the money flow not linking account to account, would be
  Amendment 4 unwired (the accounts and TRANSACTED sections);
- a deposit at or over £10,000, or the count drifting from the SAR's own words, would break the
  structuring story (the drumbeat section);
- HALE's control written asserted would be rule 5 violated in a demo everyone screenshots (the
  inferred-control section);
- the SAR not landing as a held Document would leave the reader nothing to extract from (the
  held-content section);
- a place or branch without its geometry row would put nothing on the map (the geometry section).
"""

from __future__ import annotations

from adapters.graph_arcadedb.testing import arcadedb_adapter
from adapters.media_objectstore.testing import InMemoryMediaStore
from demo_fixtures.ledger import (
    BRIGHTPATH_ACC,
    POINTS,
    SAR_TEXT,
    STRUCTURED_DEPOSITS,
    build_ledger_graph,
    geometry_records,
    transaction_rows,
)
from ontology.handling import load_uk_le_scheme
from ontology.packs import load_deployment_ontology
from schemas.domain import ExpandRequest, Principal, ProvenanceState

ANALYST = Principal(id="analyst-1", clearance="OFFICIAL", org_unit="verify")


def test_the_drumbeat_matches_the_sar() -> None:
    rows = transaction_rows()
    deposits = [r for r in rows if r["payee_iban"] == BRIGHTPATH_ACC and r["transaction_type"] == "CASH_IN"]
    assert len(deposits) == STRUCTURED_DEPOSITS == 26
    assert "twenty-six" in SAR_TEXT
    assert all(9400 <= float(r["amount"]) < 10000 for r in deposits)
    assert rows == sorted(rows, key=lambda r: r["at"])


def test_every_point_has_its_geometry_row() -> None:
    assert {record.geometry_ref for record in geometry_records()} == set(POINTS)


async def test_ledger_graph_side() -> None:
    ontology = load_deployment_ontology()
    scheme = load_uk_le_scheme()
    media = InMemoryMediaStore()

    async with arcadedb_adapter(ontology, scheme) as graph:
        result = await build_ledger_graph(
            graph=graph, ontology=ontology, principal=ANALYST, media=media
        )

        # The accounts and the money flow — FIBO types, loaded and found again by number.
        brightpath_account = await graph.find_node("Account", "account_number", BRIGHTPATH_ACC, ANALYST)
        assert brightpath_account is not None
        around = await graph.expand(
            ExpandRequest(node_ids=[brightpath_account.id], depth=1, edge_types=["TRANSACTED"]),
            ANALYST,
        )
        transacted = [e for e in around.edges if e.type == "TRANSACTED"]
        # Three mule accounts in, one transfer out — same-pair deposits merge into one link each.
        assert len(transacted) == 4
        assert result.transactions_loaded == len(transaction_rows())

        # The timeline's events: every transaction row became one, in order.
        assert len(result.events) == len(transaction_rows())
        assert all(event.edge_type == "TRANSACTED" for event in result.events)

        # The ring: HALE's control of the shell is inferred, never asserted (rule 5).
        hale = await graph.find_node("Person", "family_name", "Hale", ANALYST)
        brightpath = await graph.find_node("Organisation", "name", "Brightpath Consulting Ltd", ANALYST)
        assert hale is not None and brightpath is not None
        hale_edges = await graph.expand(
            ExpandRequest(node_ids=[hale.id], depth=1, edge_types=["CONTROLS"]), ANALYST
        )
        (controls,) = [e for e in hale_edges.edges if e.type == "CONTROLS"]
        assert controls.target == brightpath.id
        assert controls.provenance.state is ProvenanceState.INFERRED
        assert (controls.provenance.extracted_by or "").startswith("model:")

        # PETROV is the paper owner of the shell.
        petrov = await graph.find_node("Person", "family_name", "Petrov", ANALYST)
        assert petrov is not None
        petrov_edges = await graph.expand(
            ExpandRequest(node_ids=[petrov.id], depth=1, edge_types=["BENEFICIAL_OWNER_OF"]), ANALYST
        )
        assert any(e.target == brightpath.id for e in petrov_edges.edges)

        # The SAR is held content: a Document in the graph, its text in the media store.
        assert result.sar_document_id is not None
        sar = await graph.get_node(result.sar_document_id, ANALYST)
        assert sar is not None and sar.type == "Document"
        assert (await media.get(sar.properties["object_ref"])).decode() == SAR_TEXT

        # The places carry the refs the geometry partition answers.
        office = await graph.find_node(
            "Location", "name", "Suite 14, 83 Colmore Row, Birmingham", ANALYST
        )
        assert office is not None
        assert office.properties["geometry_ref"] in POINTS
        assert brightpath_account.properties["geometry_ref"] in POINTS


async def test_the_layered_structure_traces_to_its_beneficial_owners() -> None:
    """ADR-109 phase C: Crescent Imports is held through a BVI company and a Cyprus trust, with a
    cross-holding and a nominee. Worked by hand, as the spec's conformance cases are:

    - Tamarind Holdings (BVI) owns 90% of Crescent: 90%.
    - Aegean Fiduciary Trust (Cyprus) owns 70% of Tamarind: 0.7 × 0.9 = 63%.
    - PETROV owns 60% of Aegean and 10% of Crescent directly: 0.6 × 0.7 × 0.9 + 10 = 47.8%.
    - NAIR owns 40% of Aegean: 0.4 × 0.7 × 0.9 = 25.2% — just over the 25% threshold.
    - Kestrel Nominees holds Tamarind by an unstated share: share unknown, never assumed.
    - Tamarind owns 15% of Aegean: a circle with Aegean, flagged, never looped.
    And one person, one node: PETROV, named by the companies register and the direct writes alike,
    is a single Person (a second would split her ownership between two nodes)."""
    from adapters.compute_rustworkx.adapter import ComputeRustworkxAdapter
    from services.api.ownership import trace_for

    ontology = load_deployment_ontology()
    async with arcadedb_adapter(ontology, load_uk_le_scheme()) as graph:
        await build_ledger_graph(graph=graph, ontology=ontology, principal=ANALYST)
        people = (await graph.list_nodes("Person", ANALYST, limit=500)).nodes
        assert [p.properties.get("given_names") for p in people
                if p.properties.get("family_name") == "Petrov"] == ["Elena"]  # fmt: skip

        crescent = await graph.find_node("Organisation", "name", "Crescent Imports Ltd", ANALYST)
        assert crescent is not None
        view = await trace_for(graph, ComputeRustworkxAdapter(), crescent.id, ANALYST)
        names = {n.id: n.properties.get("name") or n.properties.get("family_name") for n in view.nodes}
        shares = {names[o.node_id]: round(o.cumulative_percent, 6) for o in view.trace.owners}
        assert shares["Tamarind Holdings Ltd"] == 90.0
        assert shares["Aegean Fiduciary Trust"] == 63.0
        assert shares["Petrov"] == 47.8
        assert shares["Nair"] == 25.2
        owners = {names[o.node_id]: o for o in view.trace.owners}
        assert owners["Petrov"].beneficial_owner and owners["Nair"].beneficial_owner
        assert owners["Kestrel Nominees Ltd"].share_unknown is True
        assert [sorted(names[n] for n in c) for c in view.trace.cycles] == [
            ["Aegean Fiduciary Trust", "Tamarind Holdings Ltd"]
        ]
