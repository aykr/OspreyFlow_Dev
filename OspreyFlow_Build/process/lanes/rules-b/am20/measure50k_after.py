"""rules-b am20's rerun of the 50,000-node batch measurement, on ADR-124 Amendment 20's `edges_among`
(the orchestrator's gates, 14 November 2026): the same shape and setup as
`../v052batch-50k/measure50k.py`, which measured the query as built failing at 25,000 ids, so steps 4,
5 and 6 (the batch end to end, the saved view and its SECRET count) are measured now that it answers.
Step 1 is the curve of the shipped `edges_among`, each answer checked as exactly the fixture's link ids
among those ids, both ways; step 2 is the plan of one chunk's query at 1,000 record ids. The comparisons
of the first run (its step 3) are gone: B is now the product, A was refused.

The first run's docstring, for the shape:

The shape. 10 hubs, each linked to 4,999 OFFICIAL leaves and 50 SECRET leaves, all in one fresh
dataset. An OFFICIAL requester expanding the 10 hubs at depth 1 may read 10 + 49,990 = 50,000 nodes
(exactly the cap, which refuses only past it) and 49,990 links. The 500 SECRET leaves are the leak check
at scale: none may be in the saved view, and were they counted the result would be 50,500 and refused
`too_many_nodes`.

What is measured, run in the order 4, 5, 6, then 1, 2, 3, inside RUN_BUDGET for the whole run, each
step bounded at STEP_CAP seconds (or what is left) and said as hitting it if it does:
  1. `edges_among` as built, on its own, at 5,000, 10,000, 25,000 and 50,000 ids (the curve stops at
     the first step past its bound);
  2. ArcadeDB's plan for it at 5,000 ids (the same traversal with `.profile()`), kept raw;
  3. two read-only comparisons, in this script only: (A) the start resolved to record ids by SQL on the
     type's unique `id` index, as `get_nodes` does, and the far end tested against those record ids in
     the traversal; (B) the same start, the far end's access step in the traversal, and membership of
     the far end's id tested here. Each is called equal to the as-built query only when the two give
     exactly the same set of link ids at that size, checked both ways;
  4. the batch end to end at 50,000: submitted, taken from the stream by the real `JobWorker` on the
     stack's Valkey, under the ten-minute limit as shipped, each stage timed from the job's own
     progress words, and its outcome;
  5. `get_nodes` over the result, and the saved view row's stored size;
  6. the SECRET leaves absent from the saved view.
Every line is printed as it is taken (flushed). `uptime` and `free -g` at the start and the end.

Run from OspreyFlow_Core, under the lease, on the stack's own host:
  PYTHONPATH=.:packages .venv/bin/python -u <this> [--dry-run]
`--dry-run` sizes the setup and says what the run expects, connecting to nothing and writing nothing.
"""

from __future__ import annotations

import argparse
import asyncio
import functools
import subprocess
import sys
import time
from collections.abc import Awaitable
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

print = functools.partial(print, flush=True)  # noqa: A001 - every figure out as it is taken

HUBS = 10
LEAVES = 4_999
SECRET_PER_HUB = 50
CURVE = (5_000, 10_000, 25_000, 50_000)
STEP_CAP = 600.0
#: The whole run, the orchestrator's grant: a step that cannot finish inside what is left is skipped
#: and said so. The batch end to end runs first, straight after the setup, so it is never the one skipped.
RUN_BUDGET = 45 * 60.0
RUN_STARTED = time.monotonic()
WRITE_CAP = 900.0
NODE_CHUNK = 2_000
#: Rates recorded by rules' v052-load on the same server (B_RECORD.md): nodes by upsert, links in bulk.
NODES_PER_S = 255
LINKS_PER_S = 640


def _shape() -> dict[str, int]:
    official = HUBS * LEAVES
    secret = HUBS * SECRET_PER_HUB
    return {
        "hubs": HUBS,
        "official_leaves": official,
        "secret_leaves": secret,
        "nodes_written": HUBS + official + secret,
        "links_written": official + secret,
        "result_nodes": HUBS + official,
        "result_links": official,
    }


def _host(label: str) -> None:
    for cmd in (["uptime"], ["free", "-g"]):
        try:
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=10).stdout.strip()
        except (OSError, subprocess.TimeoutExpired) as exc:
            out = f"({type(exc).__name__})"
        print(f"[{label}] {' '.join(cmd)}: {out}")


def dry_run() -> None:
    s = _shape()
    print("DRY RUN: nothing is connected to and nothing is written.")
    for key, value in s.items():
        print(f"  {key}: {value:,}")
    print(f"  the cap: {50_000:,} nodes; the result sits on it: {s['result_nodes'] == 50_000}")
    print(f"  SECRET leaves the leak check expects absent from the saved view: {s['secret_leaves']:,}")
    est_nodes = s["nodes_written"] / NODES_PER_S
    est_links = s["links_written"] / LINKS_PER_S
    print(f"  setup estimate at v052-load's rates: nodes {est_nodes:.0f} s, links {est_links:.0f} s,"
          f" total {(est_nodes + est_links) / 60:.1f} min (bounded at {WRITE_CAP / 60:.0f} min)")  # fmt: skip
    print(f"  the whole run is bounded at {RUN_BUDGET / 60:.0f} min: the setup, then the batch end to"
          " end, then the curve, the profile and the comparisons while time is left")  # fmt: skip
    ids = [f"{'x' * 26}" for _ in range(50_000)]
    print(f"  edges_among's script at 50,000 ids carries them twice: about "
          f"{2 * sum(len(i) + 3 for i in ids) / 1e6:.1f} MB of text")  # fmt: skip


async def _bounded(label: str, work: Awaitable[Any]) -> tuple[Any, float | None]:
    t = time.monotonic()
    cap = min(STEP_CAP, RUN_BUDGET - (t - RUN_STARTED))
    if cap < 30:
        print(f"{label}: skipped, {max(cap, 0):.0f} s left of the run's {RUN_BUDGET / 60:.0f} min")
        if asyncio.iscoroutine(work):
            work.close()
        return None, None
    try:
        result = await asyncio.wait_for(work, cap)
    except TimeoutError:
        print(f"{label}: past its bound of {cap:.0f} s, stopped")
        return None, None
    except Exception as exc:  # noqa: BLE001 - what failed is the figure, said so
        print(f"{label}: FAILED after {time.monotonic() - t:.1f} s: {type(exc).__name__}: "
              f"{str(exc)[:300]}")  # fmt: skip
        return None, None
    took = time.monotonic() - t
    print(f"{label}: {took:.1f} s")
    return result, took


async def run() -> int:
    from services.api import batch_expansion, worker_main
    from services.api.batch_expansion import JOB_TYPE_BATCH_EXPAND, BatchExpandBindings
    from services.api.case_views import PostgresCaseViewStore
    from services.api.config import PostgresConfig, ValkeyConfig
    from services.api.datasets import Dataset, PostgresDatasetStore
    from services.api.jobs import JobQueue
    from services.api.worker import JobWorker
    from valkey.asyncio import Valkey

    from adapters.graph_arcadedb.adapter import GraphArcadeDBAdapter
    from adapters.graph_arcadedb.builders import render_edges_among_gremlin
    from adapters.graph_arcadedb.client import ArcadeDBClient, ArcadeDBConfig
    from conduit_common.identity import new_edge_id, new_node_id, now_utc
    from ontology.handling import load_uk_le_scheme
    from ontology.loader import load_default_ontology
    from schemas.batch_expansion import BatchExpansionInput
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

    _host("start")
    print(f"started {datetime.now(UTC):%Y-%m-%dT%H:%M:%SZ}")
    shape = _shape()
    source = SourceRef(document_id="files/measure50k.csv", locator="row 1", excerpt_hash="5" * 64)

    def handling(classification: str) -> Handling:
        return Handling(classification=classification, handling_code="P", originator="unit-1",
                        owning_unit="unit-1")  # fmt: skip

    def prov() -> Provenance:
        return Provenance(state=ProvenanceState.ASSERTED, sources=[source], first_seen=now_utc())

    dataset = f"m50k-{uuid4().hex[:8]}"
    case_id = f"m50k-case-{uuid4().hex[:8]}"

    def node(classification: str) -> NodeWrite:
        return NodeWrite(id=new_node_id(), type="Person", properties={"family_name": "M"},
                         provenance=prov(), handling=handling(classification), created_by="m50k",
                         created_at=now_utc(), datasets=[dataset])  # fmt: skip

    client = ArcadeDBClient(ArcadeDBConfig.from_env(database="ospreyflow"))
    await client.create_database_if_absent()
    graph = GraphArcadeDBAdapter(client, load_uk_le_scheme())
    await graph.apply_schema(load_default_ontology())

    # --- setup -----------------------------------------------------------------------------
    hubs = [node("OFFICIAL") for _ in range(HUBS)]
    leaves = {h.id: [node("OFFICIAL") for _ in range(LEAVES)] for h in hubs}
    secrets = {h.id: [node("SECRET") for _ in range(SECRET_PER_HUB)] for h in hubs}
    nodes = [*hubs, *(n for ls in leaves.values() for n in ls), *(n for ss in secrets.values() for n in ss)]
    links = [
        EdgeWrite(id=new_edge_id(), type="ASSOCIATE_OF", source=h, target=leaf.id, provenance=prov(),
                  handling=handling("OFFICIAL"), created_by="m50k", created_at=now_utc(),
                  datasets=[dataset])  # fmt: skip
        for h, ls in ({**leaves}).items()
        for leaf in [*ls, *secrets[h]]
    ]
    assert len(nodes) == shape["nodes_written"] and len(links) == shape["links_written"]
    began = time.monotonic()
    written = 0
    for start in range(0, len(nodes), NODE_CHUNK):
        if time.monotonic() - began > WRITE_CAP:
            print(f"node writes stopped at their bound: {written:,} of {len(nodes):,}")
            break
        tx = await graph.begin_transaction()
        await graph.upsert_nodes(nodes[start : start + NODE_CHUNK], tx)
        await graph.commit_transaction(tx)
        written += len(nodes[start : start + NODE_CHUNK])
        if (start // NODE_CHUNK) % 5 == 0:
            print(f"  nodes: {written:,} written at {time.monotonic() - began:.0f} s")
    print(f"nodes written: {written:,} in {time.monotonic() - began:.1f} s")
    if written < len(nodes):
        print("not the planned shape: stopping before the measurements, which would not be of it")
        _host("end")
        return 2
    t = time.monotonic()
    await graph.bulk_load_edges(
        links, progress=lambda d, n: print(f"  links: {d:,} of {n:,} at {time.monotonic() - t:.0f} s")
        if d % 10_000 < 500 else None,
    )  # fmt: skip
    print(f"links written (bulk): {len(links):,} in {time.monotonic() - t:.1f} s")

    reader = Principal(id="m50k-reader", clearance="OFFICIAL", org_unit="unit-1",
                       roles=["analyst"], datasets=[dataset])  # fmt: skip
    visible = [h.id for h in hubs] + [n.id for ls in leaves.values() for n in ls]
    secret_ids = {n.id for ss in secrets.values() for n in ss}
    assert len(visible) == shape["result_nodes"]

    # --- 4. the batch end to end -------------------------------------------------------------
    dsn = PostgresConfig.from_env().dsn
    datasets = await PostgresDatasetStore.connect(dsn)
    views = await PostgresCaseViewStore.connect(dsn)
    valkey = Valkey(**ValkeyConfig.from_env().client_kwargs())

    class _Editor:
        async def get_authorized(self, *_: Any, **__: Any) -> None:
            return None

    editor = _Editor()
    try:
        await datasets.add(Dataset(id=dataset, name=f"Measure {dataset}", owning_unit="unit-1",
                                   created_at=datetime.now(UTC), created_by="m50k"))  # fmt: skip
        await datasets.set_for_case(case_id, [dataset], reader)
        jobs = JobQueue(valkey)
        worker = JobWorker(valkey, jobs, graph, consumer_name=f"m50k-{uuid4().hex[:6]}")
        worker_main.register_all(
            worker, ontology=load_default_ontology(), scheme=load_uk_le_scheme(), valkey=valkey,
            analyst_layers=datasets.layer_ids, alerts=None, judgement_store=None,
            batch=BatchExpandBindings(views=views, investigations=lambda: editor, datasets=datasets,
                                      jobs=jobs, audit=None),
        )  # fmt: skip
        body = BatchExpansionInput(request=ExpandRequest(node_ids=[h.id for h in hubs], depth=1))
        started = await batch_expansion.submit(jobs, valkey, case_id, reader, body)
        t0 = time.monotonic()

        async def watch() -> None:
            last = None
            while True:
                rec = await jobs.get_status(started.id)
                now = (rec.state, rec.progress) if rec else None
                if now != last:
                    print(f"  job at {time.monotonic() - t0:.1f} s: {now}")
                    last = now
                if rec and rec.state in ("done", "failed"):
                    return
                await asyncio.sleep(0.5)

        watching = asyncio.create_task(watch())
        while not watching.done() and time.monotonic() - t0 < batch_expansion.TIME_LIMIT_SECONDS + 120:
            await worker.run_once(JOB_TYPE_BATCH_EXPAND, block_ms=1_000, count=10)
        await asyncio.wait_for(watching, 30)
        rec = await jobs.get_status(started.id)
        assert rec is not None
        print(f"batch end to end: {time.monotonic() - t0:.1f} s, state {rec.state}, result {rec.result}")

        # --- 5 and 6. the saved view -----------------------------------------------------------
        if rec.result and rec.result.get("view_id"):
            view = await views.get(case_id, str(rec.result["view_id"]), reader.id)
            chosen = set(view.node_ids or [])
            print(f"saved view: {len(chosen):,} chosen; SECRET leaves in it: {len(chosen & secret_ids)}"
                  f" of {len(secret_ids):,} (expected 0)")  # fmt: skip
            async with views._pool.acquire() as conn:  # noqa: SLF001
                size = await conn.fetchval(
                    "SELECT pg_column_size(lens) FROM case_views WHERE id = $1", view.id
                )
            print(f"the view row's lens column: {size:,} bytes stored")
            got, _ = await _bounded(f"get_nodes over {len(chosen):,}", graph.get_nodes(sorted(chosen), reader))
            if got is not None:
                print(f"  {len(got):,} nodes")
            await views.delete(case_id, view.id, reader.id)
    finally:
        await views.close()
        await datasets.close()
        await valkey.aclose()
    # --- 1. edges_among (ADR-124 Amendment 20), its curve, each set exact -------------------
    written_links = [(e.id, e.source, e.target) for e in links]
    shown = set(visible)
    for size in CURVE:
        asked = set(visible[:size])
        expected = {i for i, s, t in written_links if s in asked and t in asked and t in shown}
        found, took = await _bounded(f"edges_among at {size:,} ids",
                                     graph.edges_among(visible[:size], reader))  # fmt: skip
        if found is None:
            print("the curve stops here")
            break
        got = [e.id for e in found]
        print(f"  {len(got):,} links; exactly the fixture's: {set(got) == expected} "
              f"(only here {len(set(got) - expected)}, only expected {len(expected - set(got))}, "
              f"twice {len(got) - len(set(got))})")

    # --- 2. one chunk's plan, at 1,000 record ids ------------------------------------------
    access = graph._access  # noqa: SLF001 - the adapter's own access step, read, not changed
    types = await graph._types_with_unique_id("vertex")  # noqa: SLF001
    rids = await graph._record_ids(types, sorted(visible)[:1_000])  # noqa: SLF001
    query = render_edges_among_gremlin(rids, access, reader)
    plan, _ = await _bounded("one chunk's profile at 1,000 record ids",
                             client.gremlin(query + ".profile()"))  # fmt: skip
    print(f"PROFILE (raw): {plan!r}"[:20_000])

    print(f"ended {datetime.now(UTC):%Y-%m-%dT%H:%M:%SZ}")
    _host("end")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    if parser.parse_args().dry_run:
        dry_run()
        return 0
    return asyncio.run(run())


if __name__ == "__main__":
    sys.exit(main())
