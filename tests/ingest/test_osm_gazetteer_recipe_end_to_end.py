"""The OSM gazetteer connector through the full ingest path: connector ->
recipe engine -> `GraphPort` -> (constructed the same way
`test_crs_reprojection.py` does, since the recipe engine does not write a
`GeometryRecord` itself yet — see that module's docstring for the stated
gap this shares) -> `AnalyticsPort`'s geometry reference partition.

`docs/00_ARCHITECTURE.md` §1.2's tier-1 gazetteer row.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from services.ingest.connectors.geo.osm import read_osm_places
from services.ingest.engine import run_recipe
from services.ingest.recipe_loader import load_recipe

from adapters.analytics_duckdb.testing import duckdb_adapter
from adapters.graph_arcadedb.testing import arcadedb_adapter
from knowledge_adapters.coordinates import geometry_reference, reproject_point
from ontology.handling import load_uk_le_scheme
from ontology.loader import load_default_ontology
from schemas.analytics import GeometryRecord
from schemas.domain import Handling, Principal
from tests.scenarios.fixtures.osm_extract import build_synthetic_osm_pbf

FIXTURES = Path(__file__).resolve().parents[1] / "scenarios" / "fixtures"

CLEARED = Principal(id="analyst-1", clearance="OFFICIAL", org_unit="unit-1")


async def test_osm_places_load_as_location_entities_with_a_resolvable_geometry(
    tmp_path: Path,
) -> None:
    pbf_path = tmp_path / "extract.osm.pbf"
    build_synthetic_osm_pbf(pbf_path)

    # The PBF format quantises lat/lon to a fixed granularity (real OSM
    # data is no different — `osm_pbf.py`'s own docstring). The float the
    # connector reconstructs from the delta-encoded integers is not
    # bit-identical to the literal fixture coordinate, so the expected
    # `geometry_ref` must be hashed from what the connector actually
    # emits, not from the original literal.
    [cranford_row] = [r for r in read_osm_places(str(pbf_path)) if r["name"] == "Cranford"]
    cranford_lon, cranford_lat = float(cranford_row["lon"]), float(cranford_row["lat"])

    recipe = load_recipe(FIXTURES / "osm_gazetteer_recipe.yaml")
    ontology = load_default_ontology()
    scheme = load_uk_le_scheme()

    async with arcadedb_adapter(ontology, scheme) as graph:
        tx = await graph.begin_transaction()
        report, _events = await run_recipe(
            recipe,
            read_osm_places(str(pbf_path)),
            graph=graph,
            ontology=ontology,
            tx=tx,
            principal=CLEARED,
            load_id="load-osm-gazetteer",
            investigation_scope="case-osm-fixture",
            source=str(pbf_path),
        )
        await graph.commit_transaction(tx)

        # Three named places — the unnamed OSM node was never a row at all.
        assert not report.rejections
        assert report.nodes_created == 3

        node = await graph.find_node("Location", "osm_id", "1", CLEARED)
        assert node is not None
        assert node.properties["name"] == "Cranford"

        expected_ref = geometry_reference("EPSG:4326", cranford_lon, cranford_lat)
        assert node.properties["geometry_ref"] == expected_ref

        # The recipe engine does not write `GeometryRecord`s itself yet
        # (the same stated gap `test_crs_reprojection.py` documents) — this
        # constructs and loads it the same way, proving the reference this
        # `Location` carries actually resolves to the right WGS84 point.
        lon, lat = reproject_point(cranford_lon, cranford_lat, source_crs="EPSG:4326")
        record = GeometryRecord(
            geometry_ref=expected_ref,
            version=1,
            lon=lon,
            lat=lat,
            source_crs="EPSG:4326",
            source_x=cranford_lon,
            source_y=cranford_lat,
            handling=Handling(
                classification="OFFICIAL", handling_code="P", owning_unit="unit-1",
                originator="unit-1",
            ),
        )
        async with duckdb_adapter([], scheme) as analytics:
            await analytics.load_geometries([record])
            stored = await analytics.get_geometry(expected_ref, CLEARED)
            assert stored is not None
            # WGS84 -> WGS84 is an identity reprojection, within pyproj's
            # own floating-point tolerance for a same-CRS pipeline.
            assert stored.lon == pytest.approx(stored.source_x, abs=1e-9)
            assert stored.lat == pytest.approx(stored.source_y, abs=1e-9)
