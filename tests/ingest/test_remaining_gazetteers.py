"""The seven remaining UK/US gazetteer connectors — `docs/07_BUILD_PLAN.md`
Phase 5 Checkpoint 3c. Mirrors `test_crs_reprojection.py`'s exact shape
(connector → recipe engine → `GraphPort`, `geometry_ref` checked against
`geometry_reference()` computed independently) rather than `osm.py`'s own
two-test-file split — none of these seven sources needed a bespoke
connector module (`services/ingest/connectors/csv_connector.read_csv`
already covers all of them, confirmed by reading its configurable
`delimiter` parameter), so there is no connector-specific parsing logic
to isolate-test separately from the recipe end-to-end path.
"""

from __future__ import annotations

import csv
from pathlib import Path

from services.ingest.connectors.csv_connector import read_csv
from services.ingest.engine import run_recipe
from services.ingest.recipe_loader import load_recipe

from adapters.graph_arcadedb.testing import arcadedb_adapter
from knowledge_adapters.coordinates import geometry_reference
from ontology.handling import load_uk_le_scheme
from ontology.loader import load_default_ontology
from schemas.domain import Principal

FIXTURES = Path(__file__).resolve().parents[1] / "scenarios" / "fixtures"

CLEARED = Principal(id="analyst-1", clearance="OFFICIAL", org_unit="unit-1")


def _write_csv(
    path: Path, rows: list[dict[str, str]], fieldnames: list[str], *, delimiter: str = ","
) -> None:
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter=delimiter)
        writer.writeheader()
        writer.writerows(rows)


async def test_os_open_names_locations_carry_a_geometry_ref(tmp_path: Path) -> None:
    from tests.scenarios.fixtures.gazetteer_sources import generate_os_open_names_rows

    rows = generate_os_open_names_rows()
    csv_path = tmp_path / "os_open_names.csv"
    _write_csv(csv_path, rows, ["ID", "NAME1", "GEOMETRY_X", "GEOMETRY_Y"])

    recipe = load_recipe(FIXTURES / "os_open_names_recipe.yaml")
    ontology = load_default_ontology()
    scheme = load_uk_le_scheme()

    async with arcadedb_adapter(ontology, scheme) as graph:
        tx = await graph.begin_transaction()
        report, _events = await run_recipe(
            recipe, read_csv(csv_path), graph=graph, ontology=ontology, tx=tx,
            principal=CLEARED, load_id="load-os-open-names",
            investigation_scope="case-geo-fixture", source=str(csv_path),
        )
        await graph.commit_transaction(tx)

        assert not report.rejections
        assert report.nodes_created == 3

        node = await graph.find_node("Location", "os_place_id", "osgb4000000074219665", CLEARED)
        assert node is not None
        assert node.properties["name"] == "Trafalgar Square"
        expected_ref = geometry_reference("EPSG:27700", 532106.0, 181020.0)
        assert node.properties["geometry_ref"] == expected_ref


async def test_open_uprn_locations_carry_a_geometry_ref(tmp_path: Path) -> None:
    from tests.scenarios.fixtures.gazetteer_sources import generate_open_uprn_rows

    rows = generate_open_uprn_rows()
    csv_path = tmp_path / "open_uprn.csv"
    _write_csv(csv_path, rows, ["UPRN", "LATITUDE", "LONGITUDE"])

    recipe = load_recipe(FIXTURES / "open_uprn_recipe.yaml")
    ontology = load_default_ontology()
    scheme = load_uk_le_scheme()

    async with arcadedb_adapter(ontology, scheme) as graph:
        tx = await graph.begin_transaction()
        report, _events = await run_recipe(
            recipe, read_csv(csv_path), graph=graph, ontology=ontology, tx=tx,
            principal=CLEARED, load_id="load-open-uprn",
            investigation_scope="case-geo-fixture", source=str(csv_path),
        )
        await graph.commit_transaction(tx)

        assert not report.rejections
        assert report.nodes_created == 3

        node = await graph.find_node("Location", "uprn", "100012345", CLEARED)
        assert node is not None
        expected_ref = geometry_reference("EPSG:4326", -0.0877, 51.5079)
        assert node.properties["geometry_ref"] == expected_ref


async def test_code_point_open_locations_carry_a_geometry_ref(tmp_path: Path) -> None:
    from tests.scenarios.fixtures.gazetteer_sources import generate_code_point_open_rows

    rows = generate_code_point_open_rows()
    csv_path = tmp_path / "code_point_open.csv"
    _write_csv(csv_path, rows, ["Postcode", "Eastings", "Northings"])

    recipe = load_recipe(FIXTURES / "code_point_open_recipe.yaml")
    ontology = load_default_ontology()
    scheme = load_uk_le_scheme()

    async with arcadedb_adapter(ontology, scheme) as graph:
        tx = await graph.begin_transaction()
        report, _events = await run_recipe(
            recipe, read_csv(csv_path), graph=graph, ontology=ontology, tx=tx,
            principal=CLEARED, load_id="load-code-point-open",
            investigation_scope="case-geo-fixture", source=str(csv_path),
        )
        await graph.commit_transaction(tx)

        assert not report.rejections
        assert report.nodes_created == 3

        node = await graph.find_node("Location", "postcode", "WC2N 5DN", CLEARED)
        assert node is not None
        expected_ref = geometry_reference("EPSG:27700", 532106.0, 181020.0)
        assert node.properties["geometry_ref"] == expected_ref


async def test_boundary_line_locations_carry_no_geometry_ref(tmp_path: Path) -> None:
    """The one gazetteer here with no single point —
    `packages/ontology/default.yaml`'s own stated allowance."""
    from tests.scenarios.fixtures.gazetteer_sources import generate_boundary_line_rows

    rows = generate_boundary_line_rows()
    csv_path = tmp_path / "boundary_line.csv"
    _write_csv(csv_path, rows, ["GSS_CODE", "NAME", "AREA_TYPE"])

    recipe = load_recipe(FIXTURES / "boundary_line_recipe.yaml")
    ontology = load_default_ontology()
    scheme = load_uk_le_scheme()

    async with arcadedb_adapter(ontology, scheme) as graph:
        tx = await graph.begin_transaction()
        report, _events = await run_recipe(
            recipe, read_csv(csv_path), graph=graph, ontology=ontology, tx=tx,
            principal=CLEARED, load_id="load-boundary-line",
            investigation_scope="case-geo-fixture", source=str(csv_path),
        )
        await graph.commit_transaction(tx)

        assert not report.rejections
        assert report.nodes_created == 3

        node = await graph.find_node("Location", "gss_code", "E09000033", CLEARED)
        assert node is not None
        assert node.properties == {"gss_code": "E09000033", "name": "Westminster"}


async def test_usgs_gnis_locations_carry_a_geometry_ref(tmp_path: Path) -> None:
    from tests.scenarios.fixtures.gazetteer_sources import generate_usgs_gnis_rows

    rows = generate_usgs_gnis_rows()
    csv_path = tmp_path / "usgs_gnis.csv"
    _write_csv(
        csv_path, rows,
        ["FEATURE_ID", "FEATURE_NAME", "FEATURE_CLASS", "STATE_ALPHA", "COUNTY_NAME",
         "PRIM_LAT_DEC", "PRIM_LONG_DEC"],
        delimiter="|",
    )

    recipe = load_recipe(FIXTURES / "usgs_gnis_recipe.yaml")
    ontology = load_default_ontology()
    scheme = load_uk_le_scheme()

    async with arcadedb_adapter(ontology, scheme) as graph:
        tx = await graph.begin_transaction()
        report, _events = await run_recipe(
            recipe, read_csv(csv_path, delimiter="|"), graph=graph, ontology=ontology, tx=tx,
            principal=CLEARED, load_id="load-usgs-gnis",
            investigation_scope="case-geo-fixture", source=str(csv_path),
        )
        await graph.commit_transaction(tx)

        assert not report.rejections
        assert report.nodes_created == 2

        node = await graph.find_node("Location", "gnis_feature_id", "1331235", CLEARED)
        assert node is not None
        assert node.properties["name"] == "Texas State Capitol"
        expected_ref = geometry_reference("EPSG:4326", -97.740370, 30.274670)
        assert node.properties["geometry_ref"] == expected_ref


async def test_tiger_line_locations_carry_a_representative_point(tmp_path: Path) -> None:
    """A road segment's `geometry_ref` here is a pre-computed midpoint, not
    real address-range interpolation — see this recipe's own header
    comment on why that's a stated simplification, not a silent one."""
    from tests.scenarios.fixtures.gazetteer_sources import generate_tiger_line_rows

    rows = generate_tiger_line_rows()
    csv_path = tmp_path / "tiger_line.csv"
    _write_csv(
        csv_path, rows,
        ["TLID", "FULLNAME", "LFROMHN", "LTOHN", "RFROMHN", "RTOHN", "MID_LAT", "MID_LON"],
    )

    recipe = load_recipe(FIXTURES / "tiger_line_recipe.yaml")
    ontology = load_default_ontology()
    scheme = load_uk_le_scheme()

    async with arcadedb_adapter(ontology, scheme) as graph:
        tx = await graph.begin_transaction()
        report, _events = await run_recipe(
            recipe, read_csv(csv_path), graph=graph, ontology=ontology, tx=tx,
            principal=CLEARED, load_id="load-tiger-line",
            investigation_scope="case-geo-fixture", source=str(csv_path),
        )
        await graph.commit_transaction(tx)

        assert not report.rejections
        assert report.nodes_created == 2

        node = await graph.find_node("Location", "tiger_geoid", "110435556789", CLEARED)
        assert node is not None
        assert node.properties["name"] == "Congress Ave"
        expected_ref = geometry_reference("EPSG:4326", -97.743500, 30.267500)
        assert node.properties["geometry_ref"] == expected_ref


async def test_nad_locations_carry_a_geometry_ref(tmp_path: Path) -> None:
    """National Address Database coverage is voluntary and uneven per
    `docs/07_BUILD_PLAN.md`'s own caveat — a property of the real data,
    not something this recipe/connector handles specially."""
    from tests.scenarios.fixtures.gazetteer_sources import generate_nad_rows

    rows = generate_nad_rows()
    csv_path = tmp_path / "nad.csv"
    _write_csv(
        csv_path, rows,
        ["NAD_ADDRESS_ID", "StreetAddress", "City", "State", "Zip", "Latitude", "Longitude"],
    )

    recipe = load_recipe(FIXTURES / "nad_recipe.yaml")
    ontology = load_default_ontology()
    scheme = load_uk_le_scheme()

    async with arcadedb_adapter(ontology, scheme) as graph:
        tx = await graph.begin_transaction()
        report, _events = await run_recipe(
            recipe, read_csv(csv_path), graph=graph, ontology=ontology, tx=tx,
            principal=CLEARED, load_id="load-nad",
            investigation_scope="case-geo-fixture", source=str(csv_path),
        )
        await graph.commit_transaction(tx)

        assert not report.rejections
        assert report.nodes_created == 2

        node = await graph.find_node("Location", "nad_address_id", "CA-SAC-0001", CLEARED)
        assert node is not None
        assert node.properties["name"] == "1315 10th St"
        expected_ref = geometry_reference("EPSG:4326", -121.493400, 38.576600)
        assert node.properties["geometry_ref"] == expected_ref
