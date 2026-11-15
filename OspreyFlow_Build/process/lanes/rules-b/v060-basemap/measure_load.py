"""rules-b v060-basemap: the great-britain gazetteer as v0.6.0 item 10 loads it, measured against the
leased stack's ArcadeDB (a database of its own) and a scratch DuckDB for the points. Run from
OspreyFlow_Core with the lease's ports: `python measure_load.py load|count <extract> <scratch dir>`.

`load`: the load's time (one pass over the extract, the batches, the points), created, referenced
and rejected, the points written, and this process's peak memory. `count`: a second pass counting
every node, the named nodes and the settlements by kind (the owner's figure was about 900,000 named
points), run last and under a time cap. No key, password or port is printed."""

from __future__ import annotations

import asyncio
import resource
import sys
import time
from pathlib import Path

import scripts.build_local_basemap as script
from services.api.analytics_store import open_analytics
from services.ingest.connectors.geo.osm import SETTLEMENT_PLACES
from services.ingest.connectors.geo.osm_pbf import read_osm_pbf
from services.resolve.trigger import service_principal

from adapters.graph_arcadedb.adapter import GraphArcadeDBAdapter
from adapters.graph_arcadedb.client import ArcadeDBClient, ArcadeDBConfig
from ontology.handling import load_uk_le_scheme
from ontology.loader import load_default_ontology

DATABASE = "rulesb_basemap_measure"
DATASET = "gazetteer-osm-great-britain"


def peak_mb() -> int:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss // 1024  # Linux: kilobytes


def count(extract: Path) -> int:
    started = time.perf_counter()
    nodes = named = settlements = 0
    kinds: dict[str, int] = {}
    for node in read_osm_pbf(str(extract)):
        nodes += 1
        if node.tags.get("name"):
            named += 1
            place = node.tags.get("place")
            if place in SETTLEMENT_PLACES:
                settlements += 1
                kinds[place] = kinds.get(place, 0) + 1
    print(f"PASS over the extract: {time.perf_counter() - started:.0f} s; {nodes:,} nodes, "
          f"{named:,} named, {settlements:,} named settlements; peak {peak_mb():,} MB")  # fmt: skip
    print("SETTLEMENTS by kind: " + ", ".join(f"{k} {v:,}" for k, v in sorted(kinds.items())))
    return 0


async def load(extract: Path, scratch: Path) -> int:

    scheme = load_uk_le_scheme()
    client = ArcadeDBClient(ArcadeDBConfig.from_env(DATABASE))
    await client.create_database_if_absent()
    graph = GraphArcadeDBAdapter(client, scheme)
    ontology = load_default_ontology()
    await graph.apply_schema(ontology)
    analytics, close = await open_analytics(
        "duckdb", duckdb_path=str(scratch / "analytics.duckdb"), handling_scheme=scheme
    )
    principal = service_principal(scheme)
    try:
        started = time.perf_counter()
        report = await script.load_gazetteer(
            extract, graph=graph, ontology=ontology, principal=principal,
            load_id="load-osm-gazetteer-great-britain", dataset=DATASET, unit="unit-1",
            analytics=analytics,
        )  # fmt: skip
        print(f"LOAD: {time.perf_counter() - started:.0f} s; created {report.nodes_created:,}, "
              f"referenced {report.nodes_referenced:,}, rejected {len(report.rejections):,}; "
              f"batches of {script.GAZETTEER_BATCH:,}; peak {peak_mb():,} MB")  # fmt: skip
        points = analytics._con.execute("SELECT count(*) FROM geometries").fetchone()  # type: ignore[attr-defined]  # noqa: SLF001
        print(f"POINTS in the scratch analytics store: {points[0]:,}")
    finally:
        await close()
        await client.aclose()
    return 0


if __name__ == "__main__":
    if sys.argv[1] == "count":
        sys.exit(count(Path(sys.argv[2])))
    sys.exit(asyncio.run(load(Path(sys.argv[2]), Path(sys.argv[3]))))
