"""A gazetteer's identifiers never reach the Glass (rule 7; the orchestrator's ruling of 9 November
2026, ADR-147 Amendment 1), through the real routes a case reads its nodes by once it has added the
gazetteer: search (`/search`, `services/api/search.py`), the working set's seed (`/seed`) and
expansion (`/expand`). A gazetteer place with an `osm_id` and a `uprn` is planted in a gazetteer
dataset, beside a neighbour, and a case reading it searches for it by name, puts it on its canvas
and expands from a person present at it, so the place arrives in the expansion; no answer carries
either identifier. Shown red with the projection removed
(`ontology.handling._gazetteer_identifiers_withheld`, `P4_RED_RECORD.md`).

Runs the real `services.api.app` over real ArcadeDB, Postgres and Valkey on a leased test stack, as
`test_sources_withheld_routes.py` does. Everything it writes is removed in teardown, pass or fail:
the two nodes and their link, by id (the Conduit's database is always `ospreyflow`, so not a
throwaway one); its two cases, each delete checked; and in Postgres this run's gazetteer dataset,
the cases' own analyst layers and the rows naming them.
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
#: Digits, as the OSM loader writes an `osm_id` (`connectors/geo/osm.py`), led by a 7 so the place's
#: own name (which holds the tag) never contains it.
OSM_ID = f"7{TAG}"
UPRN = f"9{TAG}"
PERSON = f"Quillfeather{TAG}"
#: Every node this run plants beyond the place and the person, removed in teardown.
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


async def _plant() -> tuple[str, str, str, dict[str, Any]]:
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
    # Twelve more places whose `osm_id`s share the place's prefix: more than a type-ahead page.
    alike = [
        place.model_copy(
            update={
                "id": new_node_id(),
                "properties": {"name": f"Elsewhere {i}", "osm_id": f"{OSM_ID}{i:02d}"},
            }
        )
        for i in range(12)
    ]
    # Every id recorded before anything is written: teardown removes what a part-way failure left.
    PLANTED.extend([place.id, neighbour.id, link.id, *(n.id for n in alike)])
    tx = await graph.begin_transaction()
    await graph.upsert_nodes([place, neighbour, *alike], tx)
    await graph.upsert_edges([link], tx)
    await graph.commit_transaction(tx)
    # The person's stored record, to put on the second case's canvas: a person in a gazetteer
    # dataset is found by name alone, and a person has no `name` (decision 3b), so it is not
    # searched for.
    unlimited = UNIT.model_copy(update={"datasets": None})
    stored = await graph.get_node(neighbour.id, unlimited)
    await client.aclose()
    assert stored is not None
    return place.id, neighbour.id, link.id, stored.model_dump(mode="json")


async def _remove(ids: list[str]) -> None:
    if not ids:
        return
    client, _graph_adapter = await _graph()
    try:
        quoted = ",".join(f"'{i}'" for i in ids)
        await client.gremlin(f"g.E().has('id',within({quoted})).drop()")
        await client.gremlin(f"g.V().has('id',within({quoted})).drop()")
        left = await client.gremlin(f"g.V().has('id',within({quoted})).values('id')")
        assert left == [], f"left behind in the shared database: {left}"
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
    PLANTED.clear()
    cases: list[str] = []

    from services.api.app import app

    try:
        place_id, neighbour_id, _link_id, person_body = _run(_plant())
        with TestClient(app) as client:
            made = client.post("/v1/investigations", headers=headers, json=new_case())
            case_id = made.json()["id"]
            cases.append(case_id)
            _run(_give_case(case_id))

            # The ruling of 9 November 2026: the case's own searches match a gazetteer place on its
            # name alone. The exact search by its `osm_id` finds nothing; the type-ahead on the
            # identifier's prefix suggests nothing and says no `more`, though 12 places share it.
            by_id = client.post(
                f"/v1/investigations/{case_id}/search", headers=headers, json={"query": OSM_ID}
            )
            assert by_id.status_code == 200 and by_id.json()["nodes"] == [], by_id.text
            for body in (
                {"query": OSM_ID},
                {"query": OSM_ID, "mode": "contains", "ignore_case": True},
            ):
                hinted = client.post(
                    f"/v1/investigations/{case_id}/suggest", headers=headers, json=body
                )
                assert hinted.status_code == 200, hinted.text
                assert hinted.json()["nodes"] == [] and hinted.json()["more"] is False, body
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
            put = client.post(
                f"/v1/investigations/{other_id}/seed",
                headers=headers,
                json={"nodes": [person_body], "edges": []},
            )
            assert put.status_code == 200, put.text
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
        _run(_remove(list(PLANTED)))
        _run(_remove_rows(cases))
        assert not refused, f"cases not removed: {refused}"
