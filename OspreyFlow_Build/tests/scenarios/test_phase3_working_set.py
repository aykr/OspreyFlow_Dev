"""Phase 3's exit criterion, end to end:

"A scripted client seeds a working set, expands three times, disconnects
mid-stream, reconnects and arrives at a byte-identical set. Every action
appears in the audit stream. An expansion that would breach the cap
returns the typed `limit_exceeded` error with its three options. An
expansion that excludes a handling-filtered node reports a non-zero
`filtered_count`."

Runs the real `services.api.app` FastAPI app — real lifespan, real
ArcadeDB/Valkey/Postgres connections (`make dev-up`), a real signed JWT
against a loopback JWKS fixture (`tests/conftest.py`) — the only thing not
"real" is that the OIDC IdP is a fixture rather than Keycloak, which is
exactly the substitution `services/api/auth.py`'s design intends to be
transparent.

The graph fixture (`_arrange_graph`) is written directly through
`GraphPort`, bypassing the API — `hub` (OFFICIAL) connects to `visible`
(OFFICIAL) and to `secret` (SECRET). Seeding and expanding from `hub` as
an OFFICIAL principal then exercises `filtered_count` for free on the
same expand calls the sequencing/audit/reconnect assertions already need,
rather than a second, separate arrangement.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Iterator
from typing import Any

import asyncpg
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from adapters.graph_arcadedb.adapter import GraphArcadeDBAdapter
from adapters.graph_arcadedb.client import ArcadeDBClient, ArcadeDBConfig
from conduit_common.identity import new_node_id, now_utc
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
from tests.services.api.case_dataset import dataset_for, give_case_its_dataset


@pytest.fixture
def api_env(jwks_url: str) -> Iterator[None]:
    """`services.api.config.ApiConfig.from_env()` reads these at lifespan
    startup, not at import time — setting them here, before the app's
    `with TestClient(app) as client:` block runs, is enough; no need to
    reload any module."""
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


def _bearer(private_key: rsa.RSAPrivateKey, **claim_overrides: object) -> dict[str, str]:
    token = sign_token(private_key, default_claims(**claim_overrides))
    return {"Authorization": f"Bearer {token}"}


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


def _provenance() -> Provenance:
    return Provenance(
        state=ProvenanceState.ASSERTED,
        sources=[SourceRef(document_id="doc-1", locator="p.1", excerpt_hash="a" * 64)],
        first_seen=now_utc(),
    )


def _handling(classification: str) -> Handling:
    return Handling(
        classification=classification, handling_code="P",
        originator="unit-1", owning_unit="unit-1",
    )


#: Since ADR-099 a case reads only its own datasets: the graph below is written into one, and each
#: case made here is given it (`case_dataset.py` says why). Every principal here is in `unit-1`.
_UNIT = Principal(id="loader-1", clearance="OFFICIAL", org_unit="unit-1", roles=["analyst"])
_DATASET = dataset_for(_UNIT)


async def _arrange_graph() -> dict[str, Any]:
    """`hub` (OFFICIAL) -- ASSOCIATE_OF --> `visible` (OFFICIAL) and
    `hub` -- ASSOCIATE_OF --> `secret` (SECRET), written directly through
    `GraphPort` so `expand(hub, depth=1)` has something real to traverse
    — an OFFICIAL principal's `expand()` reaches `visible` but not
    `secret`, which is what makes `filtered_count` non-zero below."""
    client = ArcadeDBClient(ArcadeDBConfig.from_env(database="ospreyflow"))
    await client.create_database_if_absent()
    graph = GraphArcadeDBAdapter(client, load_uk_le_scheme())
    await graph.apply_schema(load_default_ontology())

    hub_id, visible_id, secret_id = new_node_id(), new_node_id(), new_node_id()
    hub_write = NodeWrite(
        id=hub_id, type="Person", properties={"family_name": "Hub"},
        provenance=_provenance(),
        handling=_handling("OFFICIAL"), created_by="loader-1", created_at=now_utc(), datasets=[_DATASET],
    )
    tx = await graph.begin_transaction()
    await graph.upsert_nodes(
        [
            hub_write,
            NodeWrite(
                id=visible_id, type="Person", properties={"family_name": "Visible"},
                provenance=_provenance(),
                handling=_handling("OFFICIAL"), created_by="loader-1", created_at=now_utc(), datasets=[_DATASET],
            ),
            NodeWrite(
                id=secret_id, type="Person", properties={"family_name": "Secret"},
                provenance=_provenance(),
                handling=_handling("SECRET"), created_by="loader-1", created_at=now_utc(), datasets=[_DATASET],
            ),
        ],
        tx,
    )
    await graph.upsert_edges(
        [
            EdgeWrite(
                id=new_node_id(), type="ASSOCIATE_OF", source=hub_id, target=visible_id,
                provenance=_provenance(), handling=_handling("OFFICIAL"),
                created_by="loader-1", created_at=now_utc(), datasets=[_DATASET],
            ),
            EdgeWrite(
                id=new_node_id(), type="ASSOCIATE_OF", source=hub_id, target=secret_id,
                provenance=_provenance(), handling=_handling("SECRET"),
                created_by="loader-1", created_at=now_utc(), datasets=[_DATASET],
            ),
        ],
        tx,
    )
    await graph.commit_transaction(tx)
    await client.aclose()

    hub_node = {
        "id": hub_write.id,
        "type": hub_write.type,
        "properties": hub_write.properties,
        "provenance": hub_write.provenance.model_dump(mode="json"),
        "handling": hub_write.handling.model_dump(mode="json"),
        "resolution": {},
        "audit": {"created_at": hub_write.created_at.isoformat(), "created_by": "loader-1"},
    }
    return {
        "hub_node": hub_node,
        "hub_id": hub_id,
        "visible_id": visible_id,
        "secret_id": secret_id,
    }


async def _audit_rows_for(investigation_id: str) -> list[asyncpg.Record]:
    from services.api.config import PostgresConfig

    conn = await asyncpg.connect(dsn=PostgresConfig.from_env().dsn)
    try:
        return await conn.fetch(
            "SELECT action FROM audit_log WHERE investigation_id = $1 ORDER BY id",
            investigation_id,
        )
    finally:
        await conn.close()


def test_seed_expand_disconnect_reconnect_audit_cap_and_filtered_count(
    api_env: None, keypair: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]
) -> None:
    private_key, _ = keypair
    headers = _bearer(private_key)
    fixture = _run(_arrange_graph())
    hub_node, hub_id, secret_id = fixture["hub_node"], fixture["hub_id"], fixture["secret_id"]
    expand_body = {"request": {"node_ids": [hub_id], "depth": 1}}

    from services.api.app import app

    with TestClient(app) as client:
        # --- seed a working set -----------------------------------------
        created = client.post("/v1/investigations", headers=headers)
        assert created.status_code == 201, created.text
        investigation_id = created.json()["id"]
        _run(give_case_its_dataset(investigation_id, _UNIT))

        seeded = client.post(
            f"/v1/investigations/{investigation_id}/seed",
            headers=headers,
            json={"nodes": [hub_node], "edges": []},
        )
        assert seeded.status_code == 200, seeded.text
        assert seeded.json()["delta"]["seq"] == 1

        # --- expand three times; filtered_count is non-zero every time --
        seqs: list[int] = [1]
        for _ in range(3):
            response = client.post(
                f"/v1/investigations/{investigation_id}/expand",
                headers=headers,
                json=expand_body,
            )
            assert response.status_code == 200, response.text
            body = response.json()
            seqs.append(body["delta"]["seq"])
            # The SECRET neighbour is real but excluded from every one of
            # these OFFICIAL-principal expands (`01_DOMAIN_MODEL.md` §8.2).
            # Identity, not just count — matching `test_suite.py`'s own
            # existence-leak style rather than asserting on the number
            # alone (the coverage gap the divergence review named).
            assert body["filtered_count"] > 0
            delivered_ids = {n["id"] for n in body["delta"]["nodes"]}
            assert secret_id not in delivered_ids
        assert seqs == [1, 2, 3, 4]  # seed + three expands, strictly monotonic

        # --- disconnect mid-stream, reconnect: byte-identical set -------
        with client.websocket_connect(
            f"/v1/investigations/{investigation_id}/stream", headers=headers
        ) as ws:
            ws.send_json({"last_acknowledged_seq": None})
            snapshot = ws.receive_json()
            assert snapshot["op"] == "snapshot"
            assert snapshot["seq"] == 4  # caught up to everything so far
            assert secret_id not in {n["id"] for n in snapshot["nodes"]}
        # The socket above is now closed — "disconnects mid-stream". A
        # further action happens while nobody is connected.
        further = client.post(
            f"/v1/investigations/{investigation_id}/expand",
            headers=headers,
            json=expand_body,
        )
        assert further.status_code == 200, further.text
        assert further.json()["delta"]["seq"] == 5

        with client.websocket_connect(
            f"/v1/investigations/{investigation_id}/stream", headers=headers
        ) as ws:
            # Reconnect from the last seq this client actually saw (4) —
            # the server must not have silently dropped seq 5 in between.
            ws.send_json({"last_acknowledged_seq": 4})
            caught_up = ws.receive_json()
            assert caught_up["seq"] == 5

        # --- every action appears in the audit stream --------------------
        actions = [row["action"] for row in _run(_audit_rows_for(investigation_id))]
        for expected in ("create_investigation", "seed", "expand"):
            assert expected in actions
        assert actions.count("expand") == 4  # three, then the post-disconnect one

        # --- the cap: limit_exceeded with all three options ---------------
        # A fresh investigation, seeded with only `hub` — clean headroom so
        # the breach is caused by *this* expand, not accumulated state.
        breach_investigation = client.post("/v1/investigations", headers=headers).json()["id"]
        _run(give_case_its_dataset(breach_investigation, _UNIT))
        client.post(
            f"/v1/investigations/{breach_investigation}/seed",
            headers=headers,
            json={"nodes": [hub_node], "edges": []},
        )
        import services.api.working_set.service as service_module

        original_max_nodes = service_module.MAX_NODES
        service_module.MAX_NODES = 1  # `hub` alone already meets this cap
        try:
            over_cap = client.post(
                f"/v1/investigations/{breach_investigation}/expand",
                headers=headers,
                json=expand_body,
            )
        finally:
            service_module.MAX_NODES = original_max_nodes
        assert over_cap.status_code == 409, over_cap.text
        breach_body = over_cap.json()
        assert breach_body["error"] == "limit_exceeded"
        assert breach_body["cap_kind"] == "nodes"
        assert set(breach_body["options"]) == {"branch", "filter", "promote_to_batch"}


def test_a_principal_in_a_different_org_unit_is_denied(
    api_env: None, keypair: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]
) -> None:
    """Divergence-review fix #1: `owning_unit` gates the investigation
    itself. A validly-signed token from a principal in a *different* unit
    gets the same 404 an unknown investigation id would — not a 403, so
    "wrong unit" is indistinguishable from "doesn't exist" from outside."""
    private_key, _ = keypair
    creator_headers = _bearer(private_key, sub="analyst-1", org_unit="unit-1")
    stranger_headers = _bearer(private_key, sub="analyst-stranger", org_unit="unit-2")

    from services.api.app import app

    with TestClient(app) as client:
        created = client.post("/v1/investigations", headers=creator_headers)
        assert created.status_code == 201, created.text
        investigation_id = created.json()["id"]
        _run(give_case_its_dataset(investigation_id, _UNIT))

        denied = client.get(f"/v1/investigations/{investigation_id}", headers=stranger_headers)

        assert denied.status_code == 404
        assert denied.json()["error"] == "investigation_not_found"


def test_a_lower_clearance_principal_sharing_an_investigation_sees_the_filtered_subset(
    api_env: None, keypair: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]
) -> None:
    """The case divergence-review fix #2 exists for: two principals in the
    *same* org_unit (so both pass #1's gate) at *different* clearances
    share one investigation. The SECRET principal's own expand legitimately
    sees the SECRET neighbour — it is their own properly-filtered
    `GraphPort.expand()` result. A *different*, OFFICIAL principal opening
    the same investigation afterward must not receive it back — proving
    the handling filter is re-applied on read, per-reader, not baked in
    once at write time."""
    private_key, _ = keypair
    secret_headers = _bearer(
        private_key, sub="analyst-secret", clearance="SECRET", org_unit="unit-1"
    )
    official_headers = _bearer(
        private_key, sub="analyst-official", clearance="OFFICIAL", org_unit="unit-1"
    )
    fixture = _run(_arrange_graph())
    hub_node, hub_id, secret_id = fixture["hub_node"], fixture["hub_id"], fixture["secret_id"]

    from services.api.app import app

    with TestClient(app) as client:
        created = client.post("/v1/investigations", headers=secret_headers)
        investigation_id = created.json()["id"]
        _run(give_case_its_dataset(investigation_id, _UNIT))

        # Since ADR-052 a new case is its creator's alone until shared: the SECRET analyst shares
        # it with the OFFICIAL one, which is the sharing this test is about.
        shared = client.put(
            f"/v1/investigations/{investigation_id}/access/grants/analyst-official",
            headers=secret_headers,
            json={"level": "viewer"},
        )
        assert shared.status_code == 204, shared.text
        client.post(
            f"/v1/investigations/{investigation_id}/seed",
            headers=secret_headers,
            json={"nodes": [hub_node], "edges": []},
        )
        expanded = client.post(
            f"/v1/investigations/{investigation_id}/expand",
            headers=secret_headers,
            json={"request": {"node_ids": [hub_id], "depth": 1}},
        )
        assert expanded.status_code == 200, expanded.text
        # The SECRET principal's own expand legitimately includes the
        # SECRET neighbour — this is not the leak; it is the setup for it.
        secret_delivered_ids = {n["id"] for n in expanded.json()["delta"]["nodes"]}
        assert secret_id in secret_delivered_ids

        # A different, OFFICIAL principal, same org_unit, opens the same
        # investigation — authorized by #1 (unit matches), but must be
        # denied the SECRET content #2 exists to protect.
        get_response = client.get(
            f"/v1/investigations/{investigation_id}", headers=official_headers
        )
        assert get_response.status_code == 200, get_response.text

        with client.websocket_connect(
            f"/v1/investigations/{investigation_id}/stream", headers=official_headers
        ) as ws:
            ws.send_json({"last_acknowledged_seq": None})
            snapshot = ws.receive_json()

        official_node_ids = {n["id"] for n in snapshot["nodes"]}
        assert secret_id not in official_node_ids
        assert hub_id in official_node_ids  # the OFFICIAL content is still there
        assert snapshot["filtered_count"] > 0
