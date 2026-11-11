"""*Admin › Models*' two engine kinds for the `cloud-platform` profile (`06_DECISIONS.md` ADR-135
Amendment 4, P11 part 1): **the client's own OpenAI-compatible AI gateway** (its address, and a
token or the namespace's IAM role) and **Bedrock in London by the namespace's IAM role**, with no
key stored for either IAM-role kind.

P1's and P2's access and key tests, run on both kinds, through the real app, the real right check
and the real logger, against the stand-in gateway whose client gateway and Bedrock refuse as the
real services do (`tests/adapters/model_litellm/test_stand_in_engine_kinds.py`, rule 15):

- rule 4: every `/v1/admin/models` route refuses a principal without `manage_models`, for an engine
  of each kind;
- the key: a planted token for the client gateway appears in no response, log, audit entry, models
  file or gateway row in plaintext; a key sent for an IAM-role engine is refused and kept nowhere;
- **no stored key** for an IAM-role engine: no credential, no key in its entries, no key record,
  and nothing the command line moves;
- signing in another way, or changing the kind, removes the engine's key as an address change does;
- the engine's own limits (P2) on both kinds.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from harness.apply import ApplyFailed, _keys_for_new_providers, provider_secret_lines
from harness.render import model_engines_env, model_key_variables
from pydantic import ValidationError
from services.api.app import app, get_principal
from services.api.config import DeploymentModels
from services.api.model_admin import (
    GatewayAdmin,
    InMemoryModelAdminAudit,
    Installed,
    ModelAdmin,
    ModelSettingsFile,
)
from services.api.model_keys import move_keys
from services.api.model_routing import routes_from_env

from adapters.model_litellm.stand_in import (
    StandInBedrock,
    StandInClientGateway,
    StandInGateway,
)
from schemas.deployment import ModelProviderConfig, ModelsConfig, OspreyConfig
from schemas.domain import Principal
from tests.services.api.test_model_engines import _config as engines_config

MASTER = "sk-stand-in-master"
TOKEN = "gw-token-for-the-client-gateway"
PLANTED = "gw-PLANTED-model-token-Q7Z4-do-not-leak"
BASE = "https://ai-gateway.client.example/v1"
ROLE = "arn:aws:iam::000000000000:role/osprey-gateway"
CLAUDE = "anthropic.claude-3-haiku-20240307-v1:0"

ADMIN = Principal(id="admin-1", clearance="OFFICIAL", org_unit="u", roles=["osprey-admin"])
ANALYST = Principal(id="analyst-1", clearance="OFFICIAL", org_unit="u", roles=["analyst"])
EVERY_OTHER_ADMIN_RIGHT = Principal(
    id="admin-2",
    clearance="OFFICIAL",
    org_unit="u",
    roles=[
        f"right:{r}"
        for r in ("administer_system", "manage_people", "manage_geospatial", "read_audit")
    ],
)

GATEWAY = {"name": "acme", "label": "Acme AI gateway", "kind": "gateway", "api_base": BASE,
           "roles": {"extraction": "gpt-4o-mini"}}  # fmt: skip
GATEWAY_BY_ROLE = {**GATEWAY, "auth": "iam_role"}
BEDROCK = {"name": "bedrock", "label": "Bedrock (London)", "kind": "bedrock",
           "roles": {"extraction": CLAUDE}}  # fmt: skip
KINDS = {"gateway": GATEWAY, "bedrock": BEDROCK}

#: Every name a stored key could go by in a LiteLLM entry.
KEY_PARAMS = {"api_key", "litellm_credential_name", "aws_access_key_id", "aws_secret_access_key",
              "aws_session_token", "aws_bearer_token_bedrock"}  # fmt: skip


class World:
    def __init__(
        self, tmp_path: Path, *, role: str | None = ROLE,
        declared: list[ModelProviderConfig] | None = None,
    ) -> None:  # fmt: skip
        self.folder = tmp_path / "model-settings"
        self.gateway = StandInGateway(
            master_key=MASTER,
            salt_key="salt-one",
            providers={},
            client_gateways={BASE: StandInClientGateway(TOKEN, frozenset({"gpt-4o-mini"}))},
            bedrock=StandInBedrock(frozenset({ROLE}), frozenset({CLAUDE})),
            workload_role=role,
        )
        self.audit = InMemoryModelAdminAudit()
        self.installed = Installed(
            providers=declared or [], defaults={}, key_present={}, local_only=False,
            sendable=["O"],
            locals={"extraction": "qwen2.5:7b-instruct", "vision": None, "transcription": None,
                    "embedding": "all-minilm:22m-l6-v2-fp16"},
        )  # fmt: skip
        http = httpx.AsyncClient(base_url="http://litellm:4000", transport=self.gateway.transport(),
                                 headers={"Authorization": f"Bearer {MASTER}"})  # fmt: skip
        self.admin = ModelAdmin(
            installed=self.installed, settings_file=ModelSettingsFile(self.folder),
            gateway=GatewayAdmin(http), audit=self.audit,
        )  # fmt: skip

    def params(self, model_name: str) -> dict[str, str]:
        entry = self.gateway.entry_for(model_name)
        assert entry is not None, model_name
        return self.gateway.stored_params(entry)

    def models_file(self) -> str:
        path = self.folder / "models.yaml"
        return path.read_text() if path.exists() else ""


@pytest.fixture
def world(tmp_path: Path) -> Iterator[World]:
    w = World(tmp_path)
    app.state.model_admin = w.admin
    app.dependency_overrides[get_principal] = lambda: ADMIN
    yield w
    app.dependency_overrides.clear()
    app.state.model_admin = None


@pytest.fixture
def client(world: World) -> TestClient:
    return TestClient(app)


def _as(principal: Principal) -> None:
    app.dependency_overrides[get_principal] = lambda: principal


# --- the schema ---------------------------------------------------------------------------------


def test_bedrock_signs_in_by_the_namespace_s_role_in_london_by_default() -> None:
    engine = ModelProviderConfig.model_validate(BEDROCK)
    assert (engine.auth, engine.region, engine.api_base) == ("iam_role", "eu-west-2", None)
    assert ModelProviderConfig.model_validate(GATEWAY).auth == "key"


@pytest.mark.parametrize(
    ("body", "words"),
    [
        ({**BEDROCK, "auth": "key"}, "IAM role"),
        ({**BEDROCK, "region": "us-east-1"}, "London"),
        ({**BEDROCK, "region": "eu-west-1"}, "London"),
        ({**BEDROCK, "api_base": BASE}, "address"),
        ({**GATEWAY, "api_base": None}, "address"),
        ({**GATEWAY, "region": "eu-west-2"}, "region"),
        ({"name": "gemini", "roles": {"extraction": "gemini-2.5-flash"}, "auth": "iam_role"},
         "IAM role"),
        ({**GATEWAY, "kind": "sagemaker"}, "kind"),
        ({**BEDROCK, "kind": "provider"}, "only as Amazon Bedrock in London"),
        ({**BEDROCK, "kind": "gateway", "api_base": BASE, "auth": "key"},
         "only as Amazon Bedrock in London"),
        (GATEWAY_BY_ROLE, "token for now"),
    ],
    ids=["bedrock-by-key", "bedrock-us", "bedrock-ireland", "bedrock-address",
         "gateway-no-address", "gateway-region", "provider-by-role", "unknown-kind",
         "bedrock-named-provider", "bedrock-named-gateway", "gateway-by-role-held"],
)  # fmt: skip
def test_the_schema_refuses_each_shape_the_profile_does_not_allow(
    body: dict[str, Any], words: str
) -> None:
    with pytest.raises(ValidationError) as refused:
        ModelProviderConfig.model_validate(body)
    assert words in str(refused.value)


# --- rule 4, on both kinds ----------------------------------------------------------------------


def _models_routes() -> list[APIRoute]:
    return [
        r for r in app.routes if isinstance(r, APIRoute) and r.path.startswith("/v1/admin/models")
    ]


@pytest.mark.parametrize("kind", sorted(KINDS))
@pytest.mark.parametrize(
    "principal", [ANALYST, EVERY_OTHER_ADMIN_RIGHT], ids=["analyst", "every-other-admin-right"]
)
def test_every_models_route_refuses_a_principal_without_manage_models_for_each_kind(
    client: TestClient, world: World, principal: Principal, kind: str
) -> None:
    body = KINDS[kind]
    _as(ADMIN)
    assert client.post("/v1/admin/models/engines", json={"provider": body}).status_code == 200
    seen_before, audited_before = len(world.gateway.seen), len(world.audit.entries)
    _as(principal)
    answers = {
        f"{sorted(r.methods)[0]} {r.path}": client.request(
            sorted(r.methods)[0], r.path.replace("{name}", str(body["name"])),
            json={"provider": body, "key": PLANTED, "defaults": {}},
        )
        for r in _models_routes()
    }  # fmt: skip
    assert len(answers) == 11
    assert {k: v.status_code for k, v in answers.items() if v.status_code != 403} == {}
    assert all(v.json()["detail"]["right"] == "manage_models" for v in answers.values())
    # Nothing reached the gateway or the audit for the refused principal.
    assert len(world.gateway.seen) == seen_before
    assert len(world.audit.entries) == audited_before


# --- the client's own gateway by its token ------------------------------------------------------


def test_the_gateway_s_token_reaches_its_credential_and_is_sent_to_its_address_alone(
    client: TestClient, world: World
) -> None:
    assert client.post("/v1/admin/models/engines", json={"provider": GATEWAY}).status_code == 200
    assert client.put("/v1/admin/models/engines/acme/key", json={"key": TOKEN}).status_code == 200
    params = world.params("acme/gpt-4o-mini")
    assert params["model"] == "openai/gpt-4o-mini"
    assert params["api_base"] == BASE
    assert params["litellm_credential_name"] == "osprey-acme"
    assert "api_key" not in params
    assert world.gateway.credential("osprey-acme") == TOKEN
    assert client.post("/v1/admin/models/engines/acme/test").json()["outcome"] == "ok"
    assert world.gateway.sent == [(BASE, TOKEN)]
    assert world.gateway.credential_reads == 0


def test_a_planted_token_appears_in_no_response_log_audit_file_or_gateway_row(
    client: TestClient, world: World, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    bodies: list[str] = []

    def send(method: str, path: str, **kw: Any) -> httpx.Response:
        response = client.request(method, path, **kw)
        bodies.append(f"{response.status_code} {response.text} {dict(response.headers)}")
        return response

    assert send("POST", "/v1/admin/models/engines", json={"provider": GATEWAY}).status_code == 200
    key = "/v1/admin/models/engines/acme/key"
    assert send("PUT", key, json={"key": PLANTED}).status_code == 200
    # The client's gateway refuses it, and its refusal echoes part of it.
    assert send("POST", "/v1/admin/models/engines/acme/test").json()["outcome"] == "key_refused"
    assert send("PUT", key, json={"key": PLANTED}).status_code == 200  # a rotation
    for malformed in ({"key": PLANTED, "extra": 1}, {"key": PLANTED * 300}, {"secret": PLANTED}):
        assert send("PUT", key, json=malformed).status_code == 422
    # A token pasted into the address or the label is refused, never echoed.
    for field in ("api_base", "contract_reference"):
        assert send("PUT", "/v1/admin/models/engines/acme",
                    json={"provider": {**GATEWAY, field: PLANTED}}).status_code == 422  # fmt: skip
    send("GET", "/v1/admin/models")
    send("GET", "/v1/admin/models/history")
    assert send("DELETE", key).status_code == 200

    fragments = (PLANTED, PLANTED[:12], "Q7Z4", "leak")
    seen = {
        "responses": "\n".join(bodies),
        "logs": "\n".join(r.getMessage() + repr(r.args) for r in caplog.records),
        "audit": json.dumps([e.model_dump(mode="json") for e in world.audit.entries]),
        "models file": world.models_file(),
        "gateway rows": "\n".join(world.gateway.raw_rows()),
    }
    leaked = {where: f for where, text in seen.items() for f in fragments if f in text}
    assert leaked == {}
    # It did reach the client's gateway, so the test is not passing by sending nothing.
    assert any(PLANTED[-4:] in line for line in world.gateway.log)


# --- no stored key for the IAM-role kinds -------------------------------------------------------


def test_an_iam_role_engine_keeps_no_key_anywhere(
    client: TestClient, world: World, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    body = BEDROCK
    name = str(body["name"])
    assert client.post("/v1/admin/models/engines", json={"provider": body}).status_code == 200
    refused = client.put(f"/v1/admin/models/engines/{name}/key", json={"key": PLANTED})
    assert refused.status_code == 409
    assert "IAM role" in refused.json()["detail"]["detail"]
    model = next(iter(body["roles"].values()))
    params = world.params(f"{name}/{model}")
    assert set(params) & KEY_PARAMS == set()
    assert world.gateway._creds == {}  # noqa: SLF001 - no credential of any name
    view = client.get("/v1/admin/models").json()
    assert view["engines"][0]["key_state"] == "iam_role"
    assert "keys: {}" in world.models_file()
    # Refused and audited, but the key is nowhere.
    audit = json.dumps([e.model_dump(mode="json") for e in world.audit.entries])
    logs = [r.getMessage() for r in caplog.records]
    text = "\n".join([refused.text, world.models_file(), json.dumps(params), audit,
                      *world.gateway.raw_rows(), *logs])  # fmt: skip
    assert "Q7Z4" not in text
    assert any(e.action == "key_set" and e.outcome.startswith("refused") for e in
               world.audit.entries)  # fmt: skip
    # Nor is a key removed for it: there is none (the reviewer's item 11).
    removed = client.delete(f"/v1/admin/models/engines/{name}/key")
    assert removed.status_code == 409 and "IAM role" in removed.json()["detail"]["detail"]
    # And the call to Bedrock carried no key of any kind.
    assert client.post(f"/v1/admin/models/engines/{name}/test").json()["outcome"] == "ok"
    assert [k for where, k in world.gateway.sent if where.startswith("bedrock:")] == [None]


def test_bedrock_answers_through_the_gateway_pod_s_role_in_london(
    client: TestClient, world: World
) -> None:
    client.post("/v1/admin/models/engines", json={"provider": BEDROCK})
    params = world.params(f"bedrock/{CLAUDE}")
    assert params["model"] == f"bedrock/{CLAUDE}"
    assert params["aws_region_name"] == "eu-west-2"
    result = client.post("/v1/admin/models/engines/bedrock/test").json()
    assert result["outcome"] == "ok"
    assert world.gateway.signed == [(ROLE, "eu-west-2")]
    # Offered to analysts with no key (the role is its sign-in).
    assert world.admin.routes().engines["bedrock"].key_present is True


def test_bedrock_with_no_role_on_the_gateway_pod_says_so_in_words_of_the_role(
    tmp_path: Path,
) -> None:
    w = World(tmp_path, role=None)
    asyncio.run(w.admin.add_engine("admin-1", ModelProviderConfig.model_validate(BEDROCK)))
    result = asyncio.run(w.admin.test("admin-1", "bedrock"))
    assert result.outcome == "key_refused"
    assert "IAM role" in result.words and "key" not in result.words.lower().replace("keep", "")


def test_an_engine_s_kind_is_fixed_once_added_so_its_contract_never_moves_to_another(
    client: TestClient, world: World
) -> None:
    contracted = {**GATEWAY, "privacy_contract": True, "contract_reference": "DPA 2026/07"}
    client.post("/v1/admin/models/engines", json={"provider": contracted})
    client.put("/v1/admin/models/engines/acme/key", json={"key": TOKEN})
    to_bedrock = {**contracted, "kind": "bedrock", "api_base": None, "auth": None}
    for other in ({**contracted, "kind": "provider"}, to_bedrock):
        edited = client.put("/v1/admin/models/engines/acme", json={"provider": other})
        assert edited.status_code == 422, edited.text
    engine = world.admin.settings.providers[0]
    assert (engine.kind, engine.privacy_contract) == ("gateway", True)
    assert world.gateway.credential("osprey-acme") == TOKEN


def test_a_refused_reconcile_after_an_address_change_says_no_key_rather_than_key_set(
    client: TestClient, world: World
) -> None:
    client.post("/v1/admin/models/engines", json={"provider": GATEWAY})
    client.put("/v1/admin/models/engines/acme/key", json={"key": TOKEN})
    world.gateway.refuse_model_new = 500
    moved = {**GATEWAY, "api_base": "https://ai-gateway-2.client.example/v1"}
    assert client.put("/v1/admin/models/engines/acme", json={"provider": moved}).status_code == 502
    assert world.gateway.credential("osprey-acme") is None
    assert world.admin.key_state("acme") == "none"


def test_the_command_line_moves_no_key_for_an_iam_role_engine(world: World) -> None:
    asyncio.run(world.admin.add_engine("admin-1", ModelProviderConfig.model_validate(BEDROCK)))
    moved, skipped = asyncio.run(move_keys(world.admin, [f"BEDROCK={PLANTED}"], "cli:root"))
    assert (moved, skipped) == ([], ["bedrock"])
    assert world.gateway._creds == {}  # noqa: SLF001
    assert "Q7Z4" not in world.models_file()


def test_a_declared_iam_role_engine_gets_its_entries_at_start_with_no_models_file(
    tmp_path: Path,
) -> None:
    w = World(tmp_path, declared=[ModelProviderConfig.model_validate(BEDROCK)])

    async def started() -> object:
        await w.admin.start()
        await w.admin.close()
        return await w.admin.test("admin-1", "bedrock")

    result = asyncio.run(started())
    assert w.gateway.entry_for(f"bedrock/{CLAUDE}") is not None
    assert getattr(result, "outcome", None) == "ok"
    assert not (w.folder / "models.yaml").exists()


# --- P2: each engine's own limits, on both kinds ------------------------------------------------


@pytest.mark.parametrize("kind", sorted(KINDS))
def test_each_kind_s_limits_are_its_own_gateway_key_s(
    client: TestClient, world: World, kind: str
) -> None:
    body = KINDS[kind]
    name, model = str(body["name"]), next(iter(body["roles"].values()))
    client.post("/v1/admin/models/engines", json={"provider": body})
    limits = {"requests_per_minute": 5, "tokens_per_minute": 900, "budget_tokens": 10_000,
              "budget_period": "day"}  # fmt: skip
    path = f"/v1/admin/models/engines/{name}/limits"
    assert client.put(path, json={"limits": limits}).status_code == 200
    keys = [k for k in world.gateway.virtual_keys().values()
            if k.metadata.get("osprey_engine") == name]  # fmt: skip
    assert len(keys) == 1
    assert (keys[0].rpm_limit, keys[0].tpm_limit, keys[0].max_budget) == (5, 900, 10_000)
    assert keys[0].models == [f"{name}/{model}"]


# --- an engine declared in osprey.yaml: the render, the install, the Conduit --------------------


LOCALS = DeploymentModels("qwen2.5:7b-instruct", None, None, None)


def _declared() -> OspreyConfig:
    models = ModelsConfig.model_validate({
        "local_only": False, "sendable_handling_codes": ["P"],
        "providers": [BEDROCK, GATEWAY, {"name": "gemini", "roles": {"extraction": "g-flash"}}],
    })  # fmt: skip
    return engines_config().model_copy(update={"models": models})


def _rendered(config: OspreyConfig) -> dict[str, str]:
    return dict(line.split("=", 1) for line in model_engines_env(config))


def test_the_render_tells_the_conduit_each_engine_s_kind_and_how_it_signs_in() -> None:
    config = _declared()
    installed = Installed.from_env(LOCALS, _rendered(config))
    assert installed.providers == config.models.providers


def test_an_iam_role_engine_has_no_key_variable_and_is_offered_with_none() -> None:
    config = _declared()
    assert set(model_key_variables(config)) == {"acme", "gemini"}
    routes = routes_from_env(LOCALS, _rendered(config))
    assert {n: e.key_present for n, e in routes.engines.items()} == {
        "bedrock": True, "acme": False, "gemini": False,
    }  # fmt: skip


def test_the_install_asks_no_key_for_an_iam_role_engine() -> None:
    config = _declared()
    given = {"OSPREY_MODEL_KEY_ACME": TOKEN, "OSPREY_MODEL_KEY_GEMINI": "g-key"}
    lines = provider_secret_lines(config, given)
    assert "BEDROCK" not in lines and "OSPREY_MODEL_KEY_ACME" in lines
    asked: list[str] = []

    def ask(question: str) -> str:
        asked.append(question)
        return ""

    found = _keys_for_new_providers(config, {}, {}, ask)
    assert not any("Bedrock" in q for q in asked) and "OSPREY_MODEL_KEY_BEDROCK" not in found
    # A keyed engine with no key still stops the install, in words naming its variable.
    with pytest.raises(ApplyFailed, match="OSPREY_MODEL_KEY_GEMINI"):
        provider_secret_lines(config, {"OSPREY_MODEL_KEY_ACME": TOKEN})


def _with_held_bedrock_key(tmp_path: Path) -> OspreyConfig:
    from tests.harness.test_model_engines import _config as harness_config

    models = ModelsConfig.model_validate({
        "local_only": False, "sendable_handling_codes": ["P"],
        "providers": [BEDROCK, {"name": "gemini", "roles": {"extraction": "g-flash"}}],
    })  # fmt: skip
    return harness_config(tmp_path, models)


def test_an_iam_role_engine_s_held_key_is_blanked_in_every_compose_service(tmp_path: Path) -> None:
    import yaml
    from harness.render import render

    from tests.harness.test_model_engines import _fake_resolver

    compose = yaml.safe_load(render(_with_held_bedrock_key(tmp_path), resolver=_fake_resolver)
                             .artefacts["compose.yaml"])  # fmt: skip
    for name, service in compose["services"].items():
        if "env_file" in service or name == "litellm":
            environment = service.get("environment") or {}
            assert environment.get("OSPREY_MODEL_KEY_BEDROCK") == "", name
    gateway = compose["services"]["litellm"]["environment"]
    assert gateway["OSPREY_MODEL_KEY_GEMINI"] == "${OSPREY_MODEL_KEY_GEMINI:-}"


def test_an_iam_role_engine_s_held_key_is_blanked_in_every_cluster_workload() -> None:
    from tests.harness.test_cluster_render import _containers, cluster_config, values_for

    models = {"local_only": False, "sendable_handling_codes": ["P"], "providers": [BEDROCK]}
    values = values_for(cluster_config(models=models))
    readers = [c for c in _containers(values) if c.get("envFrom")]
    assert readers
    for container in readers:
        blanked = {e["name"]: e.get("value") for e in container.get("env", [])}
        assert blanked.get("OSPREY_MODEL_KEY_BEDROCK") == "", container["name"]


def test_the_install_page_offers_no_key_field_for_an_iam_role_engine(tmp_path: Path) -> None:
    from harness.install_page import _providers

    draft = tmp_path / "osprey.yaml"
    config = _declared()
    draft.write_text(yaml_dump(config), encoding="utf-8")
    assert {p["name"] for p in _providers(draft)} == {"acme", "gemini"}


def yaml_dump(config: OspreyConfig) -> str:
    import yaml

    return yaml.safe_dump(config.model_dump(mode="json", exclude_none=True), sort_keys=False)
