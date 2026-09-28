"""The site-grid connector through the full ingest path: connector ->
recipe engine -> `GraphPort` -> `AnalyticsPort`'s geometry reference
partition — the same shape `test_osm_gazetteer_recipe_end_to_end.py` proves
for the OSM connector, and the same stated gap that test's docstring
records (the recipe engine does not write a `GeometryRecord` itself yet).

`docs/00_ARCHITECTURE.md` §1.2's site-plan row, `08_ACCEPTANCE_SCENARIOS.md`
A1.
"""

from __future__ import annotations

#: Round 13cdc: the site-grid recipe moved out of `tests/` into `recipes/`, because
#: `services/api/app.py` loads it at runtime and the Conduit's image does not ship `tests/`.
#: Imported from one place so this suite and the route cannot come to test different recipes.
from pathlib import Path

import pytest
from services.api.app import _SITE_GRID_RECIPE_PATH as SITE_GRID_RECIPE
from services.ingest.connectors.geo.site_grid import site_grid_rows
from services.ingest.engine import run_recipe
from services.ingest.recipe_loader import load_recipe

from adapters.analytics_duckdb.testing import duckdb_adapter
from adapters.graph_arcadedb.testing import arcadedb_adapter
from geo.bilinear import ControlPoint
from knowledge_adapters.coordinates import geometry_reference, reproject_point
from ontology.handling import load_uk_le_scheme
from ontology.loader import load_default_ontology
from schemas.analytics import GeometryRecord
from schemas.domain import Handling, Principal

FIXTURES = Path(__file__).resolve().parents[1] / "scenarios" / "fixtures"

CLEARED = Principal(id="analyst-1", clearance="OFFICIAL", org_unit="unit-1")

# A small, roughly HMP-Hollywood-shaped square — real-looking WGS84
# coordinates rather than the unit-test square in
# tests/ingest/test_site_grid_connector.py, since this test also proves
# reprojection through `AnalyticsPort`.
_CONTROL_POINTS = (
    ControlPoint(px=0, py=0, lon=-1.8360, lat=52.4090),
    ControlPoint(px=1000, py=0, lon=-1.8340, lat=52.4090),
    ControlPoint(px=1000, py=1000, lon=-1.8340, lat=52.4080),
    ControlPoint(px=0, py=1000, lon=-1.8360, lat=52.4080),
)


async def test_site_grid_cells_load_as_location_entities_with_a_resolvable_geometry() -> None:
    rows = list(
        site_grid_rows(site_id="site-hmp-1", control_points=_CONTROL_POINTS, rows=2, cols=2)
    )
    top_left_row = next(r for r in rows if r["site_ref"] == "site-hmp-1-r0-c0")
    cell_lon, cell_lat = float(top_left_row["lon"]), float(top_left_row["lat"])

    recipe = load_recipe(SITE_GRID_RECIPE)
    ontology = load_default_ontology()
    scheme = load_uk_le_scheme()

    async with arcadedb_adapter(ontology, scheme) as graph:
        tx = await graph.begin_transaction()
        report, _events = await run_recipe(
            recipe,
            rows,
            graph=graph,
            ontology=ontology,
            tx=tx,
            principal=CLEARED,
            load_id="load-site-grid",
            investigation_scope="case-site-fixture",
            source="site-hmp-1",
        )
        await graph.commit_transaction(tx)

        assert not report.rejections
        assert report.nodes_created == 4

        node = await graph.find_node("Location", "site_ref", "site-hmp-1-r0-c0", CLEARED)
        assert node is not None
        assert node.properties["name"] == "Grid cell (0, 0)"

        expected_ref = geometry_reference("EPSG:4326", cell_lon, cell_lat)
        assert node.properties["geometry_ref"] == expected_ref

        lon, lat = reproject_point(cell_lon, cell_lat, source_crs="EPSG:4326")
        record = GeometryRecord(
            geometry_ref=expected_ref,
            version=1,
            lon=lon,
            lat=lat,
            source_crs="EPSG:4326",
            source_x=cell_lon,
            source_y=cell_lat,
            handling=Handling(
                classification="OFFICIAL", handling_code="P", owning_unit="unit-1",
                originator="unit-1",
            ),
        )
        async with duckdb_adapter([], scheme) as analytics:
            await analytics.load_geometries([record])
            stored = await analytics.get_geometry(expected_ref, CLEARED)
            assert stored is not None
            assert stored.lon == pytest.approx(stored.source_x, abs=1e-9)
            assert stored.lat == pytest.approx(stored.source_y, abs=1e-9)


async def test_redrawing_the_same_grid_is_idempotent_not_duplicating_cells() -> None:
    """`match_on: site_ref` + `on_match: reference` — an analyst
    re-confirming the same grid (or the route being retried) must not
    create a second `Location` per cell."""
    rows = list(
        site_grid_rows(site_id="site-hmp-2", control_points=_CONTROL_POINTS, rows=2, cols=2)
    )
    recipe = load_recipe(SITE_GRID_RECIPE)
    ontology = load_default_ontology()
    scheme = load_uk_le_scheme()

    async with arcadedb_adapter(ontology, scheme) as graph:
        for load_id in ("load-a", "load-b"):
            tx = await graph.begin_transaction()
            report, _events = await run_recipe(
                recipe,
                rows,
                graph=graph,
                ontology=ontology,
                tx=tx,
                principal=CLEARED,
                load_id=load_id,
                investigation_scope="case-site-fixture",
                source="site-hmp-2",
            )
            await graph.commit_transaction(tx)
            assert not report.rejections

        # `site_ref` is one of `Location`'s declared `identifiers`
        # (`packages/ontology/default.yaml`), so an exact-match search on
        # its value is the way to check for duplicates — `name` is not an
        # identifier field and would not be searchable this way.
        matches = await graph.search_nodes("site-hmp-2-r0-c0", CLEARED, limit=20)
        assert len(matches) == 1
