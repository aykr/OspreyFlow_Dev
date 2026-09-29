"""`POST/GET /v1/investigations/{id}/judgements`, `.../gaps`, `.../assumptions` — Phase 8 Stage 4c.

Real FastAPI app, real ArcadeDB/Postgres, real HTTP, real JWT bearer auth — the same shape
`tests/scenarios/test_phase7_stage6c_watch_routes.py` already establishes for a route-level test,
reused here rather than a second pattern invented: `with TestClient(app) as client:` runs the
app's own real lifespan (its own real `judgements_store`/`graph`, not a `dependency_overrides`
fake bound to a different event loop — the event-loop-per-portal mismatch that pattern avoids).
Setup writes go through a standalone `asyncio.run(...)` call against the same persistent
`ospreyflow` ArcadeDB database and the same Postgres the running app connects to, never
`arcadedb_adapter`'s own ephemeral test database.

The underlying store/business logic is proven with real services already in
`tests/services/api/test_assessments.py`; this file proves each route wires it correctly: the
path's own `AuthorizedInvestigationDep`-verified investigation id wins over any body-supplied one,
store exceptions map to the right status codes, and `list_visible_judgements` (not the bare
ownership-only list) is what the judgements route actually calls.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from services.api.config import PostgresConfig
from services.api.investigations import InvestigationStore

from adapters.graph_arcadedb.adapter import GraphArcadeDBAdapter
from adapters.graph_arcadedb.client import ArcadeDBClient, ArcadeDBConfig
from conduit_common.identity import new_id
from ontology.handling import load_uk_le_scheme
from ontology.loader import load_default_ontology
from schemas.domain import Handling, NodeWrite, Principal, Provenance, ProvenanceState, SourceRef
from tests.conftest import default_claims, sign_token

PRINCIPAL = Principal(id="analyst-1", clearance="OFFICIAL", org_unit="unit-1")


@pytest.fixture
def api_env(jwks_url: str) -> Iterator[None]:
    """`test_phase7_stage6c_watch_routes.py`'s own fixture, unchanged."""
    import os

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


def _node_write(*, owning_unit: str, classification: str = "OFFICIAL") -> NodeWrite:
    now = datetime.now(UTC)
    return NodeWrite(
        id=new_id(),
        type="Person",
        properties={
            "family_name": "Routefixture",
            "given_names": "A",
            "date_of_birth": "1990-01-01",
        },
        provenance=Provenance(
            state=ProvenanceState.ASSERTED,
            sources=[SourceRef(document_id="fixture", locator="test", excerpt_hash="")],
            first_seen=now,
        ),
        handling=Handling(
            classification=classification,
            handling_code="P",
            originator=owning_unit,
            owning_unit=owning_unit,
        ),
        created_by="test",
        created_at=now,
    )


async def _write_node(*, owning_unit: str, classification: str = "OFFICIAL") -> str:
    """Writes directly against the same real, persistent `ospreyflow` ArcadeDB database the
    running `TestClient` app's own lifespan connects to — never `arcadedb_adapter`'s own separate
    database, which the running app would never see."""
    client = ArcadeDBClient(ArcadeDBConfig.from_env(database="ospreyflow"))
    try:
        graph = GraphArcadeDBAdapter(client, load_uk_le_scheme())
        await graph.apply_schema(load_default_ontology())
        tx = await graph.begin_transaction()
        (node_id,) = await graph.upsert_nodes(
            [_node_write(owning_unit=owning_unit, classification=classification)], tx
        )
        await graph.commit_transaction(tx)
        return node_id
    finally:
        await client.aclose()


async def _write_investigation(principal: Principal) -> str:
    store = await InvestigationStore.connect(PostgresConfig.from_env().dsn)
    try:
        investigation = await store.create(principal, name="Test case")
        return investigation.id
    finally:
        await store.close()


# --- Judgements -----------------------------------------------------------------------------


def test_save_judgement_route_creates_and_returns_it(
    api_env: None, keypair: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]
) -> None:
    private_key, _ = keypair
    headers = _bearer(private_key)
    investigation_id = asyncio.run(_write_investigation(PRINCIPAL))
    node_id = asyncio.run(_write_node(owning_unit=PRINCIPAL.org_unit))

    from services.api.app import app

    with TestClient(app) as client:
        response = client.post(
            f"/v1/investigations/{investigation_id}/judgements",
            headers=headers,
            json={
                "investigation_id": investigation_id,
                "statement": "The subject is the principal organiser.",
                "probability_band": "likely",
                "supporting": [node_id],
                "contradicting": [],
            },
        )
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["statement"] == "The subject is the principal organiser."
        assert body["supporting"] == [node_id]
        assert body["flagged_for_review"] is False


def test_save_judgement_route_rejects_zero_supporting_references(
    api_env: None, keypair: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]
) -> None:
    private_key, _ = keypair
    headers = _bearer(private_key)
    investigation_id = asyncio.run(_write_investigation(PRINCIPAL))

    from services.api.app import app

    with TestClient(app) as client:
        response = client.post(
            f"/v1/investigations/{investigation_id}/judgements",
            headers=headers,
            json={
                "investigation_id": investigation_id,
                "statement": "Unsupported.",
                "probability_band": "likely",
                "supporting": [],
            },
        )
        assert response.status_code == 422, response.text
        assert response.json()["error"] == "no_supporting_reference"


def test_save_judgement_route_rejects_an_unverifiable_citation_and_names_it(
    api_env: None, keypair: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]
) -> None:
    private_key, _ = keypair
    headers = _bearer(private_key)
    investigation_id = asyncio.run(_write_investigation(PRINCIPAL))
    unresolvable = new_id()

    from services.api.app import app

    with TestClient(app) as client:
        response = client.post(
            f"/v1/investigations/{investigation_id}/judgements",
            headers=headers,
            json={
                "investigation_id": investigation_id,
                "statement": "Cites a document, not yet supported.",
                "probability_band": "likely",
                "supporting": [unresolvable],
            },
        )
        assert response.status_code == 422, response.text
        body = response.json()
        assert body["error"] == "unverifiable_citation"
        assert body["citation_ids"] == [unresolvable]


def test_save_judgement_route_uses_the_path_investigation_id_not_the_bodys(
    api_env: None, keypair: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]
) -> None:
    """Security-relevant: a body-supplied `investigation_id` must never override the path's own
    `AuthorizedInvestigationDep`-verified one — `SaveJudgementRequest`'s own docstring states this
    is deliberate."""
    private_key, _ = keypair
    headers = _bearer(private_key)
    investigation_id = asyncio.run(_write_investigation(PRINCIPAL))
    node_id = asyncio.run(_write_node(owning_unit=PRINCIPAL.org_unit))

    from services.api.app import app

    with TestClient(app) as client:
        response = client.post(
            f"/v1/investigations/{investigation_id}/judgements",
            headers=headers,
            json={
                "investigation_id": "some-other-investigation-entirely",
                "statement": "Statement.",
                "probability_band": "likely",
                "supporting": [node_id],
            },
        )
        assert response.status_code == 201, response.text
        assert response.json()["investigation_id"] == investigation_id


def test_a_principal_in_a_different_unit_cannot_reach_the_investigation(
    api_env: None, keypair: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]
) -> None:
    private_key, _ = keypair
    investigation_id = asyncio.run(_write_investigation(PRINCIPAL))
    other_unit_headers = _bearer(private_key, sub="analyst-2", org_unit="unit-2")

    from services.api.app import app

    with TestClient(app) as client:
        response = client.get(
            f"/v1/investigations/{investigation_id}/judgements", headers=other_unit_headers
        )
        assert response.status_code == 404, response.text
        assert response.json()["error"] == "investigation_not_found"


def test_list_judgements_route_hides_one_with_an_unreadable_supporting_reference(
    api_env: None, keypair: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]
) -> None:
    private_key, _ = keypair
    investigation_id = asyncio.run(_write_investigation(PRINCIPAL))
    visible_id = asyncio.run(_write_node(owning_unit=PRINCIPAL.org_unit))
    hidden_id = asyncio.run(_write_node(owning_unit="unit-9", classification="SECRET"))

    # Saved by a SECRET-cleared principal — the same reason `test_assessments.py`'s own ADR-046
    # test does this: an OFFICIAL-cleared principal could never save this judgement, since it
    # could not confirm the SECRET citation any more than the OFFICIAL viewer below can.
    secret_headers = _bearer(private_key, clearance="SECRET")
    official_headers = _bearer(private_key, clearance="OFFICIAL")

    from services.api.app import app

    with TestClient(app) as client:
        save_response = client.post(
            f"/v1/investigations/{investigation_id}/judgements",
            headers=secret_headers,
            json={
                "investigation_id": investigation_id,
                "statement": "Cites a SECRET node.",
                "probability_band": "likely",
                "supporting": [visible_id, hidden_id],
            },
        )
        assert save_response.status_code == 201, save_response.text

        list_response = client.get(
            f"/v1/investigations/{investigation_id}/judgements", headers=official_headers
        )
        assert list_response.status_code == 200, list_response.text
        assert list_response.json()["judgements"] == []


# --- Gaps and assumptions --------------------------------------------------------------------


def test_save_and_list_gap_route(
    api_env: None, keypair: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]
) -> None:
    private_key, _ = keypair
    headers = _bearer(private_key)
    investigation_id = asyncio.run(_write_investigation(PRINCIPAL))

    from services.api.app import app

    with TestClient(app) as client:
        response = client.post(
            f"/v1/investigations/{investigation_id}/gaps",
            headers=headers,
            json={
                "investigation_id": investigation_id,
                "question": "Who supplied the vehicle?",
                "linked_entities": [],
                "status": "open",
            },
        )
        assert response.status_code == 201, response.text
        assert response.json()["raised_by"] == PRINCIPAL.id

        listed = client.get(f"/v1/investigations/{investigation_id}/gaps", headers=headers)
        assert listed.status_code == 200, listed.text
        assert any(g["question"] == "Who supplied the vehicle?" for g in listed.json()["gaps"])


def test_save_and_list_assumption_route(
    api_env: None, keypair: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]
) -> None:
    private_key, _ = keypair
    headers = _bearer(private_key)
    investigation_id = asyncio.run(_write_investigation(PRINCIPAL))

    from services.api.app import app

    with TestClient(app) as client:
        response = client.post(
            f"/v1/investigations/{investigation_id}/assumptions",
            headers=headers,
            json={
                "investigation_id": investigation_id,
                "statement": "The subject acted alone.",
                "if_false_impact": "The principal-organiser judgement falls over.",
                "linked_judgements": [],
            },
        )
        assert response.status_code == 201, response.text

        listed = client.get(
            f"/v1/investigations/{investigation_id}/assumptions", headers=headers
        )
        assert listed.status_code == 200, listed.text
        assert any(
            a["statement"] == "The subject acted alone." for a in listed.json()["assumptions"]
        )
