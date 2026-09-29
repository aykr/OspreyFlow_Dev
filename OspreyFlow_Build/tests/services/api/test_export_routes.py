"""`POST /v1/investigations/{id}/export`, `GET /v1/exports` — Phase 8 Stage 4d.

Real FastAPI app, real ArcadeDB/Postgres, real HTTP, real JWT bearer auth — the same
`with TestClient(app) as client:` real-lifespan pattern `test_assessment_routes.py` already
established for this class of test. The underlying gate/mark/ledger logic is proven with real
services already in `tests/services/api/test_export.py`; this file proves the route itself wires
it correctly — status codes, the response shape, and that a client-submitted `handling` on a node
item is never trusted over what `graph.get_node` says fresh.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from services.api.config import PostgresConfig, ValkeyConfig
from services.api.investigations import InvestigationStore
from services.api.working_set.service import WorkingSetService
from services.api.working_set.store import ValkeyWorkingSetStore
from valkey.asyncio import Valkey

from adapters.graph_arcadedb.adapter import GraphArcadeDBAdapter
from adapters.graph_arcadedb.client import ArcadeDBClient, ArcadeDBConfig
from conduit_common.identity import new_id
from ontology.handling import load_uk_le_scheme
from ontology.loader import load_default_ontology
from schemas.domain import (
    AuditStub,
    Handling,
    Node,
    NodeWrite,
    Principal,
    Provenance,
    ProvenanceState,
    SourceRef,
)
from tests.conftest import default_claims, sign_token

PRINCIPAL = Principal(id="analyst-1", clearance="OFFICIAL", org_unit="unit-1")

_PLACEHOLDER_HANDLING = {
    "classification": "OFFICIAL",
    "handling_code": "P",
    "originator": "unit-1",
    "owning_unit": "unit-1",
}


@pytest.fixture
def api_env(jwks_url: str) -> Iterator[None]:
    """`test_assessment_routes.py`'s own fixture, unchanged."""
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


def _node_write(
    *, owning_unit: str, classification: str = "OFFICIAL", sanitisation_code: str | None = None
) -> NodeWrite:
    now = datetime.now(UTC)
    return NodeWrite(
        id=new_id(),
        type="Person",
        properties={
            "family_name": "Exportroutefixture",
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
            sanitisation_code=sanitisation_code,
            originator=owning_unit,
            owning_unit=owning_unit,
        ),
        created_by="test",
        created_at=now,
    )


async def _write_node(*, owning_unit: str, sanitisation_code: str | None = None) -> str:
    client = ArcadeDBClient(ArcadeDBConfig.from_env(database="ospreyflow"))
    try:
        graph = GraphArcadeDBAdapter(client, load_uk_le_scheme())
        await graph.apply_schema(load_default_ontology())
        tx = await graph.begin_transaction()
        (node_id,) = await graph.upsert_nodes(
            [_node_write(owning_unit=owning_unit, sanitisation_code=sanitisation_code)], tx
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


def _membership_node(*, owning_unit: str, classification: str = "OFFICIAL") -> Node:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    return Node(
        id=new_id(),
        type="Person",
        provenance=Provenance(
            state=ProvenanceState.ASSERTED,
            sources=[SourceRef(document_id="fixture", locator="test", excerpt_hash="a" * 64)],
            first_seen=now,
        ),
        handling=Handling(
            classification=classification,
            handling_code="P",
            originator=owning_unit,
            owning_unit=owning_unit,
        ),
        audit=AuditStub(created_at=now, created_by="test"),
    )


#: `WorkingSetService.seed` itself validates the *seeding* principal can see everything it is
#: handed — "the one write path that must itself validate the seeding principal can see what
#: they are handing in" (its own docstring) — so seeding a SECRET node through `PRINCIPAL`
#: (OFFICIAL) would silently drop it before it was ever stored. `_seed_working_set` below seeds as
#: a principal cleared for everything the test hands it; the export itself still runs as
#: `PRINCIPAL`, whose own access is what `withheld_count_for` measures.
_SEEDER = Principal(id="seeder-1", clearance="SECRET", org_unit=PRINCIPAL.org_unit)


async def _seed_working_set(investigation_id: str, nodes: list[Node]) -> None:
    """Seeds the *real*, Valkey-backed working set this app's own `WorkingSetDep` reads from —
    the same store `submit_export_route` (`services/api/app.py`) uses, so a test proving the
    client cannot influence the export's own `withheld_count` over real HTTP is proving it against
    the same membership the route itself will read, not a stand-in."""
    valkey = Valkey(**{
        "host": ValkeyConfig.from_env().host,
        "port": ValkeyConfig.from_env().port,
        "db": ValkeyConfig.from_env().db,
    })
    client = ArcadeDBClient(ArcadeDBConfig.from_env(database="ospreyflow"))
    try:
        graph = GraphArcadeDBAdapter(client, load_uk_le_scheme())
        service = WorkingSetService(
            graph, ValkeyWorkingSetStore(valkey), load_uk_le_scheme(), valkey=valkey
        )
        await service.seed(investigation_id, nodes, [], _SEEDER)
    finally:
        await client.aclose()
        await valkey.aclose()


def test_export_route_succeeds_and_returns_a_mark_and_manifest(
    api_env: None, keypair: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]
) -> None:
    private_key, _ = keypair
    headers = _bearer(private_key)
    investigation_id = asyncio.run(_write_investigation(PRINCIPAL))
    node_id = asyncio.run(_write_node(owning_unit=PRINCIPAL.org_unit))

    from services.api.app import app

    with TestClient(app) as client:
        response = client.post(
            f"/v1/investigations/{investigation_id}/export",
            headers=headers,
            json={
                "artefact_kind": "subgraph",
                "items": [{"id": node_id, "kind": "node", "handling": _PLACEHOLDER_HANDLING}],
                "resolution_threshold": 0.95,
                # No client-writable count at all — `ExportRequest` has no such field.
            },
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["mark"]["investigation_id"] == investigation_id
        assert body["mark"]["osprey_mark"] == "OspreyFlow"
        assert body["manifest"]["policy"] == "disclose"
        # Nothing was ever seeded into this fresh investigation's own working set — the real,
        # server-computed count for it is genuinely zero, not a client-supplied figure.
        assert body["manifest"]["withheld_count"] == 0
        assert body["ledger_entry_id"]


def test_export_route_ignores_a_client_submitted_withheld_count_and_uses_the_working_set(
    api_env: None, keypair: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]
) -> None:
    """A caller-supplied count would let an artefact state that nothing was withheld when items
    were — an active misstatement of completeness (`06_DECISIONS.md` ADR-045). Seeds the real,
    Valkey-backed working set with one node this principal can see and one SECRET-classified node
    they cannot, so the true count is 1; the request body claims 0 anyway, via whatever extra JSON
    field a client that remembered the old field name might still send — proving there is no path
    from that field to the artefact at all, not merely that the honest path wins a tie."""
    private_key, _ = keypair
    headers = _bearer(private_key)
    investigation_id = asyncio.run(_write_investigation(PRINCIPAL))
    node_id = asyncio.run(_write_node(owning_unit=PRINCIPAL.org_unit))

    visible = _membership_node(owning_unit=PRINCIPAL.org_unit)
    hidden = _membership_node(owning_unit="unit-9", classification="SECRET")
    asyncio.run(_seed_working_set(investigation_id, [visible, hidden]))

    from services.api.app import app

    with TestClient(app) as client:
        response = client.post(
            f"/v1/investigations/{investigation_id}/export",
            headers=headers,
            json={
                "artefact_kind": "subgraph",
                "items": [{"id": node_id, "kind": "node", "handling": _PLACEHOLDER_HANDLING}],
                "resolution_threshold": 0.95,
                "withheld_count": 0,  # ignored — ExportRequest has no such field
            },
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["manifest"]["withheld_count"] == 1


def test_export_route_blocks_a_consult_originator_item_and_names_it_over_http(
    api_env: None, keypair: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]
) -> None:
    private_key, _ = keypair
    headers = _bearer(private_key)
    investigation_id = asyncio.run(_write_investigation(PRINCIPAL))
    s2_node_id = asyncio.run(_write_node(owning_unit=PRINCIPAL.org_unit, sanitisation_code="S2"))

    from services.api.app import app

    with TestClient(app) as client:
        response = client.post(
            f"/v1/investigations/{investigation_id}/export",
            headers=headers,
            json={
                "artefact_kind": "subgraph",
                "items": [{"id": s2_node_id, "kind": "node", "handling": _PLACEHOLDER_HANDLING}],
                "resolution_threshold": 0.95,
                "withheld_count": 0,
            },
        )
        assert response.status_code == 422, response.text
        body = response.json()
        assert body["error"] == "override_required"
        assert body["blocked"][0]["id"] == s2_node_id
        assert body["blocked"][0]["reason"] == "consult_originator"


def test_export_route_ignores_a_client_submitted_node_handling_and_uses_the_live_graph(
    api_env: None, keypair: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]
) -> None:
    """The client submits an innocuous-looking `handling` block for a node that is, in the live
    graph, actually `S2` — proving the route never trusts the client's own submission for a node
    (only for the disclosed edge-only limitation does it), the same guarantee `test_export.py`'s
    own cross-session-access test already proves at the function level, here proven through the
    real HTTP boundary."""
    private_key, _ = keypair
    headers = _bearer(private_key)
    investigation_id = asyncio.run(_write_investigation(PRINCIPAL))
    s2_node_id = asyncio.run(_write_node(owning_unit=PRINCIPAL.org_unit, sanitisation_code="S2"))

    from services.api.app import app

    with TestClient(app) as client:
        response = client.post(
            f"/v1/investigations/{investigation_id}/export",
            headers=headers,
            json={
                "artefact_kind": "subgraph",
                # The client's own submitted handling claims no sanitisation code at all.
                "items": [{"id": s2_node_id, "kind": "node", "handling": _PLACEHOLDER_HANDLING}],
                "resolution_threshold": 0.95,
                "withheld_count": 0,
            },
        )
        # Still blocked — the route re-fetched the real S2 handling from the graph.
        assert response.status_code == 422, response.text
        assert response.json()["error"] == "override_required"


def test_exports_ledger_route_requires_the_compliance_role(
    api_env: None, keypair: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]
) -> None:
    private_key, _ = keypair
    headers = _bearer(private_key)  # PRINCIPAL carries no roles at all

    from services.api.app import app

    with TestClient(app) as client:
        response = client.get("/v1/exports", headers=headers)
        assert response.status_code == 403, response.text
        assert response.json()["error"] == "compliance_role_required"
