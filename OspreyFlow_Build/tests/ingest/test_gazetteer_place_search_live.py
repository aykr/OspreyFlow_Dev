"""The map's place search against a live ArcadeDB and a real analytics store (`02_GLASS_FRONTEND.md`
§3.5, ADR-147 Amendment 1; the orchestrator's settlement of 9 November 2026).

The gazetteer is loaded as every build loads it (`scripts.build_local_basemap.load_gazetteer`, from
a synthetic extract: rule 9) into its own dataset, `gazetteer-osm-rutland`, with its points. Then:

- **a case that has added the gazetteer finds its place**, at the place's own point;
- **a case that has not finds nothing**: the store limits the read to the case's datasets (ADR-099,
  rule 3), so a place another dataset holds is not in the case's world;
- a case's own place with a name that matches (a yard on a site plan) is never offered as a place;
- a rebuild writes no second copy of a place (the load's lookup reads the gazetteer's dataset).

Shown red with the stamping removed from `load_gazetteer` (`P4_RED_RECORD.md`). Live, so under
`tests/ingest` (outside `make test`), run under a test-stack lease. The throwaway database is
dropped in teardown, pass or fail (`arcadedb_adapter`); the analytics store is in memory.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import pytest
from scripts.build_local_basemap import load_gazetteer
from services.api.map_places import gazetteer_dataset_id, search_places

from adapters.analytics_duckdb.adapter import AnalyticsDuckDBAdapter
from adapters.analytics_duckdb.schema import create_events_table, create_geometries_table
from adapters.graph_arcadedb.adapter import GraphArcadeDBAdapter
from adapters.graph_arcadedb.testing import arcadedb_adapter
from ontology.handling import load_uk_le_scheme
from ontology.loader import load_default_ontology
from schemas.domain import NodeWrite, Principal, Provenance, ProvenanceState, SourceRef
from schemas.ingest import LoadReport
from schemas.mapconfig import PlaceSearchRequest
from tests.scenarios.fixtures.osm_extract import build_synthetic_osm_pbf

GAZETTEER = gazetteer_dataset_id("rutland")
BUILDER = Principal(id="admin-1", clearance="OFFICIAL", org_unit="unit-1", datasets=[])
#: A case reading its own data and the gazetteer (a composite of the two, ADR-099 Amendment 12).
WITH_GAZETTEER = Principal(
    id="analyst-1", clearance="OFFICIAL", org_unit="unit-1", datasets=["case-a", GAZETTEER]
)
#: The same case before its Author added the gazetteer.
WITHOUT_GAZETTEER = WITH_GAZETTEER.model_copy(update={"datasets": ["case-a"]})


Stores = tuple[GraphArcadeDBAdapter, AnalyticsDuckDBAdapter, Path]


@pytest.fixture
async def stores(
    tmp_path: Path,
) -> AsyncIterator[tuple[GraphArcadeDBAdapter, AnalyticsDuckDBAdapter, Path]]:
    scheme = load_uk_le_scheme()
    con = duckdb.connect(":memory:")
    create_events_table(con)
    create_geometries_table(con)
    extract = tmp_path / "rutland.osm.pbf"
    build_synthetic_osm_pbf(extract)
    try:
        async with arcadedb_adapter(load_default_ontology(), scheme) as graph:
            yield graph, AnalyticsDuckDBAdapter(con, scheme), extract
    finally:
        con.close()


async def _load(
    graph: GraphArcadeDBAdapter, analytics: AnalyticsDuckDBAdapter, extract: Path
) -> LoadReport:
    tx = await graph.begin_transaction()
    report = await load_gazetteer(
        extract, graph=graph, ontology=load_default_ontology(), tx=tx, principal=BUILDER,
        load_id="load-osm-gazetteer-rutland", dataset=GAZETTEER, analytics=analytics,
    )  # fmt: skip
    await graph.commit_transaction(tx)
    return report


async def _a_case_yard(graph: GraphArcadeDBAdapter) -> None:
    """A case's own place, named like the gazetteer's, in the case's own dataset."""
    tx = await graph.begin_transaction()
    await graph.upsert_nodes(
        [
            NodeWrite(
                id="yard-cranford-3", type="Location",
                properties={
                    "name": "Cranford yard 3", "site_ref": "yard-3", "geometry_ref": "g-yard",
                },
                provenance=Provenance(
                    state=ProvenanceState.ASSERTED,
                    sources=[SourceRef(document_id="case-a", locator="1", excerpt_hash="a" * 64)],
                    first_seen=datetime(2026, 1, 1, tzinfo=UTC),
                ),
                handling={  # type: ignore[arg-type]
                    "classification": "OFFICIAL", "handling_code": "P",
                    "originator": "unit-1", "owning_unit": "unit-1",
                },
                created_by="analyst-1", created_at=datetime(2026, 1, 1, tzinfo=UTC),
                datasets=["case-a"],
            )
        ],
        tx,
    )  # fmt: skip
    await graph.commit_transaction(tx)


async def test_a_case_that_added_the_gazetteer_finds_its_place_and_one_that_did_not_finds_nothing(
    stores: Stores,
) -> None:
    graph, analytics, extract = stores
    report = await _load(graph, analytics, extract)
    assert (report.nodes_created, len(report.rejections)) == (3, 0)
    await _a_case_yard(graph)

    found = await search_places(graph, analytics, PlaceSearchRequest(query="cranf"), WITH_GAZETTEER)
    assert [(p.name, round(p.lat, 4), round(p.lon, 4)) for p in found.places] == [
        ("Cranford", 51.488, -0.459)
    ]
    assert found.more is False

    nothing = await search_places(
        graph, analytics, PlaceSearchRequest(query="cranf"), WITHOUT_GAZETTEER
    )
    assert nothing.places == [] and nothing.more is False


async def test_a_rebuild_writes_no_second_copy_of_a_place(stores: Stores) -> None:
    graph, analytics, extract = stores
    await _load(graph, analytics, extract)
    again = await _load(graph, analytics, extract)
    assert (again.nodes_created, again.nodes_referenced) == (0, 3)
    found = await search_places(graph, analytics, PlaceSearchRequest(query="ood"), WITH_GAZETTEER)
    assert [p.name for p in found.places] == ["Hollywood"]
