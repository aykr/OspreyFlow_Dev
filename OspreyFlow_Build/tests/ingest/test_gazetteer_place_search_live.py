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
from services.api.map_places import SCAN_LIMIT, gazetteer_dataset_id, search_places
from services.ingest.geometries import POINT_GEOMETRY_VERSION

from adapters.analytics_duckdb.adapter import AnalyticsDuckDBAdapter
from adapters.analytics_duckdb.schema import create_events_table, create_geometries_table
from adapters.graph_arcadedb.adapter import GraphArcadeDBAdapter
from adapters.graph_arcadedb.testing import arcadedb_adapter
from ontology.handling import load_uk_le_scheme
from ontology.loader import load_default_ontology
from schemas.analytics import GeometryKind, GeometryRecord
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


async def _plant(
    graph: GraphArcadeDBAdapter, analytics: AnalyticsDuckDBAdapter, *, node_id: str, name: str,
    dataset: str, classification: str, lon: float, lat: float, point_classification: str = "",
    **props: str,
) -> None:  # fmt: skip
    """One `Location` with a point of its own, written as a load writes it; the point marked as the
    place unless `point_classification` says otherwise."""
    handling = {
        "classification": classification, "handling_code": "P",
        "originator": "unit-1", "owning_unit": "unit-1",
    }  # fmt: skip
    point_handling = {**handling, "classification": point_classification or classification}
    ref = f"g-{node_id}"
    tx = await graph.begin_transaction()
    await graph.upsert_nodes(
        [
            NodeWrite(
                id=node_id, type="Location",
                properties={"name": name, "geometry_ref": ref, **props},
                provenance=Provenance(
                    state=ProvenanceState.ASSERTED,
                    sources=[SourceRef(document_id=dataset, locator="1", excerpt_hash="a" * 64)],
                    first_seen=datetime(2026, 1, 1, tzinfo=UTC),
                ),
                handling=handling,  # type: ignore[arg-type]
                created_by="analyst-1", created_at=datetime(2026, 1, 1, tzinfo=UTC),
                datasets=[dataset],
            )
        ],
        tx,
    )  # fmt: skip
    await graph.commit_transaction(tx)
    await analytics.load_geometries(
        [
            GeometryRecord(
                geometry_ref=ref, version=POINT_GEOMETRY_VERSION, kind=GeometryKind.POINT,
                lon=lon, lat=lat, handling=point_handling,  # type: ignore[arg-type]
            )
        ]
    )  # fmt: skip


async def _a_case_yard(graph: GraphArcadeDBAdapter, analytics: AnalyticsDuckDBAdapter) -> None:
    """A case's own place, named like the gazetteer's, **with a point** and a postcode, in the
    case's own dataset: only the `gazetteer-*` filter keeps it from being offered."""
    await _plant(
        graph, analytics, node_id="yard-cranford-3", name="Cranford yard 3", dataset="case-a",
        classification="OFFICIAL", lon=-0.46, lat=51.49, site_ref="yard-3", postcode="TW5 9QQ",
    )  # fmt: skip


async def _a_secret_place(graph: GraphArcadeDBAdapter, analytics: AnalyticsDuckDBAdapter) -> None:
    """A gazetteer place above an OFFICIAL reader's clearance, **its point OFFICIAL**: the analytics
    store would hand the point over, so only the graph store's own access step keeps the place out
    (rule 15: a test that the point's marking alone could pass proves nothing about the store)."""
    await _plant(
        graph, analytics, node_id="secret-cranford-depot", name="Cranford Depot",
        dataset=GAZETTEER, classification="SECRET", point_classification="OFFICIAL",
        lon=-0.47, lat=51.48, osm_id="secret-9",
    )  # fmt: skip


async def test_a_case_that_added_the_gazetteer_finds_its_place_and_one_that_did_not_finds_nothing(
    stores: Stores,
) -> None:
    graph, analytics, extract = stores
    report = await _load(graph, analytics, extract)
    assert (report.nodes_created, len(report.rejections)) == (3, 0)
    await _a_case_yard(graph, analytics)
    await _a_secret_place(graph, analytics)

    found = await search_places(graph, analytics, PlaceSearchRequest(query="cranf"), WITH_GAZETTEER)
    # Not the case's yard (it has a point, but is the case's), not the SECRET depot (rule 3).
    assert [(p.name, round(p.lat, 4), round(p.lon, 4)) for p in found.places] == [
        ("Cranford", 51.488, -0.459)
    ]
    assert found.more is False
    # Even with room for one place only, `more` does not say a hidden place matched.
    one = await search_places(
        graph, analytics, PlaceSearchRequest(query="cranf", limit=1), WITH_GAZETTEER
    )
    assert [p.name for p in one.places] == ["Cranford"] and one.more is False
    # The depot is there to be found: a reader cleared for it finds it.
    cleared = WITH_GAZETTEER.model_copy(update={"clearance": "SECRET"})
    seen = await search_places(graph, analytics, PlaceSearchRequest(query="cranf"), cleared)
    assert [p.name for p in seen.places] == ["Cranford", "Cranford Depot"]

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


async def test_an_identifier_fragment_finds_no_place_and_no_more(stores: Stores) -> None:
    """Rule 7 at the store (the independent review): the places are asked by name alone, so the
    gazetteer's identifiers (`osm_id` "1", "2", "3" in the synthetic extract, and a planted one)
    match nothing, in the places or in `more`."""
    graph, analytics, extract = stores
    await _load(graph, analytics, extract)
    await _plant(
        graph, analytics, node_id="ident-place", name="Ashwell", dataset=GAZETTEER,
        classification="OFFICIAL", lon=-0.7, lat=52.7, osm_id="osm-77441", uprn="100077441",
    )  # fmt: skip
    # More places than one scan reads whose identifiers, not names, hold the fragment: a store asked
    # on identifiers would fill its scan with them and say `more` (rule 15: with one such place the
    # name check alone would pass this case).
    tx = await graph.begin_transaction()
    await graph.upsert_nodes(
        [
            NodeWrite(
                id=f"ident-many-{i}", type="Location",
                properties={"name": f"Hamlet {i}", "osm_id": f"osm-77441-{i}",
                            "geometry_ref": f"g-many-{i}"},
                provenance=Provenance(
                    state=ProvenanceState.ASSERTED,
                    sources=[SourceRef(document_id="osm", locator=str(i), excerpt_hash="a" * 64)],
                    first_seen=datetime(2026, 1, 1, tzinfo=UTC),
                ),
                handling={  # type: ignore[arg-type]
                    "classification": "OFFICIAL", "handling_code": "P",
                    "originator": "unit-1", "owning_unit": "unit-1",
                },
                created_by="loader", created_at=datetime(2026, 1, 1, tzinfo=UTC),
                datasets=[GAZETTEER],
            )
            for i in range(SCAN_LIMIT + 5)
        ],
        tx,
    )  # fmt: skip
    await graph.commit_transaction(tx)
    for fragment in ("77441", "osm-77", "10007"):
        answer = await search_places(
            graph, analytics, PlaceSearchRequest(query=fragment), WITH_GAZETTEER
        )
        assert answer.places == [] and answer.more is False, fragment
