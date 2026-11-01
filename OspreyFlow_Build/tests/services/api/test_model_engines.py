"""ADR-135 decisions 4 and 5: an analyst may name an engine per request; the route decides.

The requests here reach a **stand-in gateway** built from the model table the renderer writes
(`render_litellm_config`) and the keys the gateway's own environment holds. Per `CLAUDE.md` rule 15
it refuses what the real LiteLLM proxy refuses — a model not in its table, a provider not in its
table, a key that is missing or wrong — and `test_the_stand_in_gateway_refuses_as_the_real_one_
does` shows each refusal before any routing test is trusted.

What a mistake would do, and the case that catches it (rule 12):
- material above the sendable codes sent to the engine an analyst named —
  `test_naming_gemini_for_material_that_may_not_be_sent_does_not_send_it`;
- an engine the administrator did not enable, or one with no key, used anyway —
  `test_an_engine_not_enabled_is_refused_in_words`, `test_an_engine_with_no_key_is_refused_in_
  words`;
- an answer that does not say which engine and model produced it —
  `test_an_answer_names_its_engine_and_model`;
- a role's default ignored, or a default with no key used — `test_no_engine_named_runs_on_the_
  default_and_a_default_with_no_key_runs_locally`;
- the Conduit reading the engines differently from how the renderer wrote them —
  `test_the_conduit_reads_the_engines_the_renderer_wrote`;
- `GET /v1/models/engines` carrying a key, offering an engine with no key, or answering without
  sign-in (rule 4) — the three `test_the_engines_route_*` cases;
- the Admin area not saying which engine has a key — `test_the_status_shows_each_engine_its_
  defaults_and_whether_its_key_is_present`.
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
from collections.abc import Mapping, Sequence
from typing import Any

import pytest
import yaml
from fastapi.testclient import TestClient
from harness.render import model_engines_env, render_litellm_config
from services.api.app import app, get_model_routes, get_principal
from services.api.config import DeploymentModels
from services.api.model_routing import (
    EngineRefused,
    ModelEgressRefused,
    ModelRoutes,
    RoutedModel,
    model_status,
    routes_from_env,
)
from tools.layout import CORE

from schemas.deployment import ModelsConfig, OspreyConfig
from schemas.domain import Handling, Principal
from schemas.model import ExtractionRequest, ExtractionResult
from tests.harness.test_render import FIXTURE_CONFIG

LOCAL = "qwen2.5:7b-instruct"
GEMINI_KEY = "AIza-gemini-NEVER-IN-AN-ANSWER"
ANTHROPIC_KEY = "sk-ant-NEVER-IN-AN-ANSWER"

MODELS = ModelsConfig.model_validate(
    {
        "local_only": False,
        "sendable_handling_codes": ["P"],
        "providers": [
            {"name": "gemini", "roles": {"extraction": "gemini-2.5-flash"}},
            # Enabled, but its key was never given (or was removed): shown "no key", not offered.
            {"name": "openai", "roles": {"extraction": "gpt-4o-mini"}},
            {"name": "anthropic", "label": "Claude", "roles": {"extraction": "claude-sonnet-4"}},
        ],
        "defaults": {"extraction": "anthropic"},
    }
)
#: The gateway's own environment: what `deployment.env` gives it.
GATEWAY_ENV = {"OSPREY_MODEL_KEY_GEMINI": GEMINI_KEY, "OSPREY_MODEL_KEY_ANTHROPIC": ANTHROPIC_KEY}
#: What each provider itself accepts.
PROVIDERS_ACCEPT = {"gemini": GEMINI_KEY, "anthropic": ANTHROPIC_KEY, "openai": "sk-openai-real"}


def _handling(code: str) -> Handling:
    return Handling(classification="OFFICIAL", handling_code=code, owning_unit="u", originator="u")


class GatewayRefused(Exception):
    """What LiteLLM answers instead of a completion: the status and its words."""

    def __init__(self, status: int, words: str) -> None:
        super().__init__(f"{status}: {words}")
        self.status = status


class StandInGateway:
    """The LiteLLM proxy as far as these requests go: it routes only a `model_name` in its table
    (`model_list`), reads each entry's `api_key` from `os.environ/<VAR>` in its own environment, and
    the provider behind it refuses a missing or wrong key. Every request is recorded, refused or
    not, so a test can say a model was never asked for at all."""

    def __init__(
        self,
        table: Mapping[str, Any],
        environ: Mapping[str, str],
        accepted: Mapping[str, str],
    ) -> None:
        self._entries = {m["model_name"]: m["litellm_params"] for m in table["model_list"]}
        self._environ = environ
        self._accepted = accepted
        self.asked: list[str] = []

    async def extract(self, req: ExtractionRequest) -> ExtractionResult:
        self.asked.append(req.model)
        params = self._entries.get(req.model)
        if params is None:
            # LiteLLM proxy: 400 "Invalid model name passed in model=…" — a provider not in the
            # table is the same refusal, since the proxy routes nothing it was not configured with.
            raise GatewayRefused(400, f"Invalid model name passed in model={req.model}")
        reference = str(params.get("api_key", ""))
        if reference.startswith("os.environ/"):
            provider = req.model.split("/", 1)[0]
            key = self._environ.get(reference.removeprefix("os.environ/"), "")
            if not key:
                raise GatewayRefused(401, f"AuthenticationError: {provider}: no API key")
            if key != self._accepted.get(provider):
                raise GatewayRefused(401, f"AuthenticationError: {provider}: API key not valid")
        return ExtractionResult(document_id=req.document_id, model=req.model, data={"answer": "a"})

    async def embed(self, texts: Sequence[str]) -> list[Any]:
        return []


def _table() -> dict[str, Any]:
    return dict(yaml.safe_load(render_litellm_config(_config())))


def _config() -> OspreyConfig:
    loaded = OspreyConfig.model_validate(yaml.safe_load(FIXTURE_CONFIG))
    return loaded.model_copy(
        update={
            "models": MODELS,
            "components": loaded.components.model_copy(update={"source_path": str(CORE)}),
        }
    )


def _conduit_env(keys: Mapping[str, str] = GATEWAY_ENV) -> dict[str, str]:
    """What the Conduit's environment holds: the rendered lines, and each key's presence as Compose
    resolves `${KEY:+yes}` from the same env file."""
    env = dict(line.split("=", 1) for line in model_engines_env(_config()))
    for provider in MODELS.enabled_providers:
        variable = MODELS.key_variable(provider.name)
        present = "yes" if keys.get(variable) else ""
        env[f"OSPREY_MODEL_KEY_PRESENT_{provider.name.upper()}"] = present
    env["OSPREY_EXTRACTION_MODEL"] = LOCAL
    return env


def _locals() -> DeploymentModels:
    return DeploymentModels(extraction=LOCAL, vision="moondream", transcription="whisper",
                            embedding="minilm")  # fmt: skip


def _routes(extraction: str | None = LOCAL, keys: Mapping[str, str] = GATEWAY_ENV) -> ModelRoutes:
    routes = routes_from_env(_locals(), _conduit_env(keys))
    if extraction is None:  # a deployment with no local extraction model
        routes = dataclasses.replace(routes, locals={**routes.locals, "extraction": None})
    return routes


def _gateway(environ: Mapping[str, str] = GATEWAY_ENV) -> StandInGateway:
    return StandInGateway(_table(), environ, PROVIDERS_ACCEPT)


def _ask(engine: str | None, handling: Handling | None) -> ExtractionRequest:
    return ExtractionRequest(document_id="q", text="t", json_schema={}, model=LOCAL,
                             handling=handling, engine=engine)  # fmt: skip


# --- the stand-in, shown to refuse first (rule 15) -----------------------------------------------


async def test_the_stand_in_gateway_refuses_as_the_real_one_does() -> None:
    gateway = _gateway()
    with pytest.raises(GatewayRefused, match="Invalid model name"):  # a model not in its table
        await gateway.extract(_ask(None, None).model_copy(update={"model": "gemini/gemini-9"}))
    with pytest.raises(GatewayRefused, match="Invalid model name"):  # a provider not in its table
        await gateway.extract(_ask(None, None).model_copy(update={"model": "mistral/large"}))
    with pytest.raises(GatewayRefused, match="no API key"):  # enabled, no key in its environment
        await gateway.extract(_ask(None, None).model_copy(update={"model": "openai/gpt-4o-mini"}))
    wrong = _gateway({**GATEWAY_ENV, "OSPREY_MODEL_KEY_GEMINI": "AIza-wrong"})
    with pytest.raises(GatewayRefused, match="not valid"):  # a wrong key
        sent = _ask(None, None).model_copy(update={"model": "gemini/gemini-2.5-flash"})
        await wrong.extract(sent)
    # And it answers what it should: the local model, and a provider with its right key.
    assert (await gateway.extract(_ask(None, None))).model == LOCAL
    sent = _ask(None, None).model_copy(update={"model": "gemini/gemini-2.5-flash"})
    assert (await gateway.extract(sent)).model == "gemini/gemini-2.5-flash"


# --- routing -------------------------------------------------------------------------------------


async def test_naming_gemini_for_material_that_may_not_be_sent_does_not_send_it() -> None:
    gateway = _gateway()
    result = await RoutedModel(gateway, routes=_routes()).extract(_ask("gemini", _handling("C")))
    assert gateway.asked == [LOCAL]
    assert not [m for m in gateway.asked if m.startswith("gemini/")]
    assert (result.engine, result.model) == ("local", LOCAL)
    # Material whose handling is not given is never sent either.
    await RoutedModel(gateway, routes=_routes()).extract(_ask("gemini", None))
    assert gateway.asked == [LOCAL, LOCAL]


async def test_with_no_local_model_unsendable_material_naming_gemini_is_refused_and_not_sent() -> (
    None
):
    gateway = _gateway()
    with pytest.raises(ModelEgressRefused, match="handling code C may not be sent"):
        await RoutedModel(gateway, routes=_routes(extraction=None)).extract(
            _ask("gemini", _handling("C"))
        )
    assert gateway.asked == []


async def test_an_engine_not_enabled_is_refused_in_words() -> None:
    gateway = _gateway()
    with pytest.raises(EngineRefused, match="mistral is not an engine this deployment enabled"):
        await RoutedModel(gateway, routes=_routes()).extract(_ask("mistral", _handling("P")))
    assert gateway.asked == []


async def test_an_engine_with_no_key_is_refused_in_words() -> None:
    gateway = _gateway()
    with pytest.raises(EngineRefused, match="OpenAI has no key on this deployment"):
        await RoutedModel(gateway, routes=_routes()).extract(_ask("openai", _handling("P")))
    # Refused whatever the material, before anything is sent.
    with pytest.raises(EngineRefused, match="no key"):
        await RoutedModel(gateway, routes=_routes()).extract(_ask("openai", _handling("C")))
    assert gateway.asked == []


async def test_an_answer_names_its_engine_and_model() -> None:
    gateway = _gateway()
    routed = RoutedModel(gateway, routes=_routes())
    sent = await routed.extract(_ask("gemini", _handling("P")))
    assert (sent.engine, sent.model) == ("gemini", "gemini/gemini-2.5-flash")
    local = await routed.extract(_ask("local", _handling("P")))
    assert (local.engine, local.model) == ("local", LOCAL)
    assert gateway.asked == ["gemini/gemini-2.5-flash", LOCAL]


async def test_no_engine_named_runs_on_the_default_and_a_default_with_no_key_runs_locally() -> None:
    gateway = _gateway()
    result = await RoutedModel(gateway, routes=_routes()).extract(_ask(None, _handling("P")))
    assert (result.engine, result.model) == ("anthropic", "anthropic/claude-sonnet-4")
    # The default's key removed: it is not used, and nothing reaches the gateway for it.
    without = {"OSPREY_MODEL_KEY_GEMINI": GEMINI_KEY}
    gateway = _gateway(without)
    result = await RoutedModel(gateway, routes=_routes(keys=without)).extract(
        _ask(None, _handling("P"))
    )
    assert (result.engine, gateway.asked) == ("local", [LOCAL])


def test_the_conduit_reads_the_engines_the_renderer_wrote() -> None:
    routes = _routes()
    assert {e.name: e.key_present for e in routes.engines.values()} == {
        "gemini": True, "openai": False, "anthropic": True,
    }  # fmt: skip
    assert routes.engines["anthropic"].label == "Claude"
    assert routes.engines["gemini"].models == {"extraction": "gemini/gemini-2.5-flash"}
    assert routes.default_for("extraction") == "anthropic"
    assert routes.default_for("vision") == "local"
    assert routes.sendable == frozenset({"P"})
    # A local-only deployment: no engines, every role local.
    bare = routes_from_env(_locals(), {})
    assert bare.engines == {} and bare.default_for("extraction") == "local"


def test_the_status_shows_each_engine_its_defaults_and_whether_its_key_is_present() -> None:
    statuses, engines, notice = model_status(_routes())
    shown = {e.name: (e.key_present, e.default_for) for e in engines}
    assert shown == {
        "local": (True, ["vision", "transcription", "embedding"]),
        "gemini": (True, []), "openai": (False, []), "anthropic": (True, ["extraction"]),
    }  # fmt: skip
    roles = {s.role: s for s in statuses}
    assert (roles["extraction"].runs_at, roles["extraction"].model) == (
        "anthropic", "anthropic/claude-sonnet-4"
    )
    assert notice == (
        "Case content with handling code P is sent to anthropic for extraction, and may be sent to "
        "gemini for extraction when an analyst chooses it. Anything else runs on this "
        "deployment's own models."
    )
    for text in (json.dumps([s.model_dump() for s in statuses]), notice):
        assert GEMINI_KEY not in text and ANTHROPIC_KEY not in text


# --- GET /v1/models/engines ----------------------------------------------------------------------

ANALYST = Principal(id="analyst-1", clearance="OFFICIAL", org_unit="unit-1", roles=["analyst"])


@pytest.fixture
def client() -> Any:
    app.dependency_overrides[get_model_routes] = _routes
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_the_engines_route_offers_only_enabled_engines_with_a_key(client: TestClient) -> None:
    app.dependency_overrides[get_principal] = lambda: ANALYST
    response = client.get("/v1/models/engines")
    assert response.status_code == 200, response.text
    assert response.json() == {
        "engines": [
            {"name": "local", "label": "This deployment's own model",
             "roles": ["extraction", "vision", "transcription", "embedding"],
             "default_for": ["vision", "transcription", "embedding"]},
            {"name": "gemini", "label": "Gemini", "roles": ["extraction"], "default_for": []},
            {"name": "anthropic", "label": "Claude", "roles": ["extraction"],
             "default_for": ["extraction"]},
        ]
    }  # fmt: skip


def test_the_engines_route_never_carries_a_key(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name, value in GATEWAY_ENV.items():
        monkeypatch.setenv(name, value)
    app.dependency_overrides[get_principal] = lambda: ANALYST
    text = client.get("/v1/models/engines").text
    assert GEMINI_KEY not in text and ANTHROPIC_KEY not in text and "key" not in text.lower()


def test_the_engines_route_is_refused_without_sign_in(client: TestClient) -> None:
    app.dependency_overrides.pop(get_principal, None)
    assert client.get("/v1/models/engines").status_code == 401


def test_a_request_naming_a_refused_engine_is_answered_in_words_with_a_4xx(
    client: TestClient,
) -> None:
    """The handler the ask routes' refusal reaches: a 422 that says why, never a 500."""
    from services.api.app import _engine_refused_handler

    refused = EngineRefused("OpenAI has no key on this deployment")
    answered = asyncio.run(_engine_refused_handler(None, refused))  # type: ignore[arg-type]
    assert answered.status_code == 422
    assert json.loads(answered.body) == {
        "error": "engine_refused", "detail": "OpenAI has no key on this deployment",
    }  # fmt: skip


def test_the_ask_requests_accept_an_engine() -> None:
    from services.api.pattern_ask import AskToSearchRequest
    from services.api.questions import AskRequest

    assert AskRequest(question="who", engine="gemini").engine == "gemini"
    assert AskRequest(question="who").engine is None
    assert AskToSearchRequest(question="who", engine="gemini").engine == "gemini"
