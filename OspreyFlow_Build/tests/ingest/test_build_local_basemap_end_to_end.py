"""`scripts/build_local_basemap.py`'s full orchestration against a live
`GraphPort` — `spec/00_ARCHITECTURE.md` §1.2. Split out from
`tests/test_build_local_basemap.py`'s pure unit
tests (`download_extract`/`run_planetiler`/`register_local_provider` need
no live store) precisely so that file can stay outside `make test`'s
`--ignore=tests/ingest` boundary while this one, needing ArcadeDB, sits
inside it — the same boundary `test_crs_reprojection.py` and
`test_recipe_engine_end_to_end.py` already respect.
"""

from __future__ import annotations

from pathlib import Path

from scripts.build_local_basemap import build_local_basemap
from services.api.mapconfig_loader import load_map_config

from adapters.graph_arcadedb.testing import arcadedb_adapter
from ontology.handling import load_uk_le_scheme
from ontology.loader import load_default_ontology
from schemas.domain import Principal
from tests.scenarios.fixtures.osm_extract import build_synthetic_osm_pbf

CLEARED = Principal(id="analyst-1", clearance="OFFICIAL", org_unit="unit-1")


async def test_build_local_basemap_loads_the_gazetteer_and_registers_the_provider(
    tmp_path: Path,
) -> None:
    def fake_downloader(region: str, dest: Path) -> Path:
        build_synthetic_osm_pbf(dest)
        return dest

    def fake_planetiler(osm_path: Path, output_path: Path, *, jar_path: Path) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"fake-pmtiles")
        return output_path

    ontology = load_default_ontology()
    scheme = load_uk_le_scheme()
    output_dir = tmp_path / "tiles"
    config_path = tmp_path / "osprey.yaml"

    async with arcadedb_adapter(ontology, scheme) as graph:
        tx = await graph.begin_transaction()
        result = await build_local_basemap(
            region="great-britain",
            output_dir=output_dir,
            planetiler_jar_path=tmp_path / "unused.jar",
            osprey_config_path=config_path,
            graph=graph,
            ontology=ontology,
            tx=tx,
            principal=CLEARED,
            progress=lambda _msg: None,
            downloader=fake_downloader,
            planetiler_runner=fake_planetiler,
        )
        await graph.commit_transaction(tx)

        assert result.gazetteer_report.nodes_created == 3
        assert result.pmtiles_path.read_bytes() == b"fake-pmtiles"

        node = await graph.find_node("Location", "osm_id", "1", CLEARED)
        assert node is not None
        assert node.properties["name"] == "Cranford"

    config = load_map_config(config_path)
    assert config.default == "osm-local-great-britain"
