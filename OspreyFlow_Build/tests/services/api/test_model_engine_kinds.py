"""*Admin › Models*' two engine kinds for the `cloud-platform` profile (`06_DECISIONS.md` ADR-135
Amendment 4, as built: Amendment 7, P11 part 1): **the client's own OpenAI-compatible AI gateway**
(its address alone, and a token) and **Bedrock in London by the namespace's IAM role**, with no key
stored for an IAM-role engine.

**On that profile alone** (Amendment 7 decision 1, the orchestrator's ruling of 11 November): on
every other profile an engine is a provider by its name and key exactly as before Amendment 4, an
engine named `bedrock` included, and the two kinds are neither offered nor taken.

P1's and P2's access and key tests, run on both kinds, through the real app, the real right check
and the real logger, against the stand-in gateway whose client gateway and Bedrock refuse as the
real services do (`tests/adapters/model_litellm/test_stand_in_engine_kinds.py`, rule 15):

- rule 4: every `/v1/admin/models` route refuses a principal without `manage_models`, for an engine
  of each kind;
- the key: a planted token for the client gateway appears in no response, log, audit entry, models
  file or gateway row in plaintext, pasted where a real paste lands (the address's userinfo or
  query, the label, the reference); a key sent for an IAM-role engine is refused and kept nowhere;
- **no stored key** for an IAM-role engine: no credential, no key in its entries, no key record,
  nothing the command line moves, and no static AWS key on the gateway's workload;
- **London only**, the model's id included (Amendment 7 decision 2);
- *Test the connection*'s words for each refusal the two kinds give;
- changing the address removes the engine's key; the kind is fixed once added;
- the engine's own limits (P2) on both kinds.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
import yaml
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

import schemas.deployment as deployment
from adapters.model_litellm.stand_in import (
    StandInBedrock,
    StandInClientGateway,
    StandInGateway,
    StandInProvider,
)
from schemas.deployment import ModelProviderConfig, OspreyConfig
from schemas.domain import Principal
from tests.services.api.test_model_engines import _config as engines_config

MASTER = "sk-stand-in-master"
TOKEN = "gw-token-for-the-client-gateway"
PLANTED = "gw-PLANTED-model-token-Q7Z4-do-not-leak"
#: A gateway's token in the shape most gateways issue: a JWT (header, payload and signature, each
#: base64url, the first two starting `eyJ`, which is `{"` encoded). It holds dots, so a check for
#: "one unbroken run" never saw it (the orchestrator's round 2, item b).
JWT = ("eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJhY21lIiwic3ViIjoib3NwcmV5In0."
       "Q7Z4dGhpcy1pcy1hLXNpZ25hdHVyZS1mb3ItdGhlLXRlc3Q")  # fmt: skip
#: A lower-case token, as Azure API Management issues subscription keys (32 hex digits).
HEX = "0f3a9c7e5b1d4a8f2c6e9b0d7a3f5c1e"
#: A JWE (an encrypted JWT): five base64url parts, the second not `eyJ`.
JWE = (
    "eyJhbGciOiJSU0EtT0FFUCIsImVuYyI6IkEyNTZHQ00ifQ."
    "OKOawDo13gRp2ojaHV7LFpZcgV7T6DVZKTyKOMTYUmKoTCV."
    "48V1_ALb6US04U3b."
    "5eym8TW_c8SuK0ltJ3rpYIzOeDQz7TALvtu6UG9oMo4vpzs9tX_EFShS8iB7j6ji."
    "XFBoMYUZodetZdvTiFvSkQ"
)
BASE = "https://ai-gateway.client.example/v1"
ROLE = "arn:aws:iam::000000000000:role/osprey-gateway"
CLAUDE = "anthropic.claude-3-haiku-20240307-v1:0"
GEMINI_KEY = "g-key-for-the-stand-in-0001"
CLOUD = "cloud-platform"
#: Every profile but `cloud-platform`.
OTHER_PROFILES = ["local-lite", "small", "cluster"]

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
GEMINI = {"name": "gemini", "roles": {"extraction": "g-flash"}}
#: An engine named `bedrock` as every profile took it before Amendment 4: LiteLLM's Bedrock provider
#: by its key (ADR-135 decision 1).
BEDROCK_BY_KEY = {"name": "bedrock", "roles": {"extraction": CLAUDE}}
KINDS = {"gateway": GATEWAY, "bedrock": BEDROCK}

#: Every name a stored key could go by in a LiteLLM entry.
KEY_PARAMS = {"api_key", "litellm_credential_name", "aws_access_key_id", "aws_secret_access_key",
              "aws_session_token", "aws_bearer_token_bedrock"}  # fmt: skip
#: The static AWS credentials botocore would prefer to the pod's own identity, were any given.
STATIC_AWS = ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN")


def _gateway_role_as_rendered() -> str | None:
    """The role the gateway's pod holds as the real cloud-platform render gives it: `ROLE` only if
    its `litellm` workload runs under a service account. Rendered with a Bedrock engine, the only
    one whose calls the gateway's own role signs: P11 part 2 gives it its own account then (rule
    15's second example: the stand-in's gateway holds what the real one holds, no more)."""
    values = _cloud_values(BEDROCK)
    gateway = next(w for w in values["workloads"] if w["name"] == "litellm")
    return ROLE if gateway.get("serviceAccountName") else None


class World:
    def __init__(
        self, tmp_path: Path, *, role: str | None | object = "as-rendered",
        declared: list[ModelProviderConfig] | None = None, profile: str = CLOUD,
        key_present: dict[str, bool] | None = None,
    ) -> None:  # fmt: skip
        if role == "as-rendered":
            role = _gateway_role_as_rendered()
        self.folder = tmp_path / "model-settings"
        self.client_gateway = StandInClientGateway(TOKEN, frozenset({"gpt-4o-mini"}))
        self.bedrock = StandInBedrock(frozenset({ROLE}), frozenset({CLAUDE}))
        self.gateway = StandInGateway(
            master_key=MASTER,
            salt_key="salt-one",
            providers={
                "gemini": StandInProvider(GEMINI_KEY, frozenset({"g-flash"})),
                # Before Amendment 4 (and on every profile but cloud-platform), `bedrock` is a
                # provider reached by its key, like any other.
                "bedrock": StandInProvider(GEMINI_KEY, frozenset({CLAUDE})),
            },
            client_gateways={BASE: self.client_gateway},
            bedrock=self.bedrock if profile == CLOUD else None,
            workload_role=role,
        )
        self.audit = InMemoryModelAdminAudit()
        self.installed = Installed(
            providers=declared or [], defaults={}, key_present=key_present or {},
            local_only=False, sendable=["O"],
            locals={"extraction": "qwen2.5:7b-instruct", "vision": None, "transcription": None,
                    "embedding": "all-minilm:22m-l6-v2-fp16"},
        )  # fmt: skip
        http = httpx.AsyncClient(base_url="http://litellm:4000", transport=self.gateway.transport(),
                                 headers={"Authorization": f"Bearer {MASTER}"})  # fmt: skip
        self.admin = ModelAdmin(
            installed=self.installed,
            settings_file=ModelSettingsFile(self.folder, profile=profile),
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
def serve() -> Iterator[Callable[[World], TestClient]]:
    def served(w: World) -> TestClient:
        app.state.model_admin = w.admin
        app.dependency_overrides[get_principal] = lambda: ADMIN
        return TestClient(app)

    yield served
    app.dependency_overrides.clear()
    app.state.model_admin = None


@pytest.fixture
def world(tmp_path: Path) -> World:
    return World(tmp_path)


@pytest.fixture
def client(world: World, serve: Callable[[World], TestClient]) -> TestClient:
    return serve(world)


@pytest.fixture
def world_with_identity(tmp_path: Path) -> World:
    """The gateway's pod given `ROLE` outright: for the cases whose subject is the Conduit's
    handling of an identity it is given (its refusals' words, no key kept), not whether the render
    gives one, which the default `World` follows (`_gateway_role_as_rendered`)."""
    return World(tmp_path, role=ROLE)


@pytest.fixture
def client_with_identity(
    world_with_identity: World, serve: Callable[[World], TestClient]
) -> TestClient:
    return serve(world_with_identity)


def _as(principal: Principal) -> None:
    app.dependency_overrides[get_principal] = lambda: principal


def _refusal(response: httpx.Response) -> str:
    return str(response.json()["detail"]["detail"])


# --- every other profile: exactly as before Amendment 4 (Amendment 7 decision 1) -----------------

#: A models file as *Admin › Models* wrote it before Amendment 4, naming `bedrock` as a provider.
MODELS_FILE_BEFORE = {
    "providers": [{"name": "bedrock", "label": "Bedrock", "roles": {"extraction": CLAUDE},
                   "api_base": None, "privacy_contract": False, "contract_reference": None}],
    "defaults": {"extraction": "bedrock"},
    "keys": {"bedrock": {"set_at": "2026-11-01T09:00:00Z", "set_by": "admin-1", "lost": False}},
    "limits": {},
}  # fmt: skip


@pytest.mark.parametrize("profile", OTHER_PROFILES)
def test_a_models_file_naming_bedrock_loads_off_the_cloud_platform_profile_as_before(
    tmp_path: Path, profile: str
) -> None:
    folder = tmp_path / "model-settings"
    folder.mkdir()
    (folder / "models.yaml").write_text(yaml.safe_dump(MODELS_FILE_BEFORE), encoding="utf-8")
    # The Conduit's own reader, from its own environment, as the Models service makes it at start.
    settings = ModelSettingsFile.from_env(
        {"OSPREY_MODEL_SETTINGS_DIR": str(folder), "OSPREY_PROFILE": profile}
    ).load()
    assert settings is not None
    engine = settings.providers[0]
    assert (engine.name, engine.kind, engine.auth, engine.region) == (
        "bedrock", "provider", "key", None,
    )  # fmt: skip
    assert engine.route("m") == "bedrock/m" and not engine.keyless


@pytest.mark.parametrize("profile", OTHER_PROFILES)
def test_off_the_cloud_platform_profile_bedrock_is_a_provider_by_its_key_as_before(
    tmp_path: Path, serve: Callable[[World], TestClient], profile: str
) -> None:
    w = World(tmp_path, profile=profile)
    client = serve(w)
    added = client.post("/v1/admin/models/engines", json={"provider": BEDROCK_BY_KEY})
    assert added.status_code == 200, added.text
    keyed = client.put("/v1/admin/models/engines/bedrock/key", json={"key": GEMINI_KEY})
    assert keyed.status_code == 200
    params = w.params(f"bedrock/{CLAUDE}")
    assert params["model"] == f"bedrock/{CLAUDE}"
    assert params["litellm_credential_name"] == "osprey-bedrock"
    assert "aws_region_name" not in params
    view = client.get("/v1/admin/models").json()
    assert view["engines"][0]["key_state"] == "set"
    assert view["engine_kinds"] == ["provider"]


@pytest.mark.parametrize("profile", OTHER_PROFILES)
@pytest.mark.parametrize(
    "body",
    [GATEWAY, BEDROCK, {**GEMINI, "auth": "iam_role"}, {**GEMINI, "region": "eu-west-2"}],
    ids=["gateway", "bedrock", "provider-by-role", "provider-with-a-region"],
)
def test_off_the_cloud_platform_profile_the_two_kinds_are_neither_offered_nor_taken(
    tmp_path: Path, serve: Callable[[World], TestClient], profile: str, body: dict[str, Any]
) -> None:
    w = World(tmp_path, profile=profile)
    client = serve(w)
    assert client.get("/v1/admin/models").json()["engine_kinds"] == ["provider"]
    refused = client.post("/v1/admin/models/engines", json={"provider": body})
    assert refused.status_code == 422, refused.text
    assert "profile: cloud-platform" in _refusal(refused)
    assert w.gateway.entry_for(f"{body['name']}/{next(iter(body['roles'].values()))}") is None
    assert w.models_file() == ""


@pytest.mark.parametrize("profile", OTHER_PROFILES)
def test_the_conduit_starts_off_the_cloud_platform_profile_on_a_declared_bedrock_provider(
    profile: str,
) -> None:
    # `OSPREY_MODEL_ENGINES` as the render wrote it before Amendment 4.
    environ = {
        "OSPREY_PROFILE": profile,
        "OSPREY_MODEL_ENGINES": json.dumps(
            [
                {
                    "name": "bedrock",
                    "label": "Bedrock",
                    "roles": {"extraction": f"bedrock/{CLAUDE}"},
                    "privacy_contract": False,
                    "contract_reference": None,
                    "api_base": None,
                }
            ]
        ),  # fmt: skip
        "OSPREY_MODEL_KEY_PRESENT_BEDROCK": "yes",
    }
    installed = Installed.from_env(LOCALS, environ)
    taken = [(p.name, p.kind, p.auth) for p in installed.providers]
    assert taken == [("bedrock", "provider", "key")]
    assert installed.key_present == {"bedrock": True}


def test_osprey_yaml_off_the_cloud_platform_profile_takes_bedrock_by_key_and_refuses_the_kinds(
) -> None:  # fmt: skip
    from tests.harness.test_cluster_render import cluster_config

    def models(*providers: dict[str, Any]) -> dict[str, Any]:
        return {"local_only": False, "sendable_handling_codes": ["P"], "providers": list(providers)}

    taken = cluster_config(models=models(BEDROCK_BY_KEY))
    assert taken.models.providers[0].plain
    for kind in (BEDROCK, GATEWAY):
        with pytest.raises(ValidationError, match="profile: cloud-platform"):
            cluster_config(models=models(kind))


def test_off_the_cloud_platform_profile_the_models_file_and_render_are_written_as_before(
    tmp_path: Path, serve: Callable[[World], TestClient]
) -> None:
    w = World(tmp_path, profile="small")
    client = serve(w)
    assert client.post("/v1/admin/models/engines", json={"provider": GEMINI}).status_code == 200
    written = yaml.safe_load(w.models_file())
    assert set(written["providers"][0]) == {
        "name", "label", "roles", "api_base", "privacy_contract", "contract_reference",
    }  # fmt: skip
    added = next(e for e in w.audit.entries if e.action == "engine_added")
    assert not {"kind", "auth", "region"} & set(added.changes)
    config = engines_config()
    engines = json.loads(dict(line.split("=", 1) for line in model_engines_env(config))
                         ["OSPREY_MODEL_ENGINES"])  # fmt: skip
    assert all(not {"kind", "auth", "region"} & set(e) for e in engines)


def test_on_the_cloud_platform_profile_the_three_kinds_are_offered(client: TestClient) -> None:
    offered = client.get("/v1/admin/models").json()["engine_kinds"]
    assert offered == ["provider", "gateway", "bedrock"]


# --- the cloud-platform profile's refusals (Amendment 7), at Admin › Models' own route ----------


def test_bedrock_signs_in_by_the_namespace_s_role_in_london_by_default() -> None:
    engine = ModelProviderConfig.model_validate(BEDROCK)
    assert (engine.auth, engine.region, engine.api_base) == ("iam_role", "eu-west-2", None)
    assert ModelProviderConfig.model_validate(GATEWAY).auth == "key"


def _bedrock_model(model: str) -> dict[str, Any]:
    return {**BEDROCK, "roles": {"extraction": model}}


@pytest.mark.parametrize(
    ("body", "words"),
    [
        ({**BEDROCK, "auth": "key"}, "IAM role"),
        ({**BEDROCK, "region": "us-east-1"}, "London"),
        ({**BEDROCK, "region": "eu-west-1"}, "London"),
        ({**BEDROCK, "api_base": BASE}, "address"),
        ({**GATEWAY, "api_base": None}, "address"),
        ({**GATEWAY, "region": "eu-west-2"}, "region"),
        ({**GEMINI, "auth": "iam_role"}, "IAM role"),
        ({**GATEWAY, "kind": "sagemaker"}, "kind"),
        # ("Bedrock" itself is redacted here: the request carried it as the label, which is not
        # shaped like a name, and nothing a person sent is quoted back.)
        (BEDROCK_BY_KEY, "reached only as Amazon"),
        ({**BEDROCK, "kind": "gateway", "api_base": BASE, "auth": "key"}, "reached only as Amazon"),
        (GATEWAY_BY_ROLE, "token for now"),
        # London only covers the model's id (Amendment 7 decision 2): an inference profile's id.
        (_bedrock_model(f"eu.{CLAUDE}"), "London only"),
        (_bedrock_model(f"us.{CLAUDE}"), "London only"),
        (_bedrock_model(f"apac.{CLAUDE}"), "London only"),
        (_bedrock_model(f"global.{CLAUDE}"), "London only"),
        (_bedrock_model(f"jp.{CLAUDE}"), "London only"),
        (_bedrock_model(f"us-gov.{CLAUDE}"), "London only"),
        (_bedrock_model("arn:aws:bedrock:eu-west-2:000000000000:inference-profile/"
                        f"eu.{CLAUDE}"), "London only"),  # fmt: skip
        (_bedrock_model("arn:aws:bedrock:eu-west-2:000000000000:application-inference-profile/"
                        "a1b2c3"), "London only"),  # fmt: skip
    ],
    ids=["bedrock-by-key", "bedrock-us", "bedrock-ireland", "bedrock-address",
         "gateway-no-address", "gateway-region", "provider-by-role", "unknown-kind",
         "bedrock-named-provider", "bedrock-named-gateway", "gateway-by-role-held",
         "id-eu", "id-us", "id-apac", "id-global", "id-jp", "id-us-gov", "arn-profile",
         "arn-application-profile"],
)  # fmt: skip
def test_the_cloud_platform_profile_refuses_each_shape_amendment_7_does_not_allow(
    client: TestClient, world: World, body: dict[str, Any], words: str
) -> None:
    refused = client.post("/v1/admin/models/engines", json={"provider": body})
    assert refused.status_code == 422, refused.text
    assert words in _refusal(refused)
    # Refused before the gateway was asked anything, and nothing written.
    model = next(iter(body["roles"].values()))
    assert world.gateway.entry_for(f"{body['name']}/{model}") is None
    assert world.models_file() == ""
    # A model's id is never quoted back (it may be anything a person pasted).
    assert "inference-profile/" not in refused.text and "a1b2c3" not in refused.text


@pytest.mark.parametrize("model", [
    CLAUDE, "amazon.titan-embed-text-v2:0", "cohere.embed-english-v3",
    "anthropic.claude-3-sonnet-20240229-v1:0:28k",
])  # fmt: skip
def test_a_bedrock_model_s_own_id_is_taken_on_the_cloud_platform_profile(model: str) -> None:
    engine = ModelProviderConfig.model_validate(_bedrock_model(model))
    assert deployment.engine_refusal(engine, CLOUD) is None


def test_the_conduit_refuses_a_cross_region_id_however_it_arrives(tmp_path: Path) -> None:
    """Every sibling reader of an engine on the profile: the models file and the render's lines."""
    folder = tmp_path / "model-settings"
    folder.mkdir()
    across = {**BEDROCK, "roles": {"extraction": f"eu.{CLAUDE}"}}
    (folder / "models.yaml").write_text(yaml.safe_dump({"providers": [across]}), encoding="utf-8")
    with pytest.raises(ValueError, match="London only"):
        ModelSettingsFile(folder, profile=CLOUD).load()
    environ = {"OSPREY_PROFILE": CLOUD, "OSPREY_MODEL_ENGINES": json.dumps([
        {**across, "roles": {"extraction": f"bedrock/eu.{CLAUDE}"}}])}  # fmt: skip
    with pytest.raises(ValueError, match="London only"):
        Installed.from_env(LOCALS, environ)


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


def test_the_gateway_answers_at_its_address_written_with_a_trailing_slash(
    client: TestClient, world: World
) -> None:
    body = {**GATEWAY, "api_base": f"{BASE}/"}
    assert client.post("/v1/admin/models/engines", json={"provider": body}).status_code == 200
    assert client.put("/v1/admin/models/engines/acme/key", json={"key": TOKEN}).status_code == 200
    assert client.post("/v1/admin/models/engines/acme/test").json()["outcome"] == "ok"


#: Where a token really lands when pasted into the wrong field (the review's item 4): the address's
#: userinfo, its query or fragment, the label, the contract reference.
PASTED = [
    ("api_base", f"https://{PLANTED}@ai-gateway.client.example/v1"),
    ("api_base", f"https://sk-proj-{PLANTED}@ai-gateway.client.example/v1"),
    ("api_base", f"https://user:{PLANTED}@ai-gateway.client.example/v1"),
    ("api_base", f"{BASE}?api-key={PLANTED}"),
    ("api_base", f"{BASE}#{PLANTED}"),
    ("label", PLANTED),
    ("contract_reference", PLANTED),
    # The shapes round 2 added (my own lane review of it, item 8): the same sweep of logs, the
    # audit, the models file and the gateway's rows.
    ("label", JWT),
    ("contract_reference", JWT),
    ("api_base", f"{BASE}/{PLANTED}"),
    ("api_base", f"{BASE}/{JWT}"),
    ("label", f"Acme gateway {PLANTED}"),
    ("contract_reference", f"DPA 2026/07 {PLANTED}"),
    ("api_base", f"{BASE}/{HEX}"),
]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("label", JWT),
        ("label", f"Acme gateway {JWT}"),
        ("contract_reference", JWT),
        ("contract_reference", f"DPA 2026/07 {JWT}"),
        # A key in the address's path (item d): the token pasted after the address.
        ("api_base", f"{BASE}/{PLANTED}"),
        ("api_base", f"{BASE}/{JWT}"),
        ("api_base", f"https://ai-gateway.client.example/sk-proj-{PLANTED}/v1"),
        # My own lane review of round 2, items 5 and 6: a lower-case token (Azure API Management's
        # subscription key is 32 lower-case hex), a token among words in the label, and a JWT
        # padded, encrypted (JWE: five parts, the second not `eyJ`) or with its dots encoded.
        ("api_base", f"{BASE}/{HEX}"),
        ("label", f"Acme gateway {PLANTED}"),
        ("label", JWT.replace(".", "=.", 1)),
        ("label", JWE),
        ("api_base", f"{BASE}/{JWT.replace('.', '%2E')}"),
        # P11 part 2, carried from part 1's confirmation: a token among a reference's words, and an
        # upper-case hex or base32 token in the path.
        ("contract_reference", f"DPA 2026/07 {PLANTED}"),
        ("api_base", f"{BASE}/{HEX.upper()}"),
        ("api_base", f"{BASE}/JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP"),
    ],
    ids=["label-jwt", "label-words-and-jwt", "reference-jwt", "reference-words-and-jwt",
         "path-token", "path-jwt", "path-sk", "path-hex", "label-words-and-token",
         "label-padded-jwt", "label-jwe", "path-encoded-jwt", "reference-words-and-token",
         "path-upper-hex", "path-base32"],
)  # fmt: skip
def test_a_token_in_a_field_that_is_shown_or_kept_is_refused_and_never_echoed(
    client: TestClient, world: World, field: str, value: str
) -> None:
    for body in ({**GATEWAY, field: value}, {**GATEWAY, "name": "acme_two", field: value}):
        refused = client.post("/v1/admin/models/engines", json={"provider": body})
        assert refused.status_code == 422, (field, refused.text)
        assert "Q7Z4" not in refused.text and "eyJ" not in refused.text
    assert world.models_file() == ""


@pytest.mark.parametrize("profile", ["local-lite", "small", "cluster"])
def test_the_engines_as_context_frees_only_a_cluster_translation(profile: str) -> None:
    """`ENGINES_AS` lets `harness.cloud_platform._as_cluster` validate its translation with its
    engines held to cloud-platform's rules. Honoured only for `cloud-platform` on a cluster
    configuration: a Lite or Small one, or another value, is refused as before (my own lane review
    of round 2, note 11)."""
    from schemas.deployment import ENGINES_AS
    from tests.harness.test_cluster_render import cluster_config

    base = cluster_config() if profile == "cluster" else engines_config()
    raw = base.model_dump(mode="json", exclude_none=True)
    raw["models"] = {"local_only": False, "sendable_handling_codes": ["P"], "providers": [BEDROCK]}
    raw["profile"] = profile
    if profile == "cluster":
        OspreyConfig.model_validate(raw, context={ENGINES_AS: CLOUD})  # the translation, freed
    else:
        with pytest.raises(ValidationError, match="profile: cloud-platform"):
            OspreyConfig.model_validate(raw, context={ENGINES_AS: CLOUD})
    with pytest.raises(ValidationError, match="profile: cloud-platform"):
        OspreyConfig.model_validate(raw, context={ENGINES_AS: "small"})


@pytest.mark.parametrize("path", ["/v1", "/openai/deployments/my-deployment-2024-08-06/v1",
                                  "/api/v2/gpt-4o-mini-2024-07-18", "/openai/v1",
                                  "/deployments/claude-3-haiku-london/chat"])  # fmt: skip
def test_an_address_s_ordinary_path_is_taken(client: TestClient, path: str) -> None:
    body = {**GATEWAY, "api_base": f"https://ai-gateway.client.example{path}"}
    assert client.post("/v1/admin/models/engines", json={"provider": body}).status_code == 200


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
    # A token pasted where a paste really lands is refused, on an edit and on an add, never echoed.
    for field, value in PASTED:
        edited = send("PUT", "/v1/admin/models/engines/acme",
                      json={"provider": {**GATEWAY, field: value}})  # fmt: skip
        assert edited.status_code == 422, (field, value)
        added = send("POST", "/v1/admin/models/engines",
                     json={"provider": {**GATEWAY, "name": "acme_two", field: value}})  # fmt: skip
        assert added.status_code == 422, (field, value)
    send("GET", "/v1/admin/models")
    send("GET", "/v1/admin/models/history")
    assert send("DELETE", key).status_code == 200

    fragments = (PLANTED, PLANTED[:12], "Q7Z4", "leak", "eyJhbGci", HEX)
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
    # And the engine still has its first address: no pasted one was taken.
    assert world.admin.settings.providers[0].api_base == BASE


# --- Test the connection: each refusal of the two kinds, in their own words (rule 15) ----------


def _tested(client: TestClient, name: str) -> dict[str, Any]:
    return dict(client.post(f"/v1/admin/models/engines/{name}/test").json())


def test_the_gateway_s_policy_refusal_names_the_policy_as_well_as_the_token(
    client: TestClient, world: World
) -> None:
    world.client_gateway.refused_by_policy = frozenset({"gpt-4o-mini"})
    client.post("/v1/admin/models/engines", json={"provider": GATEWAY})
    client.put("/v1/admin/models/engines/acme/key", json={"key": TOKEN})
    result = _tested(client, "acme")
    assert result["outcome"] == "key_refused"
    assert "policy" in result["words"] and "gateway's owners" in result["words"]


def test_the_gateway_s_rate_limit_is_said_as_its_own(client: TestClient, world: World) -> None:
    world.client_gateway.rate_limited = True
    client.post("/v1/admin/models/engines", json={"provider": GATEWAY})
    client.put("/v1/admin/models/engines/acme/key", json={"key": TOKEN})
    result = _tested(client, "acme")
    assert result["outcome"] == "rate_limited"
    assert "Your organisation's AI gateway is limiting" in result["words"]


@pytest.mark.parametrize(
    "refusal",
    [(400, '{"fault":{"faultstring":"Request rejected","detail":{"errorcode":"steps.raise"}}}'),
     (403, "<html><head><title>403 Forbidden</title></head><body>Request blocked</body></html>")],
    ids=["api-manager-400", "firewall-403-html"],
)  # fmt: skip
def test_the_gateway_s_refusal_in_another_shape_is_said_as_refused_never_unreachable(
    client: TestClient, world: World, refusal: tuple[int, str]
) -> None:
    world.client_gateway.refusal = refusal
    client.post("/v1/admin/models/engines", json={"provider": GATEWAY})
    client.put("/v1/admin/models/engines/acme/key", json={"key": TOKEN})
    result = _tested(client, "acme")
    assert result["outcome"] in ("request_refused", "key_refused")
    assert "could not be reached" not in result["words"]
    assert "gateway" in result["words"] and "Request rejected" not in json.dumps(result)


def test_bedrock_s_model_not_enabled_is_said_as_the_model_s_access_not_the_role_s(
    client_with_identity: TestClient, world_with_identity: World
) -> None:
    client, world = client_with_identity, world_with_identity
    world.bedrock.enabled_models = frozenset()
    client.post("/v1/admin/models/engines", json={"provider": BEDROCK})
    result = _tested(client, "bedrock")
    assert result["outcome"] == "model_not_enabled"
    assert "Model access" in result["words"] and "not the role's permissions" in result["words"]
    assert "refused the namespace's IAM role" not in result["words"]


def test_bedrock_s_expired_credentials_are_said_as_expired(
    client_with_identity: TestClient, world_with_identity: World
) -> None:
    client, world = client_with_identity, world_with_identity
    world.bedrock.expired = True
    client.post("/v1/admin/models/engines", json={"provider": BEDROCK})
    result = _tested(client, "bedrock")
    assert result["outcome"] == "sign_in_expired"
    assert "expired" in result["words"] and "restart the gateway" in result["words"]


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
    assert "IAM role" in _refusal(refused)
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
    assert removed.status_code == 409 and "IAM role" in _refusal(removed)
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


def test_a_keyed_engine_declared_beside_bedrock_is_made_at_start_and_answers_once_its_key_moves(
    tmp_path: Path,
) -> None:
    """`_start_once` reconciles every declared engine when an IAM-role one is among them (the
    review's item 8): the keyed engine's entries name its credential before the key is there, are
    offered to no analyst until it is, and answer once `move_keys` brings it in."""
    gemini = ModelProviderConfig.model_validate(GEMINI)
    w = World(tmp_path, declared=[gemini, ModelProviderConfig.model_validate(BEDROCK)],
              key_present={"gemini": False})  # fmt: skip

    async def started() -> tuple[object, object]:
        await w.admin.start()
        await w.admin.close()
        return (await w.admin.test("admin-1", "bedrock"), await w.admin.test("admin-1", "gemini"))

    bedrock, gemini_before = asyncio.run(started())
    assert getattr(bedrock, "outcome", None) == "ok"
    assert w.params("gemini/g-flash")["litellm_credential_name"] == "osprey-gemini"
    assert getattr(gemini_before, "outcome", None) == "key_refused"
    assert w.admin.routes().engines["gemini"].key_present is False
    assert w.gateway.credential("osprey-gemini") is None
    assert not (w.folder / "models.yaml").exists()
    moved, skipped = asyncio.run(move_keys(w.admin, [f"GEMINI={GEMINI_KEY}"], "cli:root"))
    assert (moved, skipped) == (["gemini"], [])
    assert asyncio.run(w.admin.test("admin-1", "gemini")).outcome == "ok"
    assert w.admin.routes().engines["gemini"].key_present is True


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
    """A real cloud-platform deployment with an engine of each kind (P7's fixture): the cases below
    once ran on a Small configuration with these engines copied in unvalidated, which no real call
    site makes (my own lane review of round 2, item 4)."""
    return _cloud_config(BEDROCK, GATEWAY, GEMINI)


def _rendered(config: OspreyConfig) -> dict[str, str]:
    """The Conduit's environment as the cloud-platform render writes it, `OSPREY_PROFILE` and the
    engines' variables included, never written by hand."""
    from tests.harness.test_cloud_platform_render import _values

    return {k: str(v) for k, v in _values(config)["environment"].items()}


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


def _cloud_config(*providers: dict[str, Any]) -> OspreyConfig:
    """A real `profile: cloud-platform` deployment (P7's own fixture), with these engines: the
    cases below ran on a widened profile set before P7 merged, which hid that the render refused
    the very engines it was rendering (the orchestrator's round 2, item a)."""
    from tests.harness.test_cloud_platform_render import AWS, _config

    models = {"local_only": not providers, "sendable_handling_codes": ["P"] if providers else [],
              "providers": list(providers)}  # fmt: skip
    # Each engine's host is an egress host, which the render refuses without its networks.
    nets = {**AWS, BEDROCK_HOST: ["198.18.2.0/24"], "ai-gateway.client.example": ["203.0.113.0/24"],
            "generativelanguage.googleapis.com": ["203.0.114.0/24"]}  # fmt: skip
    return _config("development", models=models, cloud_platform={"egress_nets": nets})


#: Bedrock's runtime in London, the one host a Bedrock engine's calls reach (ADR-135 Am 4).
BEDROCK_HOST = "bedrock-runtime.eu-west-2.amazonaws.com"


def test_a_bedrock_engine_s_host_is_an_egress_host_by_its_region() -> None:
    """A Bedrock engine names no address; the render took an engine's host from its address or its
    provider's name alone, so it refused Bedrock as "names no api_base" (P11 at the rebase onto
    P7). Its host is its region's runtime, allowed by its networks, or refused in words."""
    from harness.cloud_platform import CloudPlatformNotRenderable

    from tests.harness.test_cloud_platform_render import _artefacts, _config, _hosts

    hosts = _hosts(_cloud_values(BEDROCK))
    assert hosts[BEDROCK_HOST] == ["198.18.2.0/24"]
    # By its kind, whatever its name: a row keyed `bedrock` by name would pass the case above.
    renamed = {**BEDROCK, "name": "claude_london", "label": "Claude (London)"}
    assert _hosts(_cloud_values(renamed))[BEDROCK_HOST] == ["198.18.2.0/24"]
    models = {"local_only": False, "sendable_handling_codes": ["P"], "providers": [BEDROCK]}
    with pytest.raises(CloudPlatformNotRenderable, match=BEDROCK_HOST):
        _artefacts(_config("development", models=models))


def _cloud_values(*providers: dict[str, Any]) -> dict[str, Any]:
    from tests.harness.test_cloud_platform_render import _values

    return _values(_cloud_config(*providers))


@pytest.mark.parametrize("declared", [[BEDROCK], [BEDROCK, GATEWAY], []],
                         ids=["bedrock", "bedrock-and-gateway", "none"])  # fmt: skip
def test_the_cloud_platform_render_tells_the_conduit_its_profile(
    declared: list[dict[str, Any]],
) -> None:
    """The Conduit offers and takes the two kinds by `OSPREY_PROFILE` (`model_admin`): the
    cloud-platform render renders an engine of each kind, and writes the profile they need."""
    values = _cloud_values(*declared)
    assert values["environment"]["OSPREY_PROFILE"] == CLOUD
    installed = Installed.from_env(LOCALS, {**values["environment"]})
    assert [p.name for p in installed.providers] == [p["name"] for p in declared]


def test_an_iam_role_engine_s_held_key_is_blanked_in_every_cloud_platform_workload() -> None:
    from tests.harness.test_cloud_platform_render import _containers

    containers = _containers(_cloud_values(BEDROCK))
    readers = [c for c in containers if c.get("envFrom")]
    assert readers
    for container in readers:
        blanked = {e["name"]: e.get("value") for e in container.get("env", [])}
        assert blanked.get("OSPREY_MODEL_KEY_BEDROCK") == "", container["name"]
    # The gateway reads the Secret by name only, and not this name.
    gateway = next(c for c in containers if c["name"] == "litellm")
    assert not gateway.get("envFrom")
    assert all(e["name"] != "OSPREY_MODEL_KEY_BEDROCK" for e in gateway["env"])


@pytest.mark.parametrize(
    "declared", [[BEDROCK], [BEDROCK, GATEWAY]], ids=["bedrock", "bedrock-and-gateway"]
)
def test_the_gateway_workload_carries_no_static_aws_key(declared: list[dict[str, Any]]) -> None:
    """The gateway's pod signs Bedrock's calls by its own identity alone (the review's item 8):
    botocore prefers static keys in the environment to the pod's web identity, so none is given,
    declared at install (a cloud-platform render runs the gateway only with an engine enabled, P7;
    one added later in *Admin › Models* is held by the case after this)."""
    values = _cloud_values(*declared)
    gateway = next(w for w in values["workloads"] if w["name"] == "litellm")
    # Nothing reaches it unnamed: it reads no Secret whole, so a key held there is not handed on.
    assert not gateway.get("envFrom")
    # And none is named, in any shape the chart takes (`value`, `secret`, `config`, `field`).
    assert not {e["name"] for e in gateway.get("env", [])} & set(STATIC_AWS)
    assert not any(variable in yaml.safe_dump(values) for variable in STATIC_AWS)
    # The gateway does read its own keys by name: the case is not passing on an empty workload.
    assert any(e["name"] == "LITELLM_MASTER_KEY" for e in gateway["env"])


def test_an_engine_added_in_admin_models_gives_the_gateway_no_static_aws_key(
    client: TestClient, world: World
) -> None:
    client.post("/v1/admin/models/engines", json={"provider": BEDROCK})
    params = world.params(f"bedrock/{CLAUDE}")
    assert not {p.lower() for p in STATIC_AWS} & set(params)
    assert not any("AWS_" in str(v) for v in params.values())
    assert client.post("/v1/admin/models/engines/bedrock/test").json()["outcome"] == "ok"
    assert [k for where, k in world.gateway.sent if where.startswith("bedrock:")] == [None]


def test_the_install_page_offers_no_key_field_for_an_iam_role_engine(tmp_path: Path) -> None:
    from harness.install_page import _providers

    draft = tmp_path / "osprey.yaml"
    draft.write_text(yaml_dump(_cloud_config(BEDROCK, GATEWAY, GEMINI)), encoding="utf-8")
    assert {p["name"] for p in _providers(draft)} == {"acme", "gemini"}


def yaml_dump(config: OspreyConfig) -> str:
    return yaml.safe_dump(config.model_dump(mode="json", exclude_none=True), sort_keys=False)
