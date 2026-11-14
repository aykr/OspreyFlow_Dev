"""An engine's refusals and a slow engine, said in words (ADR-135 Amendment 13; the orchestrator's
route row D2, 14 November 2026).

Measured first, through the pinned gateway and the real `LiteLLMClient`
(`process/lanes/studio/model-words/`, replayed here from `gemini_refusals.json` word for word):
before this change every one of these reached a person as "The model answered, but not in the
shape asked for", and a slow engine as an unhandled 500 after up to fifteen minutes. What a mistake
would do, and the case that catches it:

- Gemini's refusal of its key said as a malformed answer
  (`test_a_key_the_provider_refuses_is_said_as_the_key_and_asked_once`);
- its quota said so, or asked again on top of the gateway's own three tries
  (`test_the_provider_s_own_quota_is_busy_not_a_limit_set_here`);
- its overload asked nine times in all
  (`test_a_provider_failure_the_gateway_passed_on_is_asked_once`);
- the gateway's cooldown after a failure said as a fault
  (`test_the_gateway_resting_the_engine_after_a_failure_is_unavailable`);
- the gateway's own refusal of our key blamed on the provider
  (`test_the_gateway_s_own_refusal_keeps_its_old_path`);
- a hosted engine left fifteen minutes, or a local model cut to the hosted bound
  (`test_a_hosted_engine_is_stopped_at_its_own_bound_and_a_local_model_keeps_its_own`);
- the engine left unnamed, or the provider's words passed on (the routed and Conduit cases).
"""

from __future__ import annotations

import asyncio
import json
import threading
import time
from collections.abc import Callable, Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import httpx
import pytest
from services.api.app import _model_engine_refused_handler
from services.api.model_routing import RoutedModel

from adapters.model_litellm.client import LiteLLMClient, LiteLLMConfig
from adapters.model_litellm.errors import (
    ExtractionFailedError,
    ModelEngineRefused,
    ModelLimitReached,
)
from adapters.model_litellm.usage import calling

MEASURED: dict[str, Any] = json.loads(
    (Path(__file__).parent / "gemini_refusals.json").read_text(encoding="utf-8")
)
SCHEMA = {"type": "object", "properties": {"x": {"type": "string"}}, "required": ["x"]}


def _replaying(status: int, body: dict[str, Any]) -> tuple[LiteLLMClient, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def answer(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(status, json=body)

    client = LiteLLMClient(LiteLLMConfig(api_key="sk-test"), transport=httpx.MockTransport(answer))
    return client, seen


def _measured(name: str) -> tuple[LiteLLMClient, list[httpx.Request]]:
    return _replaying(MEASURED[name]["status"], MEASURED[name]["body"])


def _extract(client: LiteLLMClient, engine: str = "gemini") -> Any:
    async def go() -> Any:
        with calling(engine, "extraction"):
            return await client.extract_json(model="m", text="t", response_schema=SCHEMA)

    return asyncio.run(go())


def _refused(client: LiteLLMClient, engine: str = "gemini") -> ModelEngineRefused:
    with pytest.raises(ModelEngineRefused) as refused:
        _extract(client, engine)
    assert isinstance(
        refused.value, ExtractionFailedError
    )  # every existing caller still catches it
    return refused.value


def test_a_key_the_provider_refuses_is_said_as_the_key_and_asked_once() -> None:
    client, seen = _measured("gemini-bad-key")
    refused = _refused(client)
    assert refused.kind == "key"
    assert len(seen) == 1
    assert "API key not valid" not in str(refused) and "GeminiException" not in str(refused)


def test_a_permission_the_provider_refuses_is_said_as_the_key() -> None:
    client, seen = _measured("gemini-403")
    assert _refused(client).kind == "key" and len(seen) == 1


def test_the_provider_s_own_quota_is_busy_not_a_limit_set_here() -> None:
    """A 429 `throttling_error`, as the gateway's own key limit is, but not in its words."""
    client, seen = _measured("gemini-429")
    refused = _refused(client)
    assert refused.kind == "busy" and not isinstance(refused, ModelLimitReached)
    assert len(seen) == 1  # the gateway already tried three times
    assert "not a limit set on this deployment" in str(refused)


def test_a_provider_failure_the_gateway_passed_on_is_asked_once() -> None:
    """ADR-135 Amendment 13's choice: the gateway already asked the provider three times (measured:
    the stub saw three for each of the client's asks), so the client asks once, not three times."""
    client, seen = _measured("gemini-503")
    assert _refused(client).kind == "unavailable"
    assert len(seen) == 1


def test_the_gateway_resting_the_engine_after_a_failure_is_unavailable() -> None:
    """The cooldown's 429, as the pinned gateway gives it (measured 8 November, `stand_in.py`)."""
    client, seen = _replaying(429, {"error": {
        "message": "No deployments available for selected model, Try again in 5 seconds. Passed "
        "model=gemini/gemini-2.5-flash. pre-call-checks=False, cooldown_list=['a1b2']",
        "type": "internal_server_error", "param": None, "code": "429"}})  # fmt: skip
    assert _refused(client).kind == "unavailable" and len(seen) == 1


def test_no_key_at_all_is_said_as_the_key() -> None:
    """A 500 whose words are the provider's `AuthenticationError` (measured 8 November)."""
    client, _ = _replaying(500, {"error": {
        "message": "litellm.AuthenticationError: AuthenticationError: OpenAIException - The "
        "api_key client option must be set", "type": "internal_server_error", "param": None,
        "code": "500"}})  # fmt: skip
    assert _refused(client).kind == "key"


def test_the_gateway_s_own_refusal_keeps_its_old_path() -> None:
    """Our key refused by the gateway itself is not the provider's: its words, from the pinned
    source (`proxy/auth/auth_checks.py`), never begin `litellm.`."""
    client, _ = _replaying(401, {"error": {
        "message": "Authentication Error, Invalid proxy server token passed. key=88dc…",
        "type": "auth_error", "param": "None", "code": "401"}})  # fmt: skip
    with pytest.raises(ExtractionFailedError) as failed:
        _extract(client)
    assert not isinstance(failed.value, ModelEngineRefused)


def test_a_server_fault_without_the_gateway_s_words_is_still_retried() -> None:
    client, seen = _replaying(500, {"error": {"message": "Internal Server Error"}})
    with pytest.raises(ExtractionFailedError) as failed:
        _extract(client)
    assert not isinstance(failed.value, ModelEngineRefused)
    assert len(seen) == 3


# --- a slow engine: a real socket, since a mock transport enforces no timeout ------------------


ANSWER = json.dumps({"choices": [{"message": {"content": json.dumps({"x": "y"})}}]}).encode()


@pytest.fixture
def slow_gateway() -> Iterator[Callable[[float], LiteLLMClient]]:
    """A gateway that answers after `DELAY` seconds, as the measured slow engine did (it answered
    nothing, and the client raised `httpx.ReadTimeout`)."""

    class Slow(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            self.rfile.read(int(self.headers.get("content-length") or 0))
            time.sleep(0.6)
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(ANSWER)))
            self.end_headers()
            self.wfile.write(ANSWER)

        def log_message(self, *args: object) -> None:
            return None

    server = ThreadingHTTPServer(("127.0.0.1", 0), Slow)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    def client(hosted_bound: float) -> LiteLLMClient:
        return LiteLLMClient(
            LiteLLMConfig(
                host="127.0.0.1",
                port=server.server_address[1],
                api_key="sk-test",
                timeout_seconds=5,
                hosted_timeout_seconds=hosted_bound,
            )
        )

    yield client
    server.shutdown()


def test_a_hosted_engine_is_stopped_at_its_own_bound_and_a_local_model_keeps_its_own(
    slow_gateway: Callable[[float], LiteLLMClient],
) -> None:
    started = time.monotonic()
    refused = _refused(slow_gateway(0.2), "gemini")
    assert time.monotonic() - started < 0.6, "stopped at the hosted bound, not the local one"
    assert refused.kind == "timed_out" and refused.timeout_seconds == 0.2
    assert "0.2 seconds" in str(refused)
    # The same slow answer is waited for when the deployment's own model gives it.
    assert _extract(slow_gateway(0.2), "local") == {"x": "y"}


def test_the_hosted_bound_is_the_deployment_s_to_set(monkeypatch: pytest.MonkeyPatch) -> None:
    assert LiteLLMConfig().hosted_timeout_seconds == 120.0
    monkeypatch.setenv("OSPREY_HOSTED_MODEL_TIMEOUT_SECONDS", "45")
    assert LiteLLMConfig.from_env().hosted_timeout_seconds == 45.0


# --- the engine named, through the real routing; and what the Conduit answers ------------------


class _Refusing:
    """The adapter the routing wraps, refusing as the client does for each kind."""

    def __init__(self, refusal: ModelEngineRefused) -> None:
        self.refusal = refusal

    async def extract(self, req: Any) -> Any:
        raise self.refusal

    async def describe_image(self, req: Any) -> Any:
        raise self.refusal


@pytest.mark.parametrize("kind", ["busy", "key", "unavailable", "timed_out"])
def test_the_routing_names_the_engine_that_refused(kind: str) -> None:
    from services.api.datasets import Dataset, InMemoryDatasetStore
    from services.api.model_routing import Engine, ModelRoutes

    from schemas.domain import Handling
    from schemas.model import ExtractionRequest

    datasets = InMemoryDatasetStore()
    datasets.add(Dataset(id="open", name="Open", owning_unit="u", created_by="seed", egress="any",
                         created_at="2026-11-01T00:00:00Z"))  # type: ignore[arg-type]  # fmt: skip
    gemini = Engine(name="gemini", label="Gemini", models={"extraction": "gemini-2.5-flash"},
                    key_present=True)  # fmt: skip
    routes = ModelRoutes(
        locals={"extraction": None}, engines={"gemini": gemini}, defaults={"extraction": "gemini"},
        sendable=frozenset({"O"}),
    )  # fmt: skip
    routed = RoutedModel(_Refusing(ModelEngineRefused(kind, timeout_seconds=120)), routes=routes,
                         egress=datasets)  # type: ignore[arg-type]  # fmt: skip
    request = ExtractionRequest(
        document_id="d", text="t", json_schema={"type": "object"}, model="m", engine="gemini",
        datasets=["open"], handling=Handling(classification="OFFICIAL", handling_code="O",
                                             owning_unit="u", originator="u"),
    )  # fmt: skip
    with pytest.raises(ModelEngineRefused) as refused:
        asyncio.run(routed.extract(request))
    assert str(refused.value).startswith("Gemini")
    assert refused.value.kind == kind


@pytest.mark.parametrize(
    ("kind", "status"), [("busy", 429), ("key", 502), ("unavailable", 503), ("timed_out", 504)]
)
def test_what_a_person_is_told_for_each_kind_and_never_a_500(kind: str, status: int) -> None:
    refused = ModelEngineRefused(kind, timeout_seconds=120).for_engine("Gemini")
    answer = asyncio.run(_model_engine_refused_handler(None, refused))  # type: ignore[arg-type]
    body = json.loads(bytes(answer.body))
    assert answer.status_code == status
    assert body == {"error": "model_engine_refused", "kind": kind, "detail": refused.words}
    assert body["detail"].startswith("Gemini") and body["detail"].endswith("Nothing was recorded.")
