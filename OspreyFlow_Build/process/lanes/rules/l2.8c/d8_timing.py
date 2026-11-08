"""D8 (L2.8c): the id path's timing. `AlertStore.get_authorized` by id, given the graph (so it settles
first), timed with no pending repoint record, with one, and with ten, each a record whose write has
not committed (its link live, so the settle reads the graph and leaves it). Run under the rules
lease on stack b; prints medians and quartiles in milliseconds."""

from __future__ import annotations

import asyncio
import json
import statistics
import sys
import time

from conduit_common.identity import new_edge_id, new_id, new_node_id
from schemas.domain import Alert, AlertMode, EdgeWrite, Handling, NodeWrite, Principal, Provenance, ProvenanceState, SourceRef
from services.api.alerts import AlertStore
from services.api.config import PostgresConfig
from tests.ingest.test_typology_rules import ONTOLOGY, SCHEME, T0, arcadedb_adapter

N = int(sys.argv[1]) if len(sys.argv) > 1 else 200
OWNER = Principal(id=f"d8-owner-{new_id()}", clearance="OFFICIAL", org_unit="verify")
OFFICIAL = Handling(classification="OFFICIAL", handling_code="P", originator="verify", owning_unit="verify")
PROV = Provenance(state=ProvenanceState.ASSERTED, first_seen=T0, sources=[SourceRef(document_id="t", locator="r", excerpt_hash="")])


async def timed(store: AlertStore, graph, alert_id: str) -> list[float]:
    for _ in range(10):  # warm
        await store.get_authorized(alert_id, OWNER, graph=graph)
    out = []
    for _ in range(N):
        t = time.perf_counter()
        await store.get_authorized(alert_id, OWNER, graph=graph)
        out.append((time.perf_counter() - t) * 1000)
    return out


def summary(name: str, xs: list[float]) -> str:
    q = statistics.quantiles(xs, n=4)
    return f"{name}: n={len(xs)} median={statistics.median(xs):.2f} ms q1={q[0]:.2f} q3={q[2]:.2f} max={max(xs):.2f}"


async def main() -> None:
    store = await AlertStore.connect(PostgresConfig.from_env().dsn)
    planted: list[str] = []
    try:
        async with arcadedb_adapter(ONTOLOGY, SCHEME) as graph:
            tx = await graph.begin_transaction()
            p, q = await graph.upsert_nodes([NodeWrite(id=new_node_id(), type="Person", properties={"family_name": f"D8 {i}"},
                                                       provenance=PROV, handling=OFFICIAL, created_by="t", created_at=T0) for i in "pq"], tx)
            (link,) = await graph.upsert_edges([EdgeWrite(id=new_edge_id(), type="ASSOCIATE_OF", source=p, target=q,
                                                          provenance=PROV, handling=OFFICIAL, created_by="t", created_at=T0)], tx)
            await graph.commit_transaction(tx)
            alert = Alert(id=new_id(), rule_id=f"typology:{new_id()}", owner_id=OWNER.id, mode=AlertMode.FULL,
                          referent_node_ids=[q], edge_ids=[link], investigation_id=f"case-{new_id()}", created_at=T0,
                          typology="structuring", words="D8", severity="medium")
            await store.save(alert, handlings=[OFFICIAL])
            async with store._pool.acquire() as conn:
                before = await conn.fetchval("SELECT count(*) FROM alert_repoint_records WHERE NOT applied")
            print(f"pending records in the table before planting: {before}")
            lines = [summary("no pending record", await timed(store, graph, alert.id))]
            for count in (1, 10):
                while len(planted) < count:
                    record = await store.open_record()
                    await store._add_to_record(record, links=[(link, new_edge_id(), "ASSOCIATE_OF")])
                    planted.append(record)
                lines.append(summary(f"{count} pending record(s), write not committed", await timed(store, graph, alert.id)))
            print("\n".join(lines))
    finally:
        async with store._pool.acquire() as conn:
            await conn.execute("DELETE FROM alert_repoint_records WHERE id = ANY($1::text[])", planted)
        await store.close()


asyncio.run(main())
