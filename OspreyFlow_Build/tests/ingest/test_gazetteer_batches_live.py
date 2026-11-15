"""v0.6.0 item 10, live: the gazetteer loaded a batch to a transaction (`GAZETTEER_BATCH`) against a
real ArcadeDB. Every settlement is found after a load that spans several batches; a second load finds
each one already held (`on_match: reference` reads what the earlier batches committed); and a named
point that is not a settlement is never written (the owner's ruling, 15 November 2026). Live, so under
`tests/ingest`, run under a test-stack lease."""

from __future__ import annotations

from pathlib import Path

import pytest
import scripts.build_local_basemap as script
from adapters.graph_arcadedb.testing import arcadedb_adapter
from ontology.handling import load_uk_le_scheme
from ontology.loader import load_default_ontology
from schemas.domain import Principal

from tests.scenarios.fixtures.osm_extract import build_synthetic_osm_pbf

READER = Principal(id="analyst-1", clearance="OFFICIAL", org_unit="unit-1",
                   datasets=["gazetteer-osm-rutland"])  # fmt: skip
SETTLEMENTS = [(f"Settlement {i}", "place", ("village", "hamlet", "town")[i % 3], 52.6 + i / 100,
                -0.7) for i in range(12)]  # fmt: skip
NOT_ONE = [("The Anchor", "amenity", "cafe", 52.65, -0.72), ("Hill Farm", "place", "farm", 52.7, -0.7)]


async def test_a_load_over_several_batches_finds_every_settlement_and_a_rebuild_finds_them_held(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    extract = tmp_path / "rutland.osm.pbf"
    build_synthetic_osm_pbf(extract, places=SETTLEMENTS + NOT_ONE)
    monkeypatch.setattr(script, "GAZETTEER_BATCH", 5)  # 12 settlements: batches of 5, 5 and 2
    ontology = load_default_ontology()
    async with arcadedb_adapter(ontology, load_uk_le_scheme()) as graph:

        async def load() -> tuple[int, int, int]:
            report = await script.load_gazetteer(
                extract, graph=graph, ontology=ontology, principal=READER,
                load_id="load-osm-gazetteer-rutland", dataset="gazetteer-osm-rutland",
            )  # fmt: skip
            return report.nodes_created, report.nodes_referenced, len(report.rejections)

        assert await load() == (12, 0, 0)
        for osm_id in range(1, 13):
            assert await graph.find_node("Location", "osm_id", str(osm_id), READER) is not None
        for osm_id in (13, 14):  # the cafe and the farm
            assert await graph.find_node("Location", "osm_id", str(osm_id), READER) is None
        assert await load() == (0, 12, 0)
