"""The run API's caller and Operations' figures (`06_DECISIONS.md` ADR-141 decisions 3, 4, 7, 10
and 14; rules 3, 4 and 7).

- A service identity's token (Keycloak's shape for the client-credentials grant: `azp` the client,
  `preferred_username` `service-account-<client>`) names its client; a person's token, whatever
  its `azp`, is refused 403 and one not signed by the realm 401. Signed by the conftest's keypair
  and served from its JWKS, as `PrincipalResolver` is tested.
- The roll-up withholds a day's counts where one of its runs wrote a marking the reader may not
  view, names an owner and never serves an account id, even inside a refusal's words.
- `/v1/admin/operations/runs` refuses a reader without `operate_schedules` (403), and reads only
  the reader's unit unless they administer the system (the reach is passed to the ledger's own
  `WHERE`: rule 3).
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from services.api.app import (
    app,
    get_handling_scheme,
    get_principal,
    get_principal_names,
    get_recipe_runs,
    get_run_quotas,
    get_studio_recipes,
)
from services.api.operations_rollup import external_triggers, rollup_rows, scheduler_health
from services.api.recipe_runs import RecipeRun
from services.api.run_quotas import InMemoryQuotaStore, QuotaAlert
from services.api.service_identity import ServiceIdentityRefused, ServiceIdentityVerifier

from ontology.handling import load_uk_le_scheme
from principal_auth import OidcResolverSettings
from schemas.domain import Handling, Principal
from schemas.ingest import RunMetering
from schemas.operations import RunQuota
from tests.conftest import default_claims, sign_token

SCHEME = load_uk_le_scheme()
_OFFICIAL = Handling(
    classification="OFFICIAL", handling_code="P", originator="u", owning_unit="unit-1"
)
_SECRET = _OFFICIAL.model_copy(update={"classification": "SECRET"})
OWNER_ID = "acct-owner-8812"
READER = Principal(
    id="admin-1", clearance="OFFICIAL", org_unit="unit-1", roles=["right:operate_schedules"]
)


def _verifier(jwks_url: str) -> ServiceIdentityVerifier:
    return ServiceIdentityVerifier(
        OidcResolverSettings(oidc_jwks_url=jwks_url)  # type: ignore[call-arg]
    )


def test_a_service_identitys_token_names_its_client(
    jwks_url: str, keypair: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]
) -> None:
    key, _ = keypair
    claims = {
        "sub": "uuid-1",
        "azp": "Airflow-Prod",
        "preferred_username": "service-account-airflow-prod",
        "exp": default_claims()["exp"],
    }
    token = sign_token(key, claims)
    assert _verifier(jwks_url).client_of(token) == "Airflow-Prod"


@pytest.mark.parametrize(
    "claims",
    [{"azp": "airflow-prod", "preferred_username": "analyst-1"}, {}],
    # A person's token as the realm issues it may carry no `azp` at all: it is verified, so 403,
    # never 401 (found live at 667772b by `test_route_rights.py`'s no-role sweep).
    ids=["another-azp", "no-azp"],
)
def test_a_persons_token_is_never_taken_for_a_service_identitys(
    jwks_url: str, keypair: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey], claims: dict[str, str]
) -> None:
    key, _ = keypair
    token = sign_token(key, default_claims(**claims))
    with pytest.raises(ServiceIdentityRefused) as refused:
        _verifier(jwks_url).client_of(token)
    assert refused.value.status == 403


def test_a_token_the_realm_did_not_sign_is_401(jwks_url: str) -> None:
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    token = sign_token(
        other, {"sub": "x", "azp": "a", "preferred_username": "service-account-a",
                "exp": default_claims()["exp"]},
    )  # fmt: skip
    with pytest.raises(ServiceIdentityRefused) as refused:
        _verifier(jwks_url).client_of(token)
    assert refused.value.status == 401


def _run(**changes: object) -> RecipeRun:
    data: dict[str, object] = {
        "run_id": "run-1", "recipe_id": "rcp-1", "recipe_version": 2, "investigation_id": "case-1",
        "trigger": "schedule", "slot": None, "run_as": OWNER_ID, "source": _OFFICIAL,
        "started_at": datetime(2026, 11, 10, 9, tzinfo=UTC), "finished_at": None,
        "outcome": "succeeded", "rows_read": 10, "nodes_created": 1, "nodes_referenced": 0,
        "edges_created": 0, "rows_rejected": 0, "rows_held": 0, "load_id": None, "failure": None,
        "markings": [_OFFICIAL], "owning_unit": "unit-1", "dataset_id": "ds-1",
        "metering": RunMetering(wall_ms=40, rows_read=10, graph_writes=3),
    }  # fmt: skip
    data.update(changes)
    return RecipeRun.model_validate(data)


def test_a_days_counts_are_withheld_where_a_run_wrote_above_the_reader() -> None:
    runs = [_run(), _run(run_id="run-2", markings=[_SECRET])]
    (row,) = rollup_rows(runs, reader=READER, scheme=SCHEME, labels={"rcp-1": "Visits"})
    assert (row.runs, row.succeeded, row.wall_ms) == (2, 2, 80)
    assert (row.rows_read, row.graph_writes, row.withheld) == (None, None, True)
    (seen,) = rollup_rows([_run()], reader=READER, scheme=SCHEME, labels={"rcp-1": "Visits"})
    assert (seen.rows_read, seen.graph_writes, seen.withheld) == (10, 3, False)


def test_no_account_id_is_served_not_even_inside_a_refusals_words() -> None:
    refused = _run(
        outcome="refused",
        failure=f"the schedule's owner, {OWNER_ID}, no longer holds schedule_pipelines",
    )
    external = _run(run_id="run-3", trigger="external", triggered_by="airflow-prod")
    health = scheduler_health([refused], paused=[], names={OWNER_ID: "Sam Rowe"})
    triggers = external_triggers(
        [external], reader=READER, scheme=SCHEME, labels={}, names={OWNER_ID: "Sam Rowe"}
    )
    served = health.model_dump_json() + "".join(t.model_dump_json() for t in triggers)
    assert OWNER_ID not in served
    assert "the schedule's owner, Sam Rowe, no longer holds" in served
    assert triggers[0].ran_as_name == "Sam Rowe"
    unnamed = scheduler_health([refused], paused=[], names={})
    assert OWNER_ID not in unnamed.model_dump_json()


class _Ledger:
    """The ledger's `window`, filtering by unit as its `WHERE` does, over two units' runs."""

    def __init__(self) -> None:
        self.asked: list[list[str] | None] = []
        self.held = [
            _run(),
            _run(
                run_id="run-u2",
                recipe_id="rcp-unit-2-only",
                owning_unit="unit-2",
                dataset_id="ds-2",
            ),
        ]

    async def window(self, *, since: datetime, units: list[str] | None) -> list[RecipeRun]:
        self.asked.append(None if units is None else list(units))
        return [r for r in self.held if units is None or r.owning_unit in units]

    async def get(self, run_id: str) -> RecipeRun | None:
        return next((r for r in self.held if r.run_id == run_id), None)


class _Recipes:
    async def get(self, recipe_id: str) -> object:
        return type("R", (), {"label": "Visits"})()

    async def paused_of(self, units: list[str] | None) -> list[object]:
        """As the store's `WHERE`: unit-1's paused pipeline only to a reader of unit-1."""
        paused = type(
            "R", (), {"recipe_id": "rcp-1", "label": "Visits", "schedule_paused_reason": "by hand",
                      "owning_unit": "unit-1"},
        )()  # fmt: skip
        return [paused] if units is None or "unit-1" in units else []


class _Names:
    async def full_names(self, ids: object) -> dict[str, str]:
        return {OWNER_ID: "Sam Rowe"}


QUOTAS = InMemoryQuotaStore()


@pytest.fixture
def ledger() -> Iterator[_Ledger]:
    import asyncio

    QUOTAS.quotas.clear()
    QUOTAS.raised.clear()
    asyncio.run(QUOTAS.set(RunQuota(scope="unit", key="unit-1", runs_per_day=2)))
    asyncio.run(QUOTAS.set(RunQuota(scope="dataset", key="ds-1", runs_per_day=1)))
    asyncio.run(QUOTAS.raise_once(
        QuotaAlert("dataset", "ds-1", "2026-11-10", "unit-1's dataset reached its quota"),
        at=datetime(2026, 11, 10, tzinfo=UTC),
    ))  # fmt: skip
    found = _Ledger()
    app.dependency_overrides.update(
        {
            get_recipe_runs: lambda: found,
            get_studio_recipes: lambda: _Recipes(),
            get_principal_names: lambda: _Names(),
            get_handling_scheme: lambda: SCHEME,
            get_run_quotas: lambda: QUOTAS,
        }
    )
    yield found
    app.dependency_overrides.clear()


@pytest.mark.parametrize(
    ("roles", "status", "asked"),
    [
        (["right:operate_schedules"], 200, [["unit-1"]]),
        (["right:operate_schedules", "right:administer_system"], 200, [None]),
        (["right:administer_system"], 403, []),
    ],
    ids=["unit-only", "system-admin-every-unit", "no-operate-schedules"],
)
def test_operations_reads_the_readers_unit_unless_they_administer_the_system(
    ledger: _Ledger, roles: list[str], status: int, asked: list[list[str] | None]
) -> None:
    app.dependency_overrides[get_principal] = lambda: READER.model_copy(update={"roles": roles})
    answer = TestClient(app).get("/v1/admin/operations/runs", params={"days": 7})
    assert answer.status_code == status, answer.text
    assert ledger.asked == asked
    if status == 200:
        assert OWNER_ID not in answer.text


def test_a_reader_of_another_unit_sees_nothing_of_this_ones_runs(ledger: _Ledger) -> None:
    app.dependency_overrides[get_principal] = lambda: READER.model_copy(
        update={"org_unit": "unit-2"}
    )
    answer = TestClient(app).get("/v1/admin/operations/runs", params={"days": 7})
    assert answer.status_code == 200, answer.text
    assert "rcp-1" not in answer.text and "unit-1" not in answer.text
    assert [r["pipeline_id"] for r in answer.json()["rows"]] == ["rcp-unit-2-only"]
    body = answer.json()
    assert body["scheduler"]["paused"] == [] and body["quotas"] == [] and body["alerts"] == []
    assert "ds-1" not in answer.text


def test_a_reader_of_the_unit_sees_its_paused_pipeline_quotas_and_alert(ledger: _Ledger) -> None:
    app.dependency_overrides[get_principal] = lambda: READER
    body = TestClient(app).get("/v1/admin/operations/runs", params={"days": 7}).json()
    assert [p["pipeline_id"] for p in body["scheduler"]["paused"]] == ["rcp-1"]
    assert {(q["scope"], q["key"]) for q in body["quotas"]} == {
        ("unit", "unit-1"),
        ("dataset", "ds-1"),
    }
    assert [a["words"] for a in body["alerts"]] == ["unit-1's dataset reached its quota"]


class _Verifier:
    def __init__(self, client: str | None, status: int = 403) -> None:
        self.client, self.status = client, status

    def client_of(self, token: str) -> str:
        if self.client is None:
            raise ServiceIdentityRefused("not a service identity's", status=self.status)
        return self.client


@pytest.mark.parametrize(
    ("client", "expected"),
    [("airflow-prod", 200), ("another-client", 404), (None, 403)],
    ids=["the-trigger", "another-client", "a-person"],
)
def test_a_run_is_read_back_only_by_the_client_that_triggered_it(
    ledger: _Ledger, client: str | None, expected: int
) -> None:
    from services.api.app import get_principal_resolver

    ledger.held.append(
        _run(
            run_id="run-ext", trigger="external", triggered_by="airflow-prod", external_run_id="d:1"
        )
    )

    class _Owner:
        async def resolve_for_owner_detailed(self, owner_id: str) -> Principal:
            return READER

    app.state.service_identities = _Verifier(client)
    app.dependency_overrides[get_principal_resolver] = lambda: _Owner()
    try:
        answer = TestClient(app).get(
            "/v1/runs/run-ext", headers={"Authorization": "Bearer anything"}
        )
    finally:
        del app.state.service_identities
    assert answer.status_code == expected, answer.text
    if expected == 200:
        assert answer.json()["rows_read"] == 10 and answer.json()["external_run_id"] == "d:1"
    else:
        assert "rows_read" not in answer.text


def test_the_run_api_tells_no_account_id_and_no_failures_own_text() -> None:
    from services.api.external_runs import FAILED_WORDS, served_words

    refused = served_words(
        "refused", f"the schedule's owner, {OWNER_ID}, can no longer sign in", OWNER_ID
    )
    assert refused == "the schedule's owner, the pipeline's owner, can no longer sign in"
    failed = served_words("failed", "KeyError: 'SECRET-REF-31'", OWNER_ID)
    assert failed == FAILED_WORDS and "SECRET" not in failed
    assert served_words("succeeded", "x", OWNER_ID) is None


# --- The independent review of L1.7 (rules 3, 7 and 12) ----------------------------------------


@pytest.mark.parametrize("client", ["osprey-conduit", "osprey-glass", "osprey-dashboard-board"])
def test_a_client_the_deployment_registers_is_never_a_service_identity(
    jwks_url: str, keypair: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey], client: str
) -> None:
    """The deployment's own clients (`osprey-*`: the Conduit, the Glass, a report dashboard) have
    service accounts too; none is an orchestrator, so none may trigger a pipeline (rule 3)."""
    key, _ = keypair
    claims = {"sub": "uuid-2", "azp": client, "preferred_username": f"service-account-{client}",
              "exp": default_claims()["exp"]}  # fmt: skip
    with pytest.raises(ServiceIdentityRefused) as refused:
        _verifier(jwks_url).client_of(sign_token(key, claims))
    assert refused.value.status == 403


def test_a_service_identitys_token_is_401_on_a_persons_route(
    jwks_url: str, keypair: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]
) -> None:
    """ADR-141 Amendment 1 decision 3: a client-credentials token carries no clearance or unit, so
    every route but the run API's refuses it 401, as the realm signs it (rule 12)."""
    from services.api.auth import PrincipalResolver
    from services.api.config import ApiConfig, PostgresConfig, ValkeyConfig

    key, _ = keypair
    token = sign_token(key, {"sub": "uuid-1", "azp": "airflow-prod",
                             "preferred_username": "service-account-airflow-prod",
                             "exp": default_claims()["exp"]})  # fmt: skip
    config = ApiConfig(
        valkey=ValkeyConfig(host="localhost", port=6379, db=0),
        postgres=PostgresConfig(host="localhost", port=5432, user="x", password="x", database="x"),
        oidc_jwks_url=jwks_url, oidc_audience=None, oidc_issuer=None, oidc_algorithms=("RS256",),
        oidc_jwks_ttl_seconds=300.0, oidc_token_exchange_url=None,
        oidc_token_exchange_client_id=None, oidc_token_exchange_client_secret=None,
        supersede_job_degree_threshold=500, osprey_config_path="osprey.yaml",
        analytics_db_path=":memory:", hotlist_alert_policy="strict",
        export_manifest_policy="disclose",
    )  # type: ignore[arg-type]  # fmt: skip
    held = getattr(app.state, "principal_resolver", None)
    app.state.principal_resolver = PrincipalResolver(config)
    try:
        for path in ("/v1/admin/operations/runs", "/v1/investigations/inv-1/ingest/recipes"):
            answer = TestClient(app).get(path, headers={"Authorization": f"Bearer {token}"})
            assert answer.status_code == 401, (path, answer.text)
    finally:
        if held is None:
            del app.state.principal_resolver
        else:
            app.state.principal_resolver = held


class _Counted:
    """Every unit's runs into a dataset today, as the ledger counts them for a quota."""

    def __init__(self, today: int) -> None:
        self.today = today

    async def runs_since(self, **_: object) -> int:
        return self.today


def test_a_quota_refusal_tells_no_count_of_other_units_runs() -> None:
    """Rules 3 and 7, the strict reading: the refusal reaches the owner, the service identity and
    Operations' readers of one unit; the count is every unit's runs, so its words say only that the
    quota is used (only `administer_system` reads the number, on the quota bar)."""
    import asyncio

    from services.api.run_quotas import QuotaRefused, judge

    quotas = InMemoryQuotaStore()
    asyncio.run(quotas.set(RunQuota(scope="dataset", key="ds-1", runs_per_day=3)))
    with pytest.raises(QuotaRefused) as refused:
        asyncio.run(judge(quotas, _Counted(7), dataset_id="ds-1", owning_unit=None,
                          now=datetime(2026, 11, 10, 12, tzinfo=UTC)))  # fmt: skip
    words = str(refused.value)
    assert "the dataset's quota of 3 runs a day is used" in words
    assert "7" not in words and "today)" not in words


def test_a_budget_alert_tells_no_count_of_other_units_runs() -> None:
    import asyncio

    from services.api.run_quotas import judge

    quotas = InMemoryQuotaStore()
    asyncio.run(quotas.set(RunQuota(scope="dataset", key="ds-1", runs_per_day=10,
                                    alert_at_share=0.5)))  # fmt: skip
    asyncio.run(judge(quotas, _Counted(6), dataset_id="ds-1", owning_unit=None,
                      now=datetime(2026, 11, 10, 12, tzinfo=UTC)))  # fmt: skip
    (alert,) = quotas.raised.values()
    assert alert.words == ("The dataset's runs today reached 50% of its quota of 10 runs a day")
    assert "7" not in alert.words and "6" not in alert.words


@pytest.mark.parametrize(
    ("roles", "status"),
    [
        (["right:administer_system", "right:operate_schedules"], 200),
        (["right:administer_system"], 403),
        (["right:operate_schedules"], 403),
    ],
    ids=["both-rights", "no-operate-schedules", "no-administer-system"],
)
def test_setting_a_quota_needs_both_rights(roles: list[str], status: int) -> None:
    """`PUT …/operations/quotas/{scope}/{key}` (decision (f) of L1.7): a quota binds every unit's
    runs, so it needs `administer_system`; and it is Operations' screen, so `operate_schedules`."""
    from services.api.app import get_audit

    from tests.services.api.test_app import _FakeAudit

    quotas = InMemoryQuotaStore()
    app.dependency_overrides.update({
        get_principal: lambda: READER.model_copy(update={"roles": roles}),
        get_run_quotas: lambda: quotas,
        get_audit: lambda: _FakeAudit(),
    })  # fmt: skip
    try:
        answer = TestClient(app).put(
            "/v1/admin/operations/quotas/dataset/ds-1", json={"runs_per_day": 5}
        )
    finally:
        app.dependency_overrides.clear()
    assert answer.status_code == status, answer.text
    expected = {("dataset", "ds-1"): 5} if status == 200 else {}
    assert {k: q.runs_per_day for k, q in quotas.quotas.items()} == expected
