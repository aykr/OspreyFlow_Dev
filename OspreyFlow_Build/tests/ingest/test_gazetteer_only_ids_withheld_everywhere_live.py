"""ADR-147 Amendment 3 (CARRIES row 23, the strict reading), through the real routes over real
ArcadeDB: a gazetteer loaded through the Studio arrives in a case's own dataset as a plain file,
unmarked, so the six identifiers only a gazetteer carries (`GAZETTEER_ONLY_IDENTIFIERS`) are
withheld from every node for every request reader, and no node is matched on one, whatever dataset
it is in. A `uprn`, a case's own identifier (Amendment 1 point 3a), is kept and still matched.

A `Location` carrying an `osm_id`, an `os_place_id` and a `uprn` is planted in a case's own source
dataset (no `gazetteer-*` dataset, no gazetteer provenance), with twelve more whose `osm_id`s share
its prefix, more than a type-ahead page. The case searches and suggests by the `osm_id` and finds
nothing, with no `more`; it finds the place by its name and by its `uprn`; no answer carries the
`osm_id` or the `os_place_id`, and the `uprn` is sent. Shown red at the adapter with Amendment 3's
read and match reverted to Amendment 1's (`plants.md`).

Runs the real `services.api.app` over ArcadeDB, Postgres and Valkey on a leased test stack, as
`test_gazetteer_ids_withheld_live.py` does. Everything it writes is removed in teardown, pass or
fail: the nodes by id, its case (the delete checked), and in Postgres this run's dataset, the case's
layers and the rows naming them.
"""

from __future__ import annotations

import asyncio
import os
import secrets
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from services.api.config import PostgresConfig
from services.api.datasets import Dataset, PostgresDatasetStore

from adapters.graph_arcadedb.adapter import GraphArcadeDBAdapter
from adapters.graph_arcadedb.client import ArcadeDBClient, ArcadeDBConfig
from conduit_common.identity import new_node_id, now_utc
from ontology.handling import load_uk_le_scheme
from ontology.loader import load_default_ontology
from schemas.domain import Handling, NodeWrite, Principal, Provenance, ProvenanceState, SourceRef
from tests.conftest import default_claims, sign_token
from tests.services.api.case_dataset import new_case

UNIT = Principal(id="loader-1", clearance="OFFICIAL", org_unit="unit-1", roles=["analyst"])
#: This run's own names, identifiers and dataset, so a search finds this run's place alone and its
#: teardown removes this run's rows alone.
TAG = f"{secrets.randbelow(10**8):08d}"
OWN = f"case-own-am3-live-{TAG}"
NAME = f"Wrexbury {TAG}"
OSM_ID = f"7{TAG}"
OS_PLACE_ID = f"osgb{TAG}"
UPRN = f"9{TAG}"
PLANTED: list[str] = []


@pytest.fixture
def api_env(jwks_url: str) -> Iterator[None]:
    keys = ("OIDC_JWKS_URL", "OIDC_ALGORITHMS", "ARCADEDB_DATABASE")
    previous = {key: os.environ.get(key) for key in keys}
    os.environ.update(
        {"OIDC_JWKS_URL": jwks_url, "OIDC_ALGORITHMS": "RS256", "ARCADEDB_DATABASE": "ospreyflow"}
    )
    try:
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


async def _graph() -> tuple[ArcadeDBClient, GraphArcadeDBAdapter]:
    client = ArcadeDBClient(ArcadeDBConfig.from_env(database="ospreyflow"))
    await client.create_database_if_absent()
    graph = GraphArcadeDBAdapter(client, load_uk_le_scheme())
    await graph.apply_schema(load_default_ontology())
    return client, graph


async def _plant() -> str:
    """The case's own place, as a Studio load of a gazetteer file writes it, and twelve alike."""
    client, graph = await _graph()
    handling = Handling(
        classification="OFFICIAL", handling_code="P", originator="unit-1", owning_unit="unit-1"
    )
    provenance = Provenance(
        state=ProvenanceState.ASSERTED,
        sources=[SourceRef(document_id="studio-load", locator="1", excerpt_hash="f" * 64)],
        first_seen=now_utc(),
    )
    place = NodeWrite(
        id=new_node_id(), type="Location",
        properties={"name": NAME, "osm_id": OSM_ID, "os_place_id": OS_PLACE_ID, "uprn": UPRN},
        provenance=provenance, handling=handling, created_by="loader-1", created_at=now_utc(),
        datasets=[OWN],
    )  # fmt: skip
    alike = [
        place.model_copy(
            update={
                "id": new_node_id(),
                "properties": {"name": f"Otherwhere {i}", "osm_id": f"{OSM_ID}{i:02d}"},
            }
        )
        for i in range(12)
    ]
    # Every id recorded before anything is written: teardown removes what a part-way failure left.
    PLANTED.extend([place.id, *(n.id for n in alike)])
    tx = await graph.begin_transaction()
    await graph.upsert_nodes([place, *alike], tx)
    await graph.commit_transaction(tx)
    await client.aclose()
    return place.id


async def _remove(ids: list[str]) -> None:
    if not ids:
        return
    client, _graph_adapter = await _graph()
    try:
        quoted = ",".join(f"'{i}'" for i in ids)
        await client.gremlin(f"g.V().has('id',within({quoted})).drop()")
        left = await client.gremlin(f"g.V().has('id',within({quoted})).values('id')")
        assert left == [], f"left behind in the shared database: {left}"
    finally:
        await client.aclose()


async def _give_case(investigation_id: str) -> None:
    """The case reads this run's own source dataset alone: no gazetteer anywhere."""
    store = await PostgresDatasetStore.connect(PostgresConfig.from_env().dsn)
    try:
        await store.register(
            Dataset(
                id=OWN, name=f"Studio load (Amendment 3 live test {TAG})",
                owning_unit=UNIT.org_unit, created_at=datetime(2026, 11, 10, tzinfo=UTC),
                created_by="test",
            )
        )  # fmt: skip
        await store.set_for_case(investigation_id, [OWN], UNIT)
    finally:
        await store.close()


async def _remove_rows(case_ids: list[str]) -> None:
    import asyncpg

    connection = await asyncpg.connect(PostgresConfig.from_env().dsn)
    try:
        layers = [
            r["id"]
            for r in await connection.fetch(
                "SELECT id FROM datasets WHERE layer_of = ANY($1::text[])", case_ids
            )
        ]
        await connection.execute(
            "DELETE FROM investigation_datasets WHERE investigation_id = ANY($1::text[])", case_ids
        )
        await connection.execute(
            "DELETE FROM case_layer_reads WHERE investigation_id = ANY($1::text[])", case_ids
        )
        await connection.execute("DELETE FROM datasets WHERE id = ANY($1::text[])", [*layers, OWN])
        left = await connection.fetchval(
            "SELECT count(*) FROM datasets WHERE id = ANY($1::text[])", [*layers, OWN]
        )
        assert left == 0, f"{left} dataset row(s) of this run were not removed"
    finally:
        await connection.close()


def test_a_case_s_own_place_is_sent_and_found_without_a_gazetteer_only_identifier(
    api_env: None, keypair: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]
) -> None:
    private_key, _ = keypair
    headers = {"Authorization": f"Bearer {sign_token(private_key, default_claims())}"}
    PLANTED.clear()
    cases: list[str] = []

    from services.api.app import app

    try:
        place_id = _run(_plant())
        with TestClient(app) as client:
            made = client.post("/v1/investigations", headers=headers, json=new_case())
            case_id = made.json()["id"]
            cases.append(case_id)
            _run(_give_case(case_id))
            search = f"/v1/investigations/{case_id}/search"
            suggest = f"/v1/investigations/{case_id}/suggest"

            # Found by no identifier only a gazetteer carries: neither the exact search nor the
            # type-ahead on its prefix, which says no `more` though twelve places share it.
            for query in (OSM_ID, OS_PLACE_ID):
                by_id = client.post(search, headers=headers, json={"query": query})
                assert by_id.status_code == 200 and by_id.json()["nodes"] == [], by_id.text
            for body in (
                {"query": OSM_ID},
                {"query": OSM_ID, "mode": "contains", "ignore_case": True},
            ):
                hinted = client.post(suggest, headers=headers, json=body)
                assert hinted.status_code == 200, hinted.text
                assert hinted.json()["nodes"] == [] and hinted.json()["more"] is False, body

            # Found by its name and by its `uprn`, a case's own; sent with the `uprn` alone.
            for query in (NAME, UPRN):
                found = client.post(search, headers=headers, json={"query": query})
                assert found.status_code == 200, found.text
                assert [n["id"] for n in found.json()["nodes"]] == [place_id], (query, found.text)
                sent = found.json()["nodes"][0]["properties"]
                assert sent.get("uprn") == UPRN, sent
                assert "osm_id" not in sent and "os_place_id" not in sent, sent
                assert OSM_ID not in found.text and OS_PLACE_ID not in found.text, found.text

            seeded = client.post(
                f"/v1/investigations/{case_id}/seed",
                headers=headers,
                json={"nodes": [found.json()["nodes"][0]], "edges": []},
            )
            assert seeded.status_code == 200, seeded.text
            assert OSM_ID not in seeded.text and OS_PLACE_ID not in seeded.text, seeded.text
    finally:
        refused: list[tuple[str, int]] = []
        with TestClient(app) as client:
            for made_id in cases:
                answer = client.delete(f"/v1/investigations/{made_id}", headers=headers)
                if answer.status_code not in (200, 204):
                    refused.append((made_id, answer.status_code))
        _run(_remove(list(PLANTED)))
        _run(_remove_rows(cases))
        assert not refused, f"cases not removed: {refused}"
