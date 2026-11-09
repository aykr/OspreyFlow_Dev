"""*Admin › Maps*' build (`services/api/map_admin.build_basemap`, `06_DECISIONS.md` ADR-147 decision
3) against a live `GraphPort`, on a small synthetic region: the real OSM gazetteer loaded from a
synthetic extract (`tests/scenarios/fixtures/osm_extract.py`, never downloaded: rule 9) in one graph
transaction, committed when the build finishes, and rolled back when it fails after the load.
planetiler's own run is stood in (no jar on a CI runner, and no Java in the Conduit's image while
the owner rules on its licence). Live, so under `tests/ingest` beside
`test_build_local_basemap_end_to_end.py`, run under a test-stack lease."""

from __future__ import annotations

from pathlib import Path

import pytest
from scripts.build_local_basemap import load_gazetteer
from services.api.map_admin import (
    PLANETILER_JAR,
    InMemoryMapAdminAudit,
    MapAdmin,
    MapKeyFile,
    MapSettingsFile,
    build_basemap,
)

from adapters.graph_arcadedb.testing import arcadedb_adapter
from ontology.handling import load_uk_le_scheme
from ontology.loader import load_default_ontology
from schemas.domain import Principal
from schemas.mapconfig import MapConfig
from tests.scenarios.fixtures.osm_extract import build_synthetic_osm_pbf

CLEARED = Principal(id="analyst-1", clearance="OFFICIAL", org_unit="unit-1")
OSM = {
    "id": "osm-local", "label": "OSM", "kind": "vector", "source": "file:///data/tiles/gb.pmtiles",
    "attribution": "© OSM contributors",
    "licence": {"id": "ODbL-1.0", "redistributable": True, "client_scope": "open"},
}  # fmt: skip


def _admin(tmp_path: Path) -> MapAdmin:
    tiles = tmp_path / "tiles"
    (tiles / PLANETILER_JAR).parent.mkdir(parents=True)
    (tiles / PLANETILER_JAR).write_bytes(b"PK synthetic jar")
    return MapAdmin(
        installed=MapConfig.model_validate({"default": "osm-local", "providers": [OSM]}),
        settings_file=MapSettingsFile(tmp_path / "maps"), key_file=MapKeyFile(tmp_path / "maps"),
        audit=InMemoryMapAdminAudit(), tiles_root=tiles, java=lambda _name: "/usr/bin/java",
    )  # fmt: skip


def _downloader(region: str, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    build_synthetic_osm_pbf(dest)
    return dest


@pytest.mark.parametrize("planetiler_fails", [False, True], ids=["finished", "failed-after-load"])
async def test_the_build_loads_the_real_gazetteer_and_commits_only_a_finished_build(
    tmp_path: Path, planetiler_fails: bool
) -> None:
    admin = _admin(tmp_path)
    ontology = load_default_ontology()
    async with arcadedb_adapter(ontology, load_uk_le_scheme()) as graph:
        transactions: list[str] = []

        async def load_places(extract: Path) -> tuple[int, int, int]:
            tx = await graph.begin_transaction()
            transactions.append(tx)
            report = await load_gazetteer(
                extract, graph=graph, ontology=ontology, tx=tx, principal=CLEARED,
                load_id="load-osm-gazetteer-rutland",
            )  # fmt: skip
            return report.nodes_created, report.nodes_referenced, len(report.rejections)

        def planetiler(extract: Path, output: Path, *, jar_path: Path) -> Path:
            output.write_bytes(b"PMTiles\x03 synthetic")
            return output

        async def build() -> tuple[str, int, int, int]:
            # As the route does: the places loaded in one transaction, committed after the build.
            result = await build_basemap(
                admin, by="admin-1", region="rutland", load_places=load_places,
                downloader=_downloader, planetiler_runner=planetiler,
                tiles_root=admin.tiles_root,
            )  # fmt: skip
            if planetiler_fails:
                raise RuntimeError("the build stopped after the places were loaded")
            return result

        try:
            name, created, _referenced, rejected = await build()
        except RuntimeError:
            await graph.rollback_transaction(transactions[0])
            assert await graph.find_node("Location", "osm_id", "1", CLEARED) is None
            return
        await graph.commit_transaction(transactions[0])

        assert (name, created, rejected) == ("rutland.pmtiles", 3, 0)
        node = await graph.find_node("Location", "osm_id", "1", CLEARED)
        assert node is not None and node.properties["name"] == "Cranford"
        assert admin.provider("osm-local-rutland").source == "file:///data/tiles/built/rutland.pmtiles"
