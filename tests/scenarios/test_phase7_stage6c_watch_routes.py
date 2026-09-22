"""Phase 7 Stage 6c's own new HTTP surface — `POST/GET /v1/hotlists`, `POST/GET /v1/monitors`,
`GET /v1/alerts`, `POST /v1/alerts/{id}/jump` — proven the same way Phase 6a's own exit criterion
was (`test_phase6a_glass_surfaces.py`'s own module docstring has the full reasoning for the
pattern): real FastAPI app, real ArcadeDB/Postgres/Valkey, real HTTP, one principal.

**What this does not attempt.** A real ingest driving the synchronous evaluation wiring
(`app.py`'s `run_studio_recipe`) through the full recipe-publish pipeline — `evaluate_hotlists_
for_entry`/`evaluate_monitors_for_entry` are already proven, exhaustively, against real
Postgres/ArcadeDB/Valkey in `tests/services/api/test_evaluation.py`; reproducing that same proof a
second time through the recipe-publish machinery (`tests/ingest/test_studio_publish_pipeline.py`'s
own, separately-proven concern) would cost real test-infrastructure work for no new coverage —
this file's own job is the route surface those functions did not have until this stage: creating a
hotlist/monitor over HTTP, and reading/jumping from an alert over HTTP, neither of which existed
before this stage regardless of how the alert underneath was produced.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from services.api.alerts import AlertStore
from services.api.config import PostgresConfig
from tests.conftest import default_claims, sign_token

from adapters.graph_arcadedb.adapter import GraphArcadeDBAdapter
from adapters.graph_arcadedb.client import ArcadeDBClient, ArcadeDBConfig
from conduit_common.identity import new_id
from ontology.handling import load_uk_le_scheme
from ontology.loader import load_default_ontology
from schemas.domain import (
    Alert,
    AlertMode,
    Handling,
    NodeWrite,
    Principal,
    Provenance,
    ProvenanceState,
    SourceRef,
)

PRINCIPAL = Principal(id="analyst-1", clearance="OFFICIAL", org_unit="unit-1")


@pytest.fixture
def api_env(jwks_url: str) -> Iterator[None]:
    """`test_phase6a_glass_surfaces.py`'s own fixture, unchanged — `ApiConfig.from_env()` reads
    these at lifespan startup, not import time."""
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


def _bearer(private_key: rsa.RSAPrivateKey) -> dict[str, str]:
    token = sign_token(private_key, default_claims())
    return {"Authorization": f"Bearer {token}"}


def _endpoint_write(
    value_normalised: str, *, owning_unit: str, classification: str = "OFFICIAL"
) -> NodeWrite:
    now = datetime.now(UTC)
    return NodeWrite(
        id=new_id(),
        type="Endpoint",
        properties={"value_normalised": value_normalised},
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


async def _write_node(value_normalised: str, *, owning_unit: str, classification: str) -> str:
    """Writes directly against the same real, persistent `ospreyflow` ArcadeDB database the
    running `TestClient` app's own lifespan connects to — `test_phase6a_glass_surfaces.py`'s own
    `_fetch_node_json` docstring has the full reasoning for why this, not `arcadedb_adapter`
    (which provisions its own, separate database the running app would never see)."""
    client = ArcadeDBClient(ArcadeDBConfig.from_env(database="ospreyflow"))
    try:
        graph = GraphArcadeDBAdapter(client, load_uk_le_scheme())
        await graph.apply_schema(load_default_ontology())
        tx = await graph.begin_transaction()
        write = _endpoint_write(
            value_normalised, owning_unit=owning_unit, classification=classification
        )
        (node_id,) = await graph.upsert_nodes([write], tx)
        await graph.commit_transaction(tx)
        return node_id
    finally:
        await client.aclose()


async def _write_alert(alert: Alert) -> None:
    store = await AlertStore.connect(PostgresConfig.from_env().dsn)
    try:
        await store.save(alert)
    finally:
        await store.close()


def test_hotlist_create_and_list_round_trip(
    api_env: None, keypair: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]
) -> None:
    private_key, _ = keypair
    headers = _bearer(private_key)
    identifier = f"+44-route-{new_id()}"

    from services.api.app import app

    with TestClient(app) as client:
        created = client.post(
            "/v1/hotlists",
            headers=headers,
            json={"identifier": identifier, "review_date": "2027-01-01"},
        )
        assert created.status_code == 201, created.text
        body = created.json()
        assert body["identifier"] == identifier
        assert body["owner_id"] == PRINCIPAL.id
        assert body["status"] == "active"

        listed = client.get("/v1/hotlists", headers=headers)
        assert listed.status_code == 200, listed.text
        assert any(h["id"] == body["id"] for h in listed.json()["hotlists"])


def test_monitor_create_requires_owning_the_pattern_first(
    api_env: None, keypair: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]
) -> None:
    private_key, _ = keypair
    headers = _bearer(private_key)

    from services.api.app import app

    with TestClient(app) as client:
        saved = client.post(
            "/v1/patterns/save",
            headers=headers,
            json={
                "pattern_id": None,
                "name": "Stage 6c route fixture",
                "definition": {
                    "nodes": [
                        {"var": "p", "entity_type": "Person"},
                        {"var": "e", "entity_type": "Endpoint"},
                    ],
                    "edges": [{"edge_type": "USES", "from_var": "p", "to_var": "e"}],
                },
            },
        )
        assert saved.status_code == 201, saved.text
        pattern_id = saved.json()["pattern_id"]

        created = client.post(
            "/v1/monitors", headers=headers, json={"pattern_id": pattern_id}
        )
        assert created.status_code == 201, created.text
        monitor = created.json()
        assert monitor["pattern_id"] == pattern_id
        assert monitor["status"] == "active"

        listed = client.get("/v1/monitors", headers=headers)
        assert any(m["id"] == monitor["id"] for m in listed.json()["monitors"])

        # A pattern this principal does not own collapses to the same 404 `PatternNotFoundError`
        # every other route in this codebase already gives — existence-leak discipline, not a
        # distinguishable 403.
        rejected = client.post(
            "/v1/monitors", headers=headers, json={"pattern_id": f"no-such-pattern-{new_id()}"}
        )
        assert rejected.status_code == 404, rejected.text


def test_alert_list_redacts_a_full_alert_whose_evidence_has_since_become_unavailable(
    api_env: None, keypair: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]
) -> None:
    """`06_DECISIONS.md` ADR-039's own re-check, proven at the route layer specifically — the task
    this stage was built under is explicit that the API-layer test already exists
    (`test_alerts.py`) and this stage needs the render-layer equivalent. `AlertView`'s own
    redaction (`watch_routes.py`) is that equivalent on the Conduit side; the Glass component
    itself gets its own vitest proof separately."""
    private_key, _ = keypair
    headers = _bearer(private_key)

    node_id = asyncio.run(
        _write_node(f"+44-{new_id()}", owning_unit=PRINCIPAL.org_unit, classification="OFFICIAL")
    )
    alert = Alert(
        id=new_id(),
        rule_id=f"hotlist:{new_id()}",
        owner_id=PRINCIPAL.id,
        mode=AlertMode.FULL,
        referent_node_ids=[node_id],
        investigation_id=None,
        created_at=datetime.now(UTC),
    )
    asyncio.run(_write_alert(alert))

    from services.api.app import app

    with TestClient(app) as client:
        before = client.get(f"/v1/alerts/{alert.id}", headers=headers)
        assert before.status_code == 200, before.text
        assert before.json()["evidence_available"] is True
        assert before.json()["referent_node_ids"] == [node_id]

    # Revoke: supersede the node with a replacement this principal can no longer see — the same
    # revocation shape `test_alerts.py::test_alert_evidence_is_unreadable_after_referent_access_
    # is_revoked` already establishes.
    async def _revoke() -> None:
        client_ = ArcadeDBClient(ArcadeDBConfig.from_env(database="ospreyflow"))
        try:
            graph = GraphArcadeDBAdapter(client_, load_uk_le_scheme())
            await graph.apply_schema(load_default_ontology())
            tx = await graph.begin_transaction()
            await graph.supersede_node(
                node_id,
                _endpoint_write(f"+44-{new_id()}", owning_unit="unit-2", classification="SECRET"),
                tx,
            )
            await graph.commit_transaction(tx)
        finally:
            await client_.aclose()

    asyncio.run(_revoke())

    with TestClient(app) as client:
        after_list = client.get("/v1/alerts", headers=headers)
        assert after_list.status_code == 200, after_list.text
        matching = [a for a in after_list.json()["alerts"] if a["id"] == alert.id]
        assert len(matching) == 1
        assert matching[0]["evidence_available"] is False
        assert matching[0]["referent_node_ids"] == []

        after_get = client.get(f"/v1/alerts/{alert.id}", headers=headers)
        assert after_get.json()["evidence_available"] is False
        assert after_get.json()["referent_node_ids"] == []


def test_jump_branches_a_new_investigation_seeded_with_the_alerts_entities(
    api_env: None, keypair: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]
) -> None:
    """`08_ACCEPTANCE_SCENARIOS.md` B14: "The new working set contains the alert's entities and a
    link to the originating investigation." Two referents, one made unreadable before the jump —
    the task's own question ("what happens when a referent became unreadable between the alert
    firing and the jump") answered as a partial success, not a silent drop nor a hard failure."""
    private_key, _ = keypair
    headers = _bearer(private_key)

    readable_node_id = asyncio.run(
        _write_node(f"+44-{new_id()}", owning_unit=PRINCIPAL.org_unit, classification="OFFICIAL")
    )
    unreadable_node_id = asyncio.run(
        _write_node(f"+44-{new_id()}", owning_unit="unit-2", classification="SECRET")
    )

    from services.api.app import app

    with TestClient(app) as client:
        # `investigations.branched_from` is a real foreign key (confirmed directly, not assumed —
        # a synthetic id with no backing row was rejected the first time this test was written) —
        # "the investigation the triggering ingest was in" needs a real `Investigation` row, so one
        # is created here exactly as an ingest route would, not synthesised.
        origin = client.post("/v1/investigations", headers=headers)
        assert origin.status_code == 201, origin.text
        origin_investigation_id = origin.json()["id"]

        alert = Alert(
            id=new_id(),
            rule_id=f"hotlist:{new_id()}",
            owner_id=PRINCIPAL.id,
            mode=AlertMode.FULL,
            referent_node_ids=[readable_node_id, unreadable_node_id],
            investigation_id=origin_investigation_id,
            created_at=datetime.now(UTC),
        )
        asyncio.run(_write_alert(alert))

        jumped = client.post(f"/v1/alerts/{alert.id}/jump", headers=headers)
        assert jumped.status_code == 201, jumped.text
        result = jumped.json()
        assert result["seeded_count"] == 1
        assert result["unreadable_count"] == 1
        assert result["investigation"]["branched_from"] == origin_investigation_id

        membership = client.get(
            f"/v1/investigations/{result['investigation']['id']}", headers=headers
        )
        assert membership.status_code == 200, membership.text


def test_app_lifespan_does_not_reopen_the_unbounded_pool_ceiling(
    api_env: None, keypair: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]
) -> None:
    """Phase 7 Stage 6c's own first carry-over — a regression guard for the connection-pool
    ceiling found and fixed while writing this stage's own real-service tests, not merely a
    one-off manual reproduction. `asyncpg.create_pool`'s own default (`min_size=10`) times all ten
    Postgres-backed stores `app.py`'s lifespan opens was already within reach of Postgres's own
    `max_connections=100` before this stage; adding three more at that default (`Hotlist`/
    `Monitor`/`AlertStore`) pushed a real lifespan over it, reproduced directly as
    `asyncpg.exceptions.TooManyConnectionsError`. All ten stores are now explicitly bounded
    (`hotlists.py::HotlistStore.connect`'s own comment has the arithmetic;
    `07_BUILD_PLAN.md`'s own Stage 6c entry has the full reconciliation against Postgres's
    configured limit and more than one Conduit instance).

    This test measures the actual delta in live Postgres connections one full `TestClient(app)`
    lifespan opens — measured directly at `12` with today's ten bounded stores, not assumed.
    Threshold `20`: generous enough to absorb that measurement's own minor run-to-run variance,
    tight enough that any *one* store regressing to `asyncpg.create_pool`'s own unbounded default
    (`min_size=10` — at least `+8` over this stage's own smallest bound) pushes the delta past it
    and fails this test. Confirmed both directions while writing it, not assumed from the
    arithmetic alone: reverting one store's own bound reproduces the failure; restoring it passes
    again."""
    import asyncpg

    async def _connection_count() -> int:
        conn = await asyncpg.connect(dsn=PostgresConfig.from_env().dsn)
        try:
            return await conn.fetchval("SELECT count(*) FROM pg_stat_activity")
        finally:
            await conn.close()

    before = asyncio.run(_connection_count())

    from services.api.app import app

    with TestClient(app):
        during = asyncio.run(_connection_count())

    # A generous ceiling, not today's own precise sum (`~13` at `min_size`) — real headroom for
    # this test to stay green as individual stores' own `min_size` is tuned, while still catching
    # the exact class of regression this stage found: a new store, or a reverted bound, opening
    # ten more connections than budgeted at once.
    assert during - before < 20, (
        f"app.py's lifespan opened {during - before} new Postgres connections (before={before}, "
        f"during={during}) — a bounded-pool regression, the same class this stage's own "
        "TooManyConnectionsError finding fixed"
    )
