"""Phase 7 Stage 6c's own new HTTP surface — `POST/GET /v1/hotlists`, `POST/GET /v1/monitors`,
`GET /v1/alerts`, `POST /v1/alerts/{id}/jump` — proven the same way Phase 6a's own exit criterion
was (`test_phase6a_glass_surfaces.py`'s own module docstring has the full reasoning for the
pattern): real FastAPI app, real ArcadeDB/Postgres/Valkey, real HTTP, one principal.

**A real ingest driving the synchronous evaluation wiring, through the full recipe-publish
pipeline, cross-analyst — Phase 8 Stage 1 (`06_DECISIONS.md` ADR-043).** This file's own docstring
used to disclaim this as out of scope ("would cost real test-infrastructure work for no new
coverage") — true while every producer only ever resolved its own requester's own principal; false
once `PrincipalResolver.resolve_for_owner` (OAuth2 Token Exchange) made a genuinely different
owner's own principal reachable, which is exactly the new coverage
`test_a_hotlist_owned_by_one_analyst_fires_from_a_different_analysts_own_ingest` below exists to
prove — `evaluate_hotlists_for_entry` alone (already proven in `test_evaluation.py`) cannot show
the route-level wiring (`app.py`'s new `principal_resolver` dependency, `_evaluate_watches_best_
effort`'s own async `_principal_for_owner`) actually reaches it for a second principal.
"""

from __future__ import annotations

import asyncio
import csv
import subprocess
from collections.abc import Iterator
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from services.api.alerts import AlertStore
from services.api.app import get_recipes_repo_root
from services.api.config import PostgresConfig
from services.api.datasets import Dataset, PostgresDatasetStore
from services.api.hotlists import HotlistStore
from services.api.studio_publish import build_recipe, write_and_commit_recipe
from services.api.studio_recipes import StudioRecipeStore
from tests.conftest import (
    TOKEN_EXCHANGE_CLIENT_ID,
    TOKEN_EXCHANGE_CLIENT_SECRET,
    TokenExchangeRegistry,
    default_claims,
    sign_token,
)
from tests.services.api.case_dataset import dataset_for, give_case_its_dataset

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
from schemas.ingest import FieldBinding, RecipeEntity, RowTemplate

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


def _case(client: TestClient, headers: dict[str, str]) -> str:
    """ADR-099 Amendment 3: watches and alerts are asked of a case, and read its datasets; the case
    reads the dataset the nodes below are written in, as a load into it would put them."""
    created = client.post("/v1/investigations", headers=headers)
    assert created.status_code == 201, created.text
    case_id = str(created.json()["id"])
    asyncio.run(give_case_its_dataset(case_id, PRINCIPAL))
    return case_id


def _endpoint_write(
    value_normalised: str,
    *,
    owning_unit: str,
    classification: str = "OFFICIAL",
    datasets: list[str] | None = None,
    document_id: str = "fixture",
) -> NodeWrite:
    now = datetime.now(UTC)
    return NodeWrite(
        id=new_id(),
        type="Endpoint",
        properties={"value_normalised": value_normalised},
        provenance=Provenance(
            state=ProvenanceState.ASSERTED,
            sources=[SourceRef(document_id=document_id, locator="row 3", excerpt_hash="")],
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
        datasets=[dataset_for(PRINCIPAL)] if datasets is None else datasets,
    )


async def _write_node(
    value_normalised: str,
    *,
    owning_unit: str,
    classification: str,
    datasets: list[str] | None = None,
    document_id: str = "fixture",
) -> str:
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
            value_normalised,
            owning_unit=owning_unit,
            classification=classification,
            datasets=datasets,
            document_id=document_id,
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
        case = _case(client, headers)
        created = client.post(
            f"/v1/investigations/{case}/hotlists",
            headers=headers,
            json={"identifier": identifier, "review_date": "2027-01-01"},
        )
        assert created.status_code == 201, created.text
        body = created.json()
        assert body["identifier"] == identifier
        assert body["owner_id"] == PRINCIPAL.id
        assert body["status"] == "active"

        listed = client.get(f"/v1/investigations/{case}/hotlists", headers=headers)
        assert listed.status_code == 200, listed.text
        assert any(h["id"] == body["id"] for h in listed.json()["hotlists"])


def test_monitor_create_requires_owning_the_pattern_first(
    api_env: None, keypair: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]
) -> None:
    private_key, _ = keypair
    headers = _bearer(private_key)

    from services.api.app import app

    with TestClient(app) as client:
        case = _case(client, headers)
        saved = client.post(
            f"/v1/investigations/{case}/patterns/save",
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
            f"/v1/investigations/{case}/monitors", headers=headers, json={"pattern_id": pattern_id}
        )
        assert created.status_code == 201, created.text
        monitor = created.json()
        assert monitor["pattern_id"] == pattern_id
        assert monitor["status"] == "active"
        # ADR-099 Amendment 3: the monitor watches its pattern's dataset.
        assert monitor["dataset_id"] == saved.json()["dataset_id"] == dataset_for(PRINCIPAL)

        listed = client.get(f"/v1/investigations/{case}/monitors", headers=headers)
        assert any(m["id"] == monitor["id"] for m in listed.json()["monitors"])

        # A pattern this principal does not own collapses to the same 404 `PatternNotFoundError`
        # every other route in this codebase already gives — existence-leak discipline, not a
        # distinguishable 403.
        rejected = client.post(
            f"/v1/investigations/{case}/monitors",
            headers=headers,
            json={"pattern_id": f"no-such-pattern-{new_id()}"},
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
        case = _case(client, headers)
        before = client.get(f"/v1/investigations/{case}/alerts/{alert.id}", headers=headers)
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
        after_list = client.get(f"/v1/investigations/{case}/alerts", headers=headers)
        assert after_list.status_code == 200, after_list.text
        matching = [a for a in after_list.json()["alerts"] if a["id"] == alert.id]
        assert len(matching) == 1
        assert matching[0]["evidence_available"] is False
        assert matching[0]["referent_node_ids"] == []

        after_get = client.get(f"/v1/investigations/{case}/alerts/{alert.id}", headers=headers)
        assert after_get.json()["evidence_available"] is False
        assert after_get.json()["referent_node_ids"] == []


def test_the_alert_routes_name_a_nodes_sources_only_within_the_cases_datasets(
    api_env: None, keypair: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]
) -> None:
    """ADR-130 Amendment 1, through the real app and the real case scoping (`get_principal`), for
    both `list_alerts_route` and `get_alert_route`: a node that belongs to a dataset the case does
    not read says its type and label and `sources_withheld`, and no file name, row or count; a
    node wholly inside the case's datasets names its file. When the case then reads both datasets,
    the same node is named."""
    private_key, _ = keypair
    headers = _bearer(private_key)
    other = f"{dataset_for(PRINCIPAL)}-other-{new_id()}"
    inside_file = f"in/inside-{new_id()}.csv"
    shared_file = f"in/shared-{new_id()}.csv"

    inside_id = asyncio.run(
        _write_node(
            f"+44-{new_id()}",
            owning_unit=PRINCIPAL.org_unit,
            classification="OFFICIAL",
            document_id=inside_file,
        )
    )
    shared_id = asyncio.run(
        _write_node(
            f"+44-{new_id()}",
            owning_unit=PRINCIPAL.org_unit,
            classification="OFFICIAL",
            datasets=[dataset_for(PRINCIPAL), other],
            document_id=shared_file,
        )
    )
    alert = Alert(
        id=new_id(),
        rule_id=f"hotlist:{new_id()}",
        owner_id=PRINCIPAL.id,
        mode=AlertMode.FULL,
        referent_node_ids=[inside_id, shared_id],
        investigation_id=None,
        created_at=datetime.now(UTC),
        dataset_id=dataset_for(PRINCIPAL),
    )
    asyncio.run(_write_alert(alert))

    from services.api.app import app

    def _both_views(client: TestClient, case: str) -> list[dict[str, object]]:
        listed = client.get(f"/v1/investigations/{case}/alerts", headers=headers)
        assert listed.status_code == 200, listed.text
        (from_list,) = [a for a in listed.json()["alerts"] if a["id"] == alert.id]
        single = client.get(f"/v1/investigations/{case}/alerts/{alert.id}", headers=headers)
        assert single.status_code == 200, single.text
        return [from_list, single.json()]

    with TestClient(app) as client:
        case = _case(client, headers)
        for view in _both_views(client, case):
            inside, shared = view["fired_on"]
            assert inside["sources_withheld"] is False
            assert inside["files"][0]["name"] == inside_file.rsplit("/", 1)[-1]
            assert inside["files"][0]["row"] == 3
            assert shared["sources_withheld"] is True
            assert shared["files"] == [] and shared["more_files"] == 0
            assert shared["type"] == "Endpoint" and shared["label"]
            assert shared_file.rsplit("/", 1)[-1] not in str(view)

        # The case now reads both datasets: the same node is named.
        async def _read_both() -> None:
            store = await PostgresDatasetStore.connect(PostgresConfig.from_env().dsn)
            try:
                await store.add(
                    Dataset(
                        id=other,
                        name="Route test data, other",
                        owning_unit=PRINCIPAL.org_unit,
                        created_at=datetime.now(UTC),
                        created_by="test",
                    )
                )
                await store.set_for_case(case, [dataset_for(PRINCIPAL), other], PRINCIPAL)
            finally:
                await store.close()

        asyncio.run(_read_both())
        for view in _both_views(client, case):
            _, shared = view["fired_on"]
            assert shared["sources_withheld"] is False
            assert shared["files"][0]["name"] == shared_file.rsplit("/", 1)[-1]


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
        origin_investigation_id = _case(client, headers)

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

        jumped = client.post(
            f"/v1/investigations/{origin_investigation_id}/alerts/{alert.id}/jump", headers=headers
        )
        assert jumped.status_code == 201, jumped.text
        result = jumped.json()
        assert result["seeded_count"] == 1
        # ADR-124: no figure for what the jumper may not read.
        assert "unreadable_count" not in result
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
    (`hotlists.py::HotlistStore.connect`'s own comment has the arithmetic and the full
    reconciliation against Postgres's configured limit and more than one Conduit instance).

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
    #
    # Re-measured 7 October 2026 at 22, every store bounded: the lifespan now opens about twenty
    # Postgres stores, not ten (ADR-080 to ADR-099 added them), so `< 20` failed on bounded stores
    # alone and no longer told a regression from growth. 26 keeps the purpose: one store back at
    # the unbounded default adds about nine (shown failing, the questions store reverted), and the
    # threshold moves again only on a new measurement, recorded here.
    #
    # 15 October 2026: 30, with 28 stores, every one bounded — growth again, not a regression, and
    # a fixed ceiling could not tell them apart a second time. The budget is now read from the code:
    # each pool's declared `min_size` (a pool with none counts as 1 here and opens 10, so it
    # overshoots by about 9), plus 5 for run-to-run variance.
    budget, undeclared = _declared_pool_minimums()
    assert undeclared == [], f"pools with no min_size, so asyncpg's default of 10: {undeclared}"
    assert during - before <= budget + 5, (
        f"app.py's lifespan opened {during - before} new Postgres connections (before={before}, "
        f"during={during}) — a bounded-pool regression, the same class this stage's own "
        "TooManyConnectionsError finding fixed"
    )


def _declared_pool_minimums() -> tuple[int, list[str]]:
    """The sum of every Conduit Postgres pool's declared `min_size`, and the pools declaring none."""
    import re

    from tools.layout import CORE

    total, undeclared = 0, []
    for path in sorted((CORE / "services" / "api").rglob("*.py")):
        for call in re.finditer(r"create_pool\(([^)]*)\)", path.read_text(encoding="utf-8")):
            declared = re.search(r"min_size=(\d+)", call.group(1))
            total += int(declared.group(1)) if declared else 1
            if not declared:
                undeclared.append(path.name)
    return total, undeclared


def test_a_pool_with_no_declared_minimum_is_named() -> None:
    """The budget's own red case, in the shape a store writes it: one pool left at the default."""
    import re

    line = "pool = await asyncpg.create_pool(dsn=dsn)"
    assert re.search(r"min_size=(\d+)", re.search(r"create_pool\(([^)]*)\)", line).group(1)) is None  # type: ignore[union-attr]
    total, undeclared = _declared_pool_minimums()
    assert total >= 20 and undeclared == []


# --- Phase 8 Stage 1 exit criterion (06_DECISIONS.md ADR-043) --------------------------------


@pytest.fixture
def api_env_with_exchange(jwks_url: str, token_exchange_url: str) -> Iterator[None]:
    """`api_env` above, extended with `06_DECISIONS.md` ADR-043's own token-exchange
    configuration — kept as its own fixture rather than changing `api_env` itself, since every
    other test in this file deliberately runs with token exchange unconfigured (the pre-Stage-1
    default, `PrincipalResolver.resolve_for_owner`'s own disclosed fallback)."""
    import os

    previous = {
        key: os.environ.get(key)
        for key in (
            "OIDC_JWKS_URL",
            "OIDC_ALGORITHMS",
            "ARCADEDB_DATABASE",
            "OIDC_TOKEN_EXCHANGE_URL",
            "OIDC_TOKEN_EXCHANGE_CLIENT_ID",
            "OIDC_TOKEN_EXCHANGE_CLIENT_SECRET",
        )
    }
    os.environ["OIDC_JWKS_URL"] = jwks_url
    os.environ["OIDC_ALGORITHMS"] = "RS256"
    os.environ["ARCADEDB_DATABASE"] = "ospreyflow"
    os.environ["OIDC_TOKEN_EXCHANGE_URL"] = token_exchange_url
    os.environ["OIDC_TOKEN_EXCHANGE_CLIENT_ID"] = TOKEN_EXCHANGE_CLIENT_ID
    os.environ["OIDC_TOKEN_EXCHANGE_CLIENT_SECRET"] = TOKEN_EXCHANGE_CLIENT_SECRET
    try:
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _row_template() -> RowTemplate:
    return RowTemplate(
        entities=[
            RecipeEntity(
                ref="a",
                pole_class="object",
                type="Endpoint",
                match_on="value_normalised",
                on_match="reference",
                properties={
                    "value_normalised": FieldBinding(field="a_party"),
                    "endpoint_kind": FieldBinding(literal="msisdn"),
                },
            )
        ]
    )


async def _publish_a_recipe_touching(
    identifier: str,
    *,
    author: Principal,
    approver: Principal,
    tmp_path: Path,
    git_repo: Path,
    numbers: list[str] | None = None,
) -> str:
    """Real Postgres (`StudioRecipeStore`), a real throwaway git commit — the identical shape
    `tests/ingest/test_studio_publish_pipeline.py`'s own `_publish_a_verified_recipe` already
    establishes, reused rather than re-derived, since recipe publishing itself is that file's own
    proven concern, not this test's."""
    store = await StudioRecipeStore.connect(PostgresConfig.from_env().dsn)
    try:
        csv_path = tmp_path / "stage1.csv"
        with csv_path.open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["a_party"])
            writer.writeheader()
            writer.writerows([{"a_party": number} for number in (numbers or [identifier])])

        draft = await store.create_draft(
            author,
            label="stage1-cross-analyst",
            connector_profile="generic-csv",
            source_location=str(csv_path),
            handling={
                "classification": "OFFICIAL",
                "handling_code": "P",
                "originator": author.org_unit,
                "owning_unit": author.org_unit,
            },
            legal_basis="RIPA s22 acquisition — authorisation 2026/0114",
        )
        draft = await store.update_row_template(
            draft.recipe_id, author, row_template=_row_template(), unmapped_fields=[]
        )
        await store.mark_verified(draft.recipe_id, draft.version, now=datetime.now(UTC))
        draft = await store.get(draft.recipe_id)

        ontology = load_default_ontology()
        built = build_recipe(
            draft,
            ontology_version=ontology.version,
            pack_versions={},
            schedule_cron=None,
            schedule_watch=None,
        )
        git_path = await write_and_commit_recipe(built, repo_root=git_repo)
        published = await store.publish(
            draft.recipe_id,
            approver,
            ontology_version=ontology.version,
            pack_versions={},
            git_path=git_path,
            schedule_cron=None,
            schedule_watch=None,
            now=datetime.now(UTC),
        )
        return published.recipe_id
    finally:
        await store.close()


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
    return repo


def test_a_hotlist_owned_by_one_analyst_fires_from_a_different_analysts_own_ingest(
    api_env_with_exchange: None,
    keypair: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey],
    token_exchange_registry: TokenExchangeRegistry,
    tmp_path: Path,
    git_repo: Path,
) -> None:
    """This phase's own named exit criterion — currently red by
    construction until this stage's own mechanism exists, turned green here. Real FastAPI app,
    real ArcadeDB/Postgres/Valkey, real HTTP, real recipe-publish pipeline, two real principals —
    A (the hotlist's own owner) and B (whose own ingest triggers evaluation), neither one the
    other. Before Stage 1, `_principal_for_owner` returned `None` for any owner but the requester;
    B's own ingest could never reach A's own hotlist. Now `principal_resolver.resolve_for_owner`
    exchanges for A's own principal, and `record_match` — always called with the *owner's* own
    principal, never the unscoped matcher (`06_DECISIONS.md` ADR-038's own addendum) — can finally
    fire for A."""
    private_key, _ = keypair
    identifier = f"+44-cross-analyst-{new_id()[:10]}"
    review_date = date(2027, 1, 1)

    analyst_a = Principal(id="analyst-a", clearance="OFFICIAL", org_unit="unit-1")
    author_approver = Principal(
        id="analyst-b",
        clearance="OFFICIAL",
        org_unit="unit-1",
        roles=["source_author", "source_approver", "loader"],
    )
    token_exchange_registry.register(
        "analyst-a",
        {
            "sub": "analyst-a",
            "clearance": "OFFICIAL",
            "org_unit": "unit-1",
            "receivable_handling_codes": [],
            "roles": ["analyst"],
        },
    )

    async def _seed() -> str:
        hotlist_store = await HotlistStore.connect(PostgresConfig.from_env().dsn)
        try:
            await hotlist_store.create(analyst_a, identifier=identifier, review_date=review_date)
        finally:
            await hotlist_store.close()
        return await _publish_a_recipe_touching(
            identifier,
            author=author_approver,
            approver=author_approver,
            tmp_path=tmp_path,
            git_repo=git_repo,
        )

    # A's own hotlist, then a real published recipe authored/approved/run by B — the loader who
    # never owns A's hotlist. Real Postgres for both, the same stores every other test in this
    # file already uses.
    recipe_id = asyncio.run(_seed())

    from services.api.app import app

    app.dependency_overrides[get_recipes_repo_root] = lambda: git_repo
    # ADR-112: the old `loader` role runs pipelines only; one who opens a case and runs a recipe in
    # it is a Data Engineer.
    token_b = sign_token(private_key, default_claims(sub="analyst-b", roles=["data_engineer"]))
    try:
        with TestClient(app) as client:
            inv_response = client.post(
                "/v1/investigations", headers={"Authorization": f"Bearer {token_b}"}
            )
            assert inv_response.status_code == 201, inv_response.text
            investigation_id = inv_response.json()["id"]

            run_response = client.post(
                f"/v1/investigations/{investigation_id}/ingest/recipes/{recipe_id}/run",
                headers={"Authorization": f"Bearer {token_b}"},
                json={},
            )
            assert run_response.status_code == 200, run_response.text
    finally:
        app.dependency_overrides.pop(get_recipes_repo_root, None)

    async def _read_alerts() -> list[Alert]:
        alert_store = await AlertStore.connect(PostgresConfig.from_env().dsn)
        try:
            return await alert_store.list_authorized(analyst_a)
        finally:
            await alert_store.close()

    alerts = asyncio.run(_read_alerts())

    assert any(a.rule_id.startswith("hotlist:") for a in alerts), (
        "no alert reached analyst A from analyst B's own ingest — the cross-analyst gap "
        "Phase 8 Stage 1 exists to close is still open"
    )


# --- ADR-127 decisions 7 and 8 (S7): a hotlist sees what a run touches, in its canonical form ----

import random  # noqa: E402

_EARLIER_FILE = "incoming/pid_earlier_load.csv"


def _drama_number() -> tuple[str, str]:
    """An Ofcom drama-range number (synthetic by rule 9), typed in national form and as E.164, drawn
    from 07700 900300-900399: the PID reserves 900600-900899 and the two numbers its search relies
    on, and no other file may write them (`test_pid_plan.py`'s J2)."""
    last = random.randint(300, 399)
    return f"07700 900{last:03d}", f"+447700900{last:03d}"


async def _preload_endpoints(values: list[str]) -> dict[str, str]:
    """What an earlier load (R5) leaves behind: each number an `Endpoint` in the case's dataset,
    naming the file it was loaded from. Returns value -> node id."""
    client = ArcadeDBClient(ArcadeDBConfig.from_env(database="ospreyflow"))
    try:
        graph = GraphArcadeDBAdapter(client, load_uk_le_scheme())
        await graph.apply_schema(load_default_ontology())
        writes = []
        for value in values:
            write = _endpoint_write(
                value, owning_unit=PRINCIPAL.org_unit, classification="OFFICIAL"
            )
            write = write.model_copy(
                update={
                    "properties": {"value_normalised": value, "endpoint_kind": "msisdn"},
                    "provenance": write.provenance.model_copy(
                        update={
                            "sources": [
                                SourceRef(
                                    document_id=_EARLIER_FILE, locator="row 1", excerpt_hash=""
                                )
                            ]
                        }
                    ),
                }
            )
            writes.append(write)
        tx = await graph.begin_transaction()
        ids = await graph.upsert_nodes(writes, tx)
        await graph.commit_transaction(tx)
        return dict(zip(values, ids, strict=True))
    finally:
        await client.aclose()


async def _sources_of(node_id: str) -> list[str]:
    from services.resolve.trigger import service_principal

    client = ArcadeDBClient(ArcadeDBConfig.from_env(database="ospreyflow"))
    try:
        graph = GraphArcadeDBAdapter(client, load_uk_le_scheme())
        node = await graph.get_node(node_id, service_principal(load_uk_le_scheme()))
        assert node is not None
        return [str(source.document_id) for source in node.provenance.sources]
    finally:
        await client.aclose()


def _run_through_the_route(
    *,
    private_key: rsa.RSAPrivateKey,
    git_repo: Path,
    recipe_id: str,
    loader: Principal,
) -> dict[str, object]:
    from services.api.app import app

    app.dependency_overrides[get_recipes_repo_root] = lambda: git_repo
    token = sign_token(private_key, default_claims(sub=loader.id, roles=["data_engineer"]))
    try:
        with TestClient(app) as client:
            headers = {"Authorization": f"Bearer {token}"}
            created = client.post("/v1/investigations", headers=headers)
            assert created.status_code == 201, created.text
            case = str(created.json()["id"])
            asyncio.run(give_case_its_dataset(case, loader))
            response = client.post(
                f"/v1/investigations/{case}/ingest/recipes/{recipe_id}/run",
                headers=headers,
                json={},
            )
            assert response.status_code == 200, response.text
            report: dict[str, object] = response.json()
            return report
    finally:
        app.dependency_overrides.pop(get_recipes_repo_root, None)


async def _alerts_of(owner: Principal) -> list[Alert]:
    store = await AlertStore.connect(PostgresConfig.from_env().dsn)
    try:
        return await store.list_authorized(owner)
    finally:
        await store.close()


async def _hotlists_for(owner: Principal, typed: list[str]) -> list[str]:
    """Hotlists made in the case's dataset, one per typed form; returns their ids."""
    store = await HotlistStore.connect(PostgresConfig.from_env().dsn)
    try:
        in_case = owner.model_copy(update={"datasets": [dataset_for(owner)]})
        return [
            (await store.create(in_case, identifier=form, review_date=date(2027, 1, 1))).id
            for form in typed
        ]
    finally:
        await store.close()


def _exchange_for(registry: TokenExchangeRegistry, owner: Principal) -> None:
    registry.register(
        owner.id,
        {
            "sub": owner.id,
            "clearance": owner.clearance,
            "org_unit": owner.org_unit,
            "receivable_handling_codes": [],
            "roles": ["analyst"],
        },
    )


def test_a_hotlist_on_a_number_a_run_only_references_fires_whether_typed_nationally_or_not(
    api_env_with_exchange: None,
    keypair: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey],
    token_exchange_registry: TokenExchangeRegistry,
    tmp_path: Path,
    git_repo: Path,
) -> None:
    """ADR-127 decisions 7 and 8 over the real app, ArcadeDB, Postgres and Valkey: the number is an
    `Endpoint` an earlier load wrote into the case's dataset, so the run matches it by reference and
    creates nothing. The hotlists are made in the case's dataset, one typed in national form and one
    in E.164, and both fire; the matched node names the file it was loaded from."""
    private_key, _ = keypair
    typed, canonical = _drama_number()
    analyst_a = Principal(id="analyst-a", clearance="OFFICIAL", org_unit="unit-1")
    loader = Principal(
        id="analyst-b",
        clearance="OFFICIAL",
        org_unit="unit-1",
        roles=["source_author", "source_approver", "loader"],
    )
    _exchange_for(token_exchange_registry, analyst_a)

    async def _seed() -> tuple[str, dict[str, str], list[str]]:
        preloaded = await _preload_endpoints([canonical])
        hotlists = await _hotlists_for(analyst_a, [typed, canonical])
        recipe_id = await _publish_a_recipe_touching(
            canonical, author=loader, approver=loader, tmp_path=tmp_path, git_repo=git_repo
        )
        return recipe_id, preloaded, hotlists

    recipe_id, preloaded, (national, plain) = asyncio.run(_seed())
    report = _run_through_the_route(
        private_key=private_key, git_repo=git_repo, recipe_id=recipe_id, loader=loader
    )
    assert report["nodes_created"] == 0 and report["nodes_referenced"] == 1, report
    assert "referenced_node_ids" not in report, "the ids are for the change stream alone"

    by_rule = {a.rule_id: a for a in asyncio.run(_alerts_of(analyst_a))}
    node_id = preloaded[canonical]
    for hotlist_id in (national, plain):
        alert = by_rule.get(f"hotlist:{hotlist_id}")
        assert alert is not None, f"no alert for hotlist {hotlist_id}: {sorted(by_rule)}"
        assert alert.referent_node_ids == [node_id]
    # Decision 8: the node the alert names says which file it was loaded from, through provenance.
    assert asyncio.run(_sources_of(node_id)) == [_EARLIER_FILE]


def test_a_run_referencing_over_two_hundred_nodes_still_alerts_for_the_two_hundred_and_fiftieth(
    api_env_with_exchange: None,
    keypair: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey],
    token_exchange_registry: TokenExchangeRegistry,
    tmp_path: Path,
    git_repo: Path,
) -> None:
    """Rule 2 over the real route: the run references 250 existing numbers and creates none; the
    hotlisted one is the last, past the 200 an evaluation used to stop at."""
    private_key, _ = keypair
    _, last = _drama_number()
    numbers = [f"+44-filler-{new_id()[:10]}" for _ in range(249)] + [last]
    analyst_a = Principal(id="analyst-a", clearance="OFFICIAL", org_unit="unit-1")
    loader = Principal(
        id="analyst-b",
        clearance="OFFICIAL",
        org_unit="unit-1",
        roles=["source_author", "source_approver", "loader"],
    )
    _exchange_for(token_exchange_registry, analyst_a)

    async def _seed() -> tuple[str, dict[str, str], str]:
        preloaded = await _preload_endpoints(numbers)
        (hotlist_id,) = await _hotlists_for(analyst_a, [last])
        recipe_id = await _publish_a_recipe_touching(
            last, author=loader, approver=loader, tmp_path=tmp_path, git_repo=git_repo,
            numbers=numbers,
        )  # fmt: skip
        return recipe_id, preloaded, hotlist_id

    recipe_id, preloaded, hotlist_id = asyncio.run(_seed())
    report = _run_through_the_route(
        private_key=private_key, git_repo=git_repo, recipe_id=recipe_id, loader=loader
    )
    assert report["nodes_created"] == 0 and report["nodes_referenced"] >= 250, report
    by_rule = {a.rule_id: a for a in asyncio.run(_alerts_of(analyst_a))}
    alert = by_rule.get(f"hotlist:{hotlist_id}")
    assert alert is not None, "the hotlisted number, the 250th of the run, raised nothing"
    assert alert.referent_node_ids == [preloaded[last]]
