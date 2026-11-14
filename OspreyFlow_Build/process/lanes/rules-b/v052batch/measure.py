"""rules-b v052batch's measurement under the lease (ADR-151 Cost; case's asks of 14 November 2026):
how long the reads at a view's cap take on real ArcadeDB and Postgres, so the ten-minute bound and
the 50,000 selection are set from figures.

One seed linked to N-1 neighbours, all OFFICIAL in one dataset, written in chunks. Then timed:
`expand` from the seed (what the job reads), `edges_among` over the whole result (what the job and
`open_view` count), `get_nodes` over it (what `open_view` reads), and the Postgres view row saved and
read back with N ids. Writes stop at five minutes and measure at the size reached, so the lease's
ten minutes hold. Run from OspreyFlow_Core under the lease: `python <this> [N]`."""

import asyncio
import sys
import time
from datetime import UTC, datetime
from uuid import uuid4

from services.api.batch_expansion import BatchViewInput
from services.api.case_views import PostgresCaseViewStore
from services.api.config import PostgresConfig

from adapters.graph_arcadedb.adapter import GraphArcadeDBAdapter
from adapters.graph_arcadedb.client import ArcadeDBClient, ArcadeDBConfig
from conduit_common.identity import new_edge_id, new_node_id, now_utc
from ontology.handling import load_uk_le_scheme
from ontology.loader import load_default_ontology
from schemas.domain import (
    EdgeWrite,
    ExpandRequest,
    Handling,
    NodeWrite,
    Principal,
    Provenance,
    ProvenanceState,
    SourceRef,
)

N = int(sys.argv[1]) if len(sys.argv) > 1 else 50_000
CHUNK = 2_000
WRITE_BUDGET = 300.0
SOURCE = SourceRef(document_id="files/measure.csv", locator="row 1", excerpt_hash="m" * 64)
HANDLING = Handling(classification="OFFICIAL", handling_code="P", originator="unit-1",
                    owning_unit="unit-1")  # fmt: skip


def _prov() -> Provenance:
    return Provenance(state=ProvenanceState.ASSERTED, sources=[SOURCE], first_seen=now_utc())


async def main() -> None:
    client = ArcadeDBClient(ArcadeDBConfig.from_env(database="ospreyflow"))
    await client.create_database_if_absent()
    graph = GraphArcadeDBAdapter(client, load_uk_le_scheme())
    await graph.apply_schema(load_default_ontology())
    dataset = f"measure-{uuid4().hex[:8]}"
    seed = NodeWrite(id=new_node_id(), type="Person", properties={"family_name": "Hub"},
                     provenance=_prov(), handling=HANDLING, created_by="measure",
                     created_at=now_utc(), datasets=[dataset])  # fmt: skip
    began, written = time.monotonic(), 1
    tx = await graph.begin_transaction()
    await graph.upsert_nodes([seed], tx)
    await graph.commit_transaction(tx)
    while written < N and time.monotonic() - began < WRITE_BUDGET:
        size = min(CHUNK, N - written)
        nodes = [seed.model_copy(update={"id": new_node_id(), "properties": {"family_name": "Leaf"}})
                 for _ in range(size)]  # fmt: skip
        edges = [EdgeWrite(id=new_edge_id(), type="ASSOCIATE_OF", source=seed.id, target=n.id,
                           provenance=_prov(), handling=HANDLING, created_by="measure",
                           created_at=now_utc(), datasets=[dataset]) for n in nodes]  # fmt: skip
        tx = await graph.begin_transaction()
        await graph.upsert_nodes(nodes, tx)
        await graph.upsert_edges(edges, tx)
        await graph.commit_transaction(tx)
        written += size
    print(f"written: {written:,} nodes and {written - 1:,} links in {time.monotonic() - began:.1f}s")

    reader = Principal(id="measure", clearance="OFFICIAL", org_unit="unit-1", roles=["analyst"],
                       datasets=[dataset])  # fmt: skip

    async def timed(label: str, coro):  # type: ignore[no-untyped-def]
        t = time.monotonic()
        try:
            result = await coro
        except Exception as exc:  # noqa: BLE001 - the measurement is what failed, said so
            print(f"{label}: FAILED after {time.monotonic() - t:.1f}s: {type(exc).__name__}")
            return None
        print(f"{label}: {time.monotonic() - t:.1f}s")
        return result

    found = await timed("expand from the seed", graph.expand(ExpandRequest(node_ids=[seed.id]), reader))
    ids = [n.id for n in found.nodes] if found else []
    print(f"expand found {len(ids):,} nodes, {len(found.edges) if found else 0:,} links")
    if ids:
        links = await timed(f"edges_among {len(ids):,} ids", graph.edges_among(ids, reader))
        print(f"edges_among found {len(links or []):,} links")
        nodes = await timed(f"get_nodes {len(ids):,} ids", graph.get_nodes(ids, reader))
        print(f"get_nodes found {len(nodes or []):,} nodes")
        views = await PostgresCaseViewStore.connect(PostgresConfig.from_env().dsn)
        try:
            lens = BatchViewInput(name="Measured", node_ids=ids)
            view = await timed("view row saved", views.save(f"measure-{dataset}", lens, "measure"))
            if view is not None:
                await timed("view row read", views.get(view.case_id, view.id, "measure"))
                async with views._pool.acquire() as conn:  # noqa: SLF001
                    size = await conn.fetchval(
                        "SELECT pg_column_size(lens) FROM case_views WHERE id = $1", view.id
                    )
                print(f"view row's lens column: {size:,} bytes stored")
                await views.delete(view.case_id, view.id, "measure")
        finally:
            await views.close()
    print(f"at {datetime.now(UTC):%H:%M:%S} UTC")


asyncio.run(main())
