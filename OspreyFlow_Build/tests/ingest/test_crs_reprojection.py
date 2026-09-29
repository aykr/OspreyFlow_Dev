"""CRS reprojection (`00_ARCHITECTURE.md` §1.2.2, ADR-017) through the full
ingest path: connector → recipe engine → Parquet staging → `GraphPort`.

`Location` carries `geometry_ref` only, never coordinates directly
(`03_CONDUIT_MIDDLEWARE.md` §5.1) — these tests check the node's
`geometry_ref` against what `geometry_reference()` independently computes
for the same source coordinate, and separately prove the matching
`GeometryRecord` round-trips through the analytics store's reference
partition via `AnalyticsPort.load_geometries`/`get_geometry` (Phase 5). The
recipe engine does not call that write path itself yet (the same stated
gap as `EventRecord` — see `services/ingest/__main__.py`), so each test
constructs and loads the record directly, the way a gazetteer connector's
write path will.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest
from services.ingest.connectors.csv_connector import read_csv
from services.ingest.engine import run_recipe
from services.ingest.recipe_loader import load_recipe

from adapters.analytics_duckdb.testing import duckdb_adapter
from adapters.graph_arcadedb.testing import arcadedb_adapter
from knowledge_adapters.coordinates import geometry_reference, reproject_point
from ontology.handling import load_uk_le_scheme
from ontology.loader import load_default_ontology
from schemas.analytics import GeometryRecord
from schemas.domain import Handling, Principal

FIXTURES = Path(__file__).resolve().parents[1] / "scenarios" / "fixtures"

CLEARED = Principal(id="analyst-1", clearance="OFFICIAL", org_unit="unit-1")


def _write_csv(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


async def test_british_national_grid_locations_carry_a_geometry_ref_not_coordinates(
    tmp_path: Path,
) -> None:
    from tests.scenarios.fixtures.geo_locations import generate_bng_rows

    rows = generate_bng_rows()
    csv_path = tmp_path / "bng.csv"
    _write_csv(csv_path, rows, ["place_id", "easting", "northing"])

    recipe = load_recipe(FIXTURES / "geo_bng_recipe.yaml")
    ontology = load_default_ontology()
    scheme = load_uk_le_scheme()

    async with arcadedb_adapter(ontology, scheme) as graph:
        tx = await graph.begin_transaction()
        report, _events = await run_recipe(
            recipe,
            read_csv(csv_path),
            graph=graph,
            ontology=ontology,
            tx=tx,
            principal=CLEARED,
            load_id="load-geo-bng",
            investigation_scope="case-geo-fixture",
            source=str(csv_path),
        )
        await graph.commit_transaction(tx)

        assert not report.rejections
        assert report.nodes_created == 3

        node = await graph.find_node("Location", "uprn", "uprn-100012345", CLEARED)
        assert node is not None
        assert set(node.properties) == {"uprn", "geometry_ref"}

        expected_ref = geometry_reference("EPSG:27700", 532106.0, 181020.0)
        assert node.properties["geometry_ref"] == expected_ref

        lon, lat = reproject_point(532106.0, 181020.0, source_crs="EPSG:27700")
        record = GeometryRecord(
            geometry_ref=expected_ref,
            version=1,
            lon=lon,
            lat=lat,
            source_crs="EPSG:27700",
            source_x=532106.0,
            source_y=181020.0,
            handling=Handling(
                classification="OFFICIAL", handling_code="P", owning_unit="unit-1",
                originator="unit-1",
            ),
        )
        async with duckdb_adapter([], scheme) as analytics:
            await analytics.load_geometries([record])
            stored = await analytics.get_geometry(expected_ref, CLEARED)
            assert stored is not None
            # Trafalgar Square, London — not merely "some longitude and latitude".
            assert stored.lon == pytest.approx(-0.0976, abs=1e-3)
            assert stored.lat == pytest.approx(51.5127, abs=1e-3)
            assert stored.source_x == pytest.approx(532106.0)
            assert stored.source_y == pytest.approx(181020.0)


async def test_texas_central_state_plane_locations_reproject_to_wgs84(tmp_path: Path) -> None:
    from tests.scenarios.fixtures.geo_locations import generate_texas_central_rows

    rows = generate_texas_central_rows()
    csv_path = tmp_path / "texas.csv"
    _write_csv(csv_path, rows, ["place_id", "easting", "northing"])

    recipe = load_recipe(FIXTURES / "geo_texas_central_recipe.yaml")
    ontology = load_default_ontology()
    scheme = load_uk_le_scheme()

    async with arcadedb_adapter(ontology, scheme) as graph:
        tx = await graph.begin_transaction()
        report, _events = await run_recipe(
            recipe,
            read_csv(csv_path),
            graph=graph,
            ontology=ontology,
            tx=tx,
            principal=CLEARED,
            load_id="load-geo-texas",
            investigation_scope="case-geo-fixture",
            source=str(csv_path),
        )
        await graph.commit_transaction(tx)

        assert not report.rejections
        assert report.nodes_created == 2

        node = await graph.find_node("Location", "gnis_feature_id", "gnis-1331235", CLEARED)
        assert node is not None
        expected_ref = geometry_reference("EPSG:32139", 949218.05, 3069475.07)
        assert node.properties["geometry_ref"] == expected_ref

        # Austin, TX — not California, not the UK.
        lon, lat = reproject_point(949218.05, 3069475.07, source_crs="EPSG:32139")
        assert lon == pytest.approx(-97.7431, abs=1e-3)
        assert lat == pytest.approx(30.2672, abs=1e-3)


async def test_california_zone_iii_state_plane_locations_reproject_to_wgs84(
    tmp_path: Path,
) -> None:
    from tests.scenarios.fixtures.geo_locations import generate_california_zone_iii_rows

    rows = generate_california_zone_iii_rows()
    csv_path = tmp_path / "california.csv"
    _write_csv(csv_path, rows, ["place_id", "easting", "northing"])

    recipe = load_recipe(FIXTURES / "geo_california_iii_recipe.yaml")
    ontology = load_default_ontology()
    scheme = load_uk_le_scheme()

    async with arcadedb_adapter(ontology, scheme) as graph:
        tx = await graph.begin_transaction()
        report, _events = await run_recipe(
            recipe,
            read_csv(csv_path),
            graph=graph,
            ontology=ontology,
            tx=tx,
            principal=CLEARED,
            load_id="load-geo-california",
            investigation_scope="case-geo-fixture",
            source=str(csv_path),
        )
        await graph.commit_transaction(tx)

        assert not report.rejections
        assert report.nodes_created == 2

        node = await graph.find_node("Location", "gnis_feature_id", "gnis-277411", CLEARED)
        assert node is not None
        expected_ref = geometry_reference("EPSG:2227", 6277390.19, 2399898.19)
        assert node.properties["geometry_ref"] == expected_ref

        # Sacramento, CA — the two US zones must not be interchangeable.
        lon, lat = reproject_point(6277390.19, 2399898.19, source_crs="EPSG:2227")
        assert lon == pytest.approx(-121.4944, abs=1e-3)
        assert lat == pytest.approx(38.5816, abs=1e-3)


async def test_a_bare_grid_reference_produces_the_same_geometry_ref_as_the_equivalent_pair(
    tmp_path: Path,
) -> None:
    """`grid_ref` and `geometry_ref` (fed an easting/northing pair) must
    agree on the same point — a UK source quoting `TQ 32106 81020` and one
    quoting `532106,181020` describe the same place and must resolve to
    the same reference, not two different geometry rows for one point."""
    from tests.scenarios.fixtures.geo_locations import generate_bng_grid_ref_rows

    rows = generate_bng_grid_ref_rows()
    csv_path = tmp_path / "grid_ref.csv"
    _write_csv(csv_path, rows, ["place_id", "grid_ref"])

    recipe = load_recipe(FIXTURES / "geo_grid_ref_recipe.yaml")
    ontology = load_default_ontology()
    scheme = load_uk_le_scheme()

    async with arcadedb_adapter(ontology, scheme) as graph:
        tx = await graph.begin_transaction()
        report, _events = await run_recipe(
            recipe,
            read_csv(csv_path),
            graph=graph,
            ontology=ontology,
            tx=tx,
            principal=CLEARED,
            load_id="load-geo-grid-ref",
            investigation_scope="case-geo-fixture",
            source=str(csv_path),
        )
        await graph.commit_transaction(tx)

        assert not report.rejections
        assert report.nodes_created == 3

        node = await graph.find_node("Location", "uprn", "uprn-100012345", CLEARED)
        assert node is not None
        assert node.properties["geometry_ref"] == geometry_reference(
            "EPSG:27700", 532106.0, 181020.0
        )


async def test_a_file_with_no_determinable_crs_is_rejected_not_guessed(tmp_path: Path) -> None:
    """`00_ARCHITECTURE.md` §1.2.2: "a file whose CRS cannot be determined
    from its metadata or a sidecar is rejected with a named error." Every
    row is rejected and counted; nothing is silently placed anywhere."""
    from tests.scenarios.fixtures.geo_locations import generate_bng_rows

    rows = generate_bng_rows()
    csv_path = tmp_path / "undeclared.csv"
    _write_csv(csv_path, rows, ["place_id", "easting", "northing"])

    recipe = load_recipe(FIXTURES / "geo_undeclared_crs_recipe.yaml")
    ontology = load_default_ontology()
    scheme = load_uk_le_scheme()

    async with arcadedb_adapter(ontology, scheme) as graph:
        tx = await graph.begin_transaction()
        report, _events = await run_recipe(
            recipe,
            read_csv(csv_path),
            graph=graph,
            ontology=ontology,
            tx=tx,
            principal=CLEARED,
            load_id="load-geo-undeclared",
            investigation_scope="case-geo-fixture",
            source=str(csv_path),
        )
        await graph.commit_transaction(tx)

        assert report.nodes_created == 0
        assert len(report.rejections) == len(rows)
        assert all("ambiguous coordinate reference system" in r.reason for r in report.rejections)
