"""The orchestrator's proof for v0.5.2 (14 November 2026): on local-lite, a batch expansion (ADR-151) runs to
done in the Conduit's own job loop, and its view opens. local-lite renders `OSPREY_JOB_WORKER=conduit` (no worker
image), so if the loop did not take `batch_expand` the panel would stay at "Waiting for the batch expansion to
start." for ever.

What it drives, end to end over HTTP, against a real Conduit process on a leased stack's ArcadeDB, Valkey and
Postgres (`test_statelessness.py`'s `_ConduitInstance`, the one `test_scheduler_lifespan.py`'s lite case uses):
a case made with its own dataset; two people and a link between them written to the Vault in it; the first
seeded onto the canvas; `POST …/batch-expansions` with the canvas's own `/expand` body for it; `GET …/{job}` every
two seconds, as the Glass's panel asks, until the job ends; and *Open the view*'s `GET …/views/{id}`.

A one-off proof, kept with the lane rather than in `tests/` (a file there joins `make test`'s offline run, whose
list of live files is the owner's Makefile). Run on the lane's stack, from OspreyFlow_Core:
`.venv/bin/pytest -c ../OspreyFlow_Build/pytest.ini -p tests.conftest -s \
../OspreyFlow_Build/process/lanes/case-b/batch-lite-live/test_batch_job_on_a_lite_conduit.py`
(`-p tests.conftest`: the suite's fixtures and its port guard, which a file outside `tests/` would not load).
"""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime

import httpx
from cryptography.hazmat.primitives.asymmetric import rsa
from tests.conftest import default_claims, sign_token
from tests.services.api.test_statelessness import _ConduitInstance, _seed_node

from adapters.graph_arcadedb.adapter import GraphArcadeDBAdapter
from adapters.graph_arcadedb.client import ArcadeDBClient, ArcadeDBConfig
from conduit_common.identity import new_edge_id, new_id
from ontology.handling import load_uk_le_scheme
from ontology.loader import load_default_ontology
from schemas.domain import EdgeWrite, Handling, NodeWrite, Provenance, ProvenanceState, SourceRef

HANDLING = Handling(
    classification="OFFICIAL", handling_code="P", originator="unit-1", owning_unit="unit-1"
)
SOURCE = SourceRef(document_id="fixture", locator="batch-lite", excerpt_hash="")


async def _two_people_linked(dataset_id: str) -> tuple[str, str]:
    now = datetime.now(UTC)
    client = ArcadeDBClient(ArcadeDBConfig.from_env(database="ospreyflow"))
    try:
        await client.create_database_if_absent()
        graph = GraphArcadeDBAdapter(client, load_uk_le_scheme())
        await graph.apply_schema(load_default_ontology())
        provenance = Provenance(state=ProvenanceState.ASSERTED, sources=[SOURCE], first_seen=now)
        people = [
            NodeWrite(
                id=new_id(), type="Person",
                properties={"family_name": f"Batchlite{new_id()[:6]}", "given_names": name},
                provenance=provenance, handling=HANDLING, created_by="test", created_at=now, datasets=[dataset_id],
            )
            for name in ("Ann", "Ben")
        ]  # fmt: skip
        tx = await graph.begin_transaction()
        ids = await graph.upsert_nodes(people, tx)
        await graph.upsert_edges(
            [EdgeWrite(id=new_edge_id(), type="ASSOCIATE_OF", source=ids[0], target=ids[1], provenance=provenance,
                       handling=HANDLING, created_by="test", created_at=now, datasets=[dataset_id])],
            tx,
        )  # fmt: skip
        await graph.commit_transaction(tx)
        return ids[0], ids[1]
    finally:
        await client.aclose()


def test_a_batch_job_runs_to_done_on_a_lite_conduit_and_its_view_opens(
    jwks_url: str, keypair: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]
) -> None:
    private_key, _ = keypair
    headers = {"Authorization": f"Bearer {sign_token(private_key, default_claims())}"}
    conduit = _ConduitInstance(jwks_url, extra_env={"OSPREY_JOB_WORKER": "conduit"})
    seen: list[str] = []
    try:
        api = conduit.base_url
        made = httpx.post(
            f"{api}/v1/investigations",
            headers=headers,
            json={"new_dataset_name": f"Batch lite {new_id()}"},
        )
        assert made.status_code == 201, made.text
        case = made.json()["id"]
        (own,) = httpx.get(f"{api}/v1/investigations/{case}/datasets", headers=headers).json()
        ann, ben = asyncio.run(_two_people_linked(own["id"]))
        seeded = httpx.post(f"{api}/v1/investigations/{case}/seed", headers=headers,
                            json={"nodes": [_seed_node(ann, own["id"])], "edges": []})  # fmt: skip
        assert seeded.status_code == 200, seeded.text

        # The canvas's own `/expand` body for the node, as the Glass's panel sends it.
        body = {"request": {"node_ids": [ann], "depth": 1, "edge_types": None}}
        started = httpx.post(
            f"{api}/v1/investigations/{case}/batch-expansions", headers=headers, json=body
        )
        print(f"POST batch-expansions: {started.status_code} {started.text}")
        assert started.status_code == 202, started.text
        job = started.json()
        began = time.monotonic()
        while job["state"] in ("queued", "running") and time.monotonic() - began < 120:
            line = f"{time.monotonic() - began:5.1f}s {job['state']}: {job['words']}"
            if not seen or seen[-1].split(" ", 1)[1] != line.split(" ", 1)[1]:
                seen.append(line)
                print(line)
            time.sleep(2)  # the panel's own interval (ADR-151)
            read = httpx.get(
                f"{api}/v1/investigations/{case}/batch-expansions/{job['id']}", headers=headers
            )
            assert read.status_code == 200, read.text
            job = read.json()
        print(
            f"{time.monotonic() - began:5.1f}s {job['state']}: {job['words']} (refusal: {job.get('refusal')})"
        )
        assert job["state"] == "done", f"the job ended {job['state']!r}, not done: {job}"
        assert job["view"] is not None, job

        # *Open the view*: the App's openLens, `GET …/views/{id}`.
        opened = httpx.get(
            f"{api}/v1/investigations/{case}/views/{job['view']['id']}", headers=headers
        )
        print(f"GET views/{job['view']['id']}: {opened.status_code}, view {opened.json()['view']['name']!r}, "
              f"nodes {sorted(n['id'] for n in opened.json()['nodes'])}, missing {opened.json()['missing']}")  # fmt: skip
        assert opened.status_code == 200, opened.text
        assert {n["id"] for n in opened.json()["nodes"]} == {ann, ben}
    finally:
        conduit.kill()
