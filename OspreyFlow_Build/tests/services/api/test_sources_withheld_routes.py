"""ADR-130 Amendment 2, rule 4: the read routes that return elements to the Glass (`/search` and
`/expand`) send a node and a link that belong to two datasets, to a case that reads one of them,
with their sources withheld; to a case that reads both, with their sources named.

Runs the real `services.api.app` over real ArcadeDB, Postgres and Valkey (`make dev-up`), as
`tests/scenarios/test_phase3_working_set.py` does, with a loopback JWKS fixture for the token. The
graph is written straight through the adapter into two datasets; each case is given its datasets
in the real dataset store. Run alone, with the dev stack up:
`cd OspreyFlow_Core && .venv/bin/pytest -c ../OspreyFlow_Build/pytest.ini \
../OspreyFlow_Build/tests/services/api/test_sources_withheld_routes.py`.
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
    NodeWrite,
    Principal,
    Provenance,
    ProvenanceState,
    SourceRef,
)
from tests.conftest import default_claims, sign_token

UNIT = Principal(id="loader-1", clearance="OFFICIAL", org_unit="unit-1", roles=["analyst"])
FIRST = "Z7001ZZ"
SECOND = "Z7002ZZ"
# A number of this run's own: the store is shared with other runs, whose people a fixed number
# would also find.
NINO = f"AB{secrets.randbelow(10**6):06d}C"
SOURCE = SourceRef(document_id="files/calls.csv", locator="row 9", excerpt_hash="e" * 64)


@pytest.fixture
def api_env(jwks_url: str) -> Iterator[None]:
    previous = {
        key: os.environ.get(key)
        for key in ("OIDC_JWKS_URL", "OIDC_ALGORITHMS", "ARCADEDB_DATABASE")
    }
    os.environ["OIDC_JWKS_URL"] = jwks_url
    os.environ["OIDC_ALGORITHMS"] = "RS256"
    os.environ["ARCADEDB_DATABASE"] = "ospreyflow"
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


def _provenance() -> Provenance:
    return Provenance(state=ProvenanceState.ASSERTED, sources=[SOURCE], first_seen=now_utc())


def _handling() -> Handling:
    return Handling(
        classification="OFFICIAL", handling_code="P", originator="unit-1", owning_unit="unit-1"
    )


async def _arrange() -> tuple[str, str]:
    """A person (with a national insurance number to search for) and a neighbour, linked, every
    one of them in both datasets. Returns the two node ids."""
    client = ArcadeDBClient(ArcadeDBConfig.from_env(database="ospreyflow"))
    await client.create_database_if_absent()
    graph = GraphArcadeDBAdapter(client, load_uk_le_scheme())
    await graph.apply_schema(load_default_ontology())
    both = [FIRST, SECOND]
    hub = NodeWrite(
        id=new_node_id(),
        type="Person",
        properties={"family_name": "Quillfeather", "nino": NINO},
        provenance=_provenance(),
        handling=_handling(),
        created_by="loader-1",
        created_at=now_utc(),
        datasets=both,
    )
    neighbour = hub.model_copy(
        update={"id": new_node_id(), "properties": {"family_name": "Marlowe"}}
    )
    tx = await graph.begin_transaction()
    await graph.upsert_nodes([hub, neighbour], tx)
    await graph.upsert_edges(
        [
            EdgeWrite(
                id=new_edge_id(),
                type="ASSOCIATE_OF",
                source=hub.id,
                target=neighbour.id,
                provenance=_provenance(),
                handling=_handling(),
                created_by="loader-1",
                created_at=now_utc(),
                datasets=both,
            )
        ],
        tx,
    )
    await graph.commit_transaction(tx)
    await client.aclose()
    return hub.id, neighbour.id


async def _give_case(investigation_id: str, dataset_ids: list[str]) -> None:
    store = await PostgresDatasetStore.connect(PostgresConfig.from_env().dsn)
    try:
        for dataset_id in (FIRST, SECOND):
            try:
                await store.add(
                    Dataset(
                        id=dataset_id,
                        name=f"Route test {dataset_id}",
                        owning_unit=UNIT.org_unit,
                        created_at=datetime.now(UTC),
                        created_by="test",
                    )
                )
            except Exception:  # noqa: BLE001 - already registered by an earlier run
                pass
        await store.set_for_case(investigation_id, dataset_ids, UNIT)
    finally:
        await store.close()


def _all_withheld(elements: list[dict[str, Any]]) -> bool:
    return bool(elements) and all(
        e["provenance"]["sources"] == [] and e["provenance"]["sources_withheld"] is True
        for e in elements
    )


def _all_named(elements: list[dict[str, Any]]) -> bool:
    return bool(elements) and all(
        [s["document_id"] for s in e["provenance"]["sources"]] == ["files/calls.csv"]
        and not e["provenance"].get("sources_withheld")
        for e in elements
    )


def test_search_and_expand_withhold_sources_from_a_case_that_reads_one_dataset(
    api_env: None, keypair: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]
) -> None:
    private_key, _ = keypair
    headers = {"Authorization": f"Bearer {sign_token(private_key, default_claims())}"}
    hub_id, _ = _run(_arrange())

    from services.api.app import app

    with TestClient(app) as client:
        narrow = client.post("/v1/investigations", headers=headers).json()["id"]
        wide = client.post("/v1/investigations", headers=headers).json()["id"]
        _run(_give_case(narrow, [FIRST]))
        _run(_give_case(wide, [FIRST, SECOND]))

        found = client.post(
            f"/v1/investigations/{narrow}/search", headers=headers, json={"query": NINO}
        )
        assert found.status_code == 200, found.text
        assert [n["id"] for n in found.json()["nodes"]] == [hub_id]
        assert _all_withheld(found.json()["nodes"])
        assert "files/calls.csv" not in found.text

        for case in (narrow, wide):
            seeded = client.post(
                f"/v1/investigations/{case}/seed",
                headers=headers,
                json={"nodes": [found.json()["nodes"][0]], "edges": []},
            )
            assert seeded.status_code == 200, seeded.text

        expanded = client.post(
            f"/v1/investigations/{narrow}/expand",
            headers=headers,
            json={"request": {"node_ids": [hub_id], "depth": 1}},
        )
        assert expanded.status_code == 200, expanded.text
        delta = expanded.json()["delta"]
        assert _all_withheld(delta["nodes"]) and _all_withheld(delta["edges"])
        assert "files/calls.csv" not in expanded.text

        # The same rows, read by a case of both datasets, are named: the withholding is the
        # reader's scope and nothing else.
        found_wide = client.post(
            f"/v1/investigations/{wide}/search", headers=headers, json={"query": NINO}
        )
        assert _all_named(found_wide.json()["nodes"])
        expanded_wide = client.post(
            f"/v1/investigations/{wide}/expand",
            headers=headers,
            json={"request": {"node_ids": [hub_id], "depth": 1}},
        )
        assert expanded_wide.status_code == 200, expanded_wide.text
        wide_delta = expanded_wide.json()["delta"]
        assert _all_named(wide_delta["nodes"]) and _all_named(wide_delta["edges"])
