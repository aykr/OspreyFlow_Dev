"""A gazetteer's identifiers never reach the Glass (rule 7; the orchestrator's ruling of 9 November
2026, ADR-147 Amendment 1), through the real routes a case reads its nodes by once it has added the
gazetteer: search (`/search`, `services/api/search.py`), the working set's seed (`/seed`) and
expansion (`/expand`). A gazetteer place with an `osm_id` and a `uprn` is planted in a gazetteer
dataset, beside a neighbour, and a case reading it searches for it by name, puts it on its canvas and
expands from a person present at it, so the place arrives in the expansion; no answer carries
either identifier. Shown red with the projection
removed (`ontology.handling._gazetteer_identifiers_withheld`, `P4_RED_RECORD.md`).

Runs the real `services.api.app` over real ArcadeDB, Postgres and Valkey on a leased test stack, as
`test_sources_withheld_routes.py` does. Everything it writes is removed in teardown, pass or fail: the
two nodes and their link, by id (the Conduit's database is always `ospreyflow`, so not a throwaway
one); its two cases, each delete checked; and in Postgres this run's gazetteer dataset, the cases'
own analyst layers and the rows naming them.
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
from conduit_common.identity import new_edge_id, new_node_id, now_utc
from ontology.handling import load_uk_le_scheme
from ontology.loader import load_default_ontology
from schemas.domain import (
    EdgeWrite,
    Handling,
    Interval,
    NodeWrite,
    Principal,
    Provenance,
    ProvenanceState,
    SourceRef,
)
from tests.conftest import default_claims, sign_token
from tests.services.api.case_dataset import new_case

UNIT = Principal(id="loader-1", clearance="OFFICIAL", org_unit="unit-1", roles=["analyst"])
#: This run's own name, identifiers and dataset, so a search finds this run's place alone and its
#: teardown removes this run's rows alone.
TAG = f"{secrets.randbelow(10**8):08d}"
GAZETTEER = f"gazetteer-osm-p4-live-{TAG}"
NAME = f"Quillbury {TAG}"
OSM_ID = f"node/{TAG}"
UPRN = f"9{TAG}"
PERSON = f"Quillfeather{TAG}"


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


def _handling() -> Handling:
    return Handling(
        classification="OFFICIAL", handling_code="P", originator="unit-1", owning_unit="unit-1"
    )


def _provenance() -> Provenance:
    return Provenance(
        state=ProvenanceState.ASSERTED,
        sources=[SourceRef(document_id="osm-extract", locator="1", excerpt_hash="e" * 64)],
        first_seen=now_utc(),
    )


async def _graph() -> tuple[ArcadeDBClient, GraphArcadeDBAdapter]:
    client = ArcadeDBClient(ArcadeDBConfig.from_env(database="ospreyflow"))
    await client.create_database_if_absent()
    graph = GraphArcadeDBAdapter(client, load_uk_le_scheme())
    await graph.apply_schema(load_default_ontology())
    return client, graph


async def _plant() -> tuple[str, str, str]:
    """A gazetteer place carrying its identifiers, and a person present at it."""
    client, graph = await _graph()
    place = NodeWrite(
        id=new_node_id(), type="Location",
        properties={"name": NAME, "osm_id": OSM_ID, "uprn": UPRN, "geometry_ref": f"g-{TAG}"},
        provenance=_provenance(), handling=_handling(), created_by="loader-1",
        created_at=now_utc(), datasets=[GAZETTEER],
    )  # fmt: skip
    neighbour = place.model_copy(
        update={"id": new_node_id(), "type": "Person", "properties": {"family_name": PERSON}}
    )
    link = EdgeWrite(
        id=new_edge_id(), type="PRESENT_AT", source=neighbour.id, target=place.id,
        interval=Interval(valid_from=datetime(2026, 1, 1, tzinfo=UTC)),
        provenance=_provenance(), handling=_handling(), created_by="loader-1",
        created_at=now_utc(), datasets=[GAZETTEER],
    )  # fmt: skip
    tx = await graph.begin_transaction()
    await graph.upsert_nodes([place, neighbour], tx)
    await graph.upsert_edges([link], tx)
    await graph.commit_transaction(tx)
    await client.aclose()
    return place.id, neighbour.id, link.id


async def _remove(ids: list[str]) -> None:
    client, _graph_adapter = await _graph()
    try:
        quoted = ",".join(f"'{i}'" for i in ids)
        await client.gremlin(f"g.E().has('id',within({quoted})).drop()")
        await client.gremlin(f"g.V().has('id',within({quoted})).drop()")
    finally:
        await client.aclose()


async def _give_case(investigation_id: str) -> None:
    store = await PostgresDatasetStore.connect(PostgresConfig.from_env().dsn)
    try:
        await store.register(
            Dataset(
                id=GAZETTEER, name="Gazetteer: P4 live test", owning_unit=UNIT.org_unit,
                created_at=datetime(2026, 11, 9, tzinfo=UTC), created_by="test",
            )
        )  # fmt: skip
        await store.set_for_case(investigation_id, [GAZETTEER], UNIT)
    finally:
        await store.close()


async def _remove_rows(case_ids: list[str]) -> None:
    """This run's dataset rows: what the cases read, their layers, and the gazetteer dataset."""
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
        await connection.execute(
            "DELETE FROM datasets WHERE id = ANY($1::text[])", [*layers, GAZETTEER]
        )
        left = await connection.fetchval(
            "SELECT count(*) FROM datasets WHERE id = ANY($1::text[])", [*layers, GAZETTEER]
        )
        assert left == 0, f"{left} dataset row(s) of this run were not removed"
    finally:
        await connection.close()


def _carries_an_identifier(text: str) -> bool:
    return OSM_ID in text or UPRN in text or '"osm_id"' in text or '"uprn"' in text


def test_a_case_reading_the_gazetteer_is_sent_its_places_without_their_identifiers(
    api_env: None, keypair: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]
) -> None:
    private_key, _ = keypair
    headers = {"Authorization": f"Bearer {sign_token(private_key, default_claims())}"}
    place_id, neighbour_id, link_id = _run(_plant())
    cases: list[str] = []

    from services.api.app import app

    try:
        with TestClient(app) as client:
            made = client.post("/v1/investigations", headers=headers, json=new_case())
            case_id = made.json()["id"]
            cases.append(case_id)
            _run(_give_case(case_id))

            found = client.post(
                f"/v1/investigations/{case_id}/search", headers=headers, json={"query": NAME}
            )
            assert found.status_code == 200, found.text
            assert [n["id"] for n in found.json()["nodes"]] == [place_id]
            assert found.json()["nodes"][0]["properties"]["name"] == NAME
            assert not _carries_an_identifier(found.text), found.text

            seeded = client.post(
                f"/v1/investigations/{case_id}/seed",
                headers=headers,
                json={"nodes": [found.json()["nodes"][0]], "edges": []},
            )
            assert seeded.status_code == 200, seeded.text
            assert not _carries_an_identifier(seeded.text), seeded.text

            # A second case, from the person alone, so the place arrives by expansion.
            other = client.post("/v1/investigations", headers=headers, json=new_case())
            other_id = other.json()["id"]
            cases.append(other_id)
            _run(_give_case(other_id))
            person = client.post(
                f"/v1/investigations/{other_id}/search", headers=headers, json={"query": PERSON}
            )
            assert [n["id"] for n in person.json()["nodes"]] == [neighbour_id], person.text
            client.post(
                f"/v1/investigations/{other_id}/seed",
                headers=headers,
                json={"nodes": person.json()["nodes"], "edges": []},
            )
            expanded = client.post(
                f"/v1/investigations/{other_id}/expand",
                headers=headers,
                json={"request": {"node_ids": [neighbour_id], "depth": 1}},
            )
            assert expanded.status_code == 200, expanded.text
            assert place_id in {n["id"] for n in expanded.json()["delta"]["nodes"]}, expanded.text
            assert not _carries_an_identifier(expanded.text), expanded.text
    finally:
        refused: list[tuple[str, int]] = []
        with TestClient(app) as client:
            for made_id in cases:
                answer = client.delete(f"/v1/investigations/{made_id}", headers=headers)
                if answer.status_code not in (200, 204):
                    refused.append((made_id, answer.status_code))
        _run(_remove([place_id, neighbour_id, link_id]))
        _run(_remove_rows(cases))
        assert not refused, f"cases not removed: {refused}"
