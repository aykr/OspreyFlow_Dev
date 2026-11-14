"""ADR-151 live: a batch expansion run by the real job worker, its consumer group on real Valkey,
over real ArcadeDB, saved in the real Postgres view store. This is the leak test the offline module's
fake graph can't be: the access filter here is the adapter's own, in the traversal (rule 3).

A person the requester may read is linked to one they may read and one held SECRET. The requester is
OFFICIAL, and the saved view holds the first two only. It goes red with the job expanding as no one
(`test_the_live_leak_check_fails_with_the_scope_dropped`). The case's level check is a stand-in
granting Editor; the route's real level check is the offline module's.

Run alone, under a lease (`stack_lease.sh`):
`cd OspreyFlow_Core && .venv/bin/pytest -c ../OspreyFlow_Build/pytest.ini \
../OspreyFlow_Build/tests/services/api/test_batch_expansion_live.py`.
"""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest
from services.api import batch_expansion, worker_main
from services.api.batch_expansion import JOB_TYPE_BATCH_EXPAND, BatchExpandBindings
from services.api.case_views import PostgresCaseViewStore
from services.api.config import PostgresConfig, ValkeyConfig
from services.api.datasets import Dataset, PostgresDatasetStore
from services.api.investigations import AccessLevel
from services.api.jobs import JobQueue
from services.api.worker import JobWorker
from valkey.asyncio import Valkey

from adapters.graph_arcadedb.adapter import GraphArcadeDBAdapter
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

UNIT = "unit-1"
OFFICIAL = Principal(id=f"bx-{uuid4().hex[:8]}", clearance="OFFICIAL", org_unit=UNIT,
                     roles=["analyst"])  # fmt: skip
SOURCE = SourceRef(document_id="files/batch.csv", locator="row 1", excerpt_hash="b" * 64)


class _Editor:
    """Grants Editor: the level check here is a stand-in, the route's own is offline."""

    async def get_authorized(
        self, investigation_id: str, principal: Principal, *, need: AccessLevel
    ) -> Any:
        return None


def _handling(classification: str) -> Handling:
    return Handling(classification=classification, handling_code="P", originator=UNIT,
                    owning_unit=UNIT)  # fmt: skip


def _node(dataset: str, classification: str = "OFFICIAL") -> NodeWrite:
    return NodeWrite(
        id=new_node_id(), type="Person", properties={"family_name": "Batch"},
        provenance=Provenance(state=ProvenanceState.ASSERTED, sources=[SOURCE], first_seen=now_utc()),
        handling=_handling(classification), created_by="loader", created_at=now_utc(),
        datasets=[dataset],
    )  # fmt: skip


def _edge(dataset: str, source: str, target: str) -> EdgeWrite:
    return EdgeWrite(
        id=new_edge_id(), type="ASSOCIATE_OF", source=source, target=target,
        provenance=Provenance(state=ProvenanceState.ASSERTED, sources=[SOURCE], first_seen=now_utc()),
        handling=_handling("OFFICIAL"), created_by="loader", created_at=now_utc(), datasets=[dataset],
    )  # fmt: skip


async def _run_one_batch() -> tuple[dict[str, str], list[str], float, dict[str, Any] | None]:
    """Writes the three people, queues one batch as OFFICIAL, and lets the real worker take it from
    the stream. Returns the ids by role, the saved view's selection, the seconds the job took and
    the job's outcome."""
    client = ArcadeDBClient(ArcadeDBConfig.from_env(database="ospreyflow"))
    await client.create_database_if_absent()
    graph = GraphArcadeDBAdapter(client, load_uk_le_scheme())
    await graph.apply_schema(load_default_ontology())
    dataset, case_id = f"bx-data-{uuid4().hex[:8]}", f"bx-case-{uuid4().hex[:8]}"
    seed, near, secret = _node(dataset), _node(dataset), _node(dataset, "SECRET")
    tx = await graph.begin_transaction()
    await graph.upsert_nodes([seed, near, secret], tx)
    await graph.upsert_edges(
        [_edge(dataset, seed.id, near.id), _edge(dataset, seed.id, secret.id)], tx
    )
    await graph.commit_transaction(tx)

    dsn = PostgresConfig.from_env().dsn
    datasets = await PostgresDatasetStore.connect(dsn)
    views = await PostgresCaseViewStore.connect(dsn)
    valkey = Valkey(**ValkeyConfig.from_env().client_kwargs())
    try:
        await datasets.add(Dataset(id=dataset, name=f"Batch {dataset}", owning_unit=UNIT,
                                   created_at=datetime.now(UTC), created_by="test"))  # fmt: skip
        await datasets.set_for_case(case_id, [dataset], OFFICIAL)
        jobs = JobQueue(valkey)
        worker = JobWorker(valkey, jobs, graph, consumer_name=f"bx-{uuid4().hex[:6]}")
        editor = _Editor()
        worker_main.register_all(
            worker, ontology=load_default_ontology(), scheme=load_uk_le_scheme(), valkey=valkey,
            analyst_layers=datasets.layer_ids, alerts=None, judgement_store=None,
            batch=BatchExpandBindings(views=views, investigations=lambda: editor, datasets=datasets,
                                      jobs=jobs, audit=None),
        )  # fmt: skip
        scoped = OFFICIAL.model_copy(update={"datasets": [dataset]})
        body = BatchExpansionInput(request=ExpandRequest(node_ids=[seed.id], depth=1))
        started = await batch_expansion.submit(jobs, valkey, case_id, scoped, body)
        began = time.monotonic()
        for _ in range(20):  # other lanes' entries may sit on the shared stream ahead of ours
            await worker.run_once(JOB_TYPE_BATCH_EXPAND, block_ms=500, count=10)
            record = await jobs.get_status(started.id)
            if record is not None and record.state in ("done", "failed"):
                break
        took = time.monotonic() - began
        record = await jobs.get_status(started.id)
        assert record is not None
        result = record.result
        chosen: list[str] = []
        if result and result.get("view_id"):
            view = await views.get(case_id, str(result["view_id"]), OFFICIAL.id)
            chosen = sorted(view.node_ids or [])
        return {"seed": seed.id, "near": near.id, "secret": secret.id}, chosen, took, result
    finally:
        await views.close()
        await datasets.close()
        await valkey.aclose()


def test_a_hidden_node_never_lands_in_the_batch_view_on_arcadedb() -> None:
    ids, chosen, took, result = asyncio.run(_run_one_batch())
    assert result is not None and result["outcome"] == "done", result
    assert chosen == sorted([ids["seed"], ids["near"]])
    assert ids["secret"] not in chosen
    assert (result["nodes"], result["links"]) == (2, 1)
    print(f"batch of 3 written, 2 visible: {took:.2f}s")


def test_the_live_leak_check_fails_with_the_scope_dropped(monkeypatch: pytest.MonkeyPatch) -> None:
    """Rule 15, live: the job expanding as SECRET with no case scope saves the SECRET node."""

    async def as_no_one(principal: Principal, *_: Any, **__: Any) -> Principal:
        return principal.model_copy(update={"datasets": None, "clearance": "SECRET"})

    monkeypatch.setattr(batch_expansion, "scope_to_case", as_no_one)
    ids, chosen, _, _ = asyncio.run(_run_one_batch())
    assert ids["secret"] in chosen
