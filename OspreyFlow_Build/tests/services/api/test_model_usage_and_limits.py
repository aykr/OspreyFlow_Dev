"""*Admin › Models*' usage and limits (`06_DECISIONS.md` ADR-135 Amendment 3), through the real app,
the real right check, the real routing (`RoutedModel` → `ModelLiteLLMAdapter` → `LiteLLMClient`) and
the stand-in gateway that records and refuses as the pinned LiteLLM was measured to (rule 15;
`tests/adapters/model_litellm/test_stand_in_gateway_usage.py`).

- the figures equal a planted gateway record, and the calls made through the real routing;
- a limit set through the route stops the next request through the real routing path, in the
  Conduit's words, never the gateway's (which name its key's hash or part of it);
- no prompt, answer, key or source-system identifier appears in any usage response, and no
  request to the gateway carries a person's id;
- the limits' changes are audited; a budget is never half set.

Access (rule 4) for the two new routes is `test_model_admin_routes.py`'s, which walks every
`/v1/admin/models` route.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from services.api.app import _model_limit_reached_handler, app, get_principal
from services.api.datasets import Dataset, InMemoryDatasetStore
from services.api.model_admin import (
    GatewayAdmin,
    InMemoryModelAdminAudit,
    Installed,
    ModelAdmin,
    ModelSettingsFile,
)
from services.api.model_routing import RoutedModel

from adapters.model_litellm.adapter import ModelLiteLLMAdapter
from adapters.model_litellm.client import LiteLLMClient, LiteLLMConfig
from adapters.model_litellm.errors import ModelLimitReached
from adapters.model_litellm.stand_in import StandInGateway, StandInProvider
from adapters.model_litellm.usage import engine_key
from schemas.domain import Handling, Principal
from schemas.model import ExtractionRequest

MASTER = "sk-stand-in-master-M4ST"
GOOD = "sk-good-provider-key-PLANT-K3Y9"
PROMPT = "PROMPT-PLANT-Q3"
ANSWER = "COMPLETION-PLANT-Z9"
SOURCE_ID = "src-system-id-PLANT-77"
ADMIN = Principal(id="admin-PERSON-PLANT-1", clearance="OFFICIAL", org_unit="u",
                  roles=["osprey-admin"])  # fmt: skip
T0 = datetime(2026, 11, 8, 10, 0, tzinfo=UTC).timestamp()
GEMINI = {"name": "gemini", "label": "Gemini", "roles": {"extraction": "gemini-2.5-flash"}}

OPEN = InMemoryDatasetStore()
OPEN.add(Dataset(id="open", name="Open", owning_unit="u", created_by="seed", egress="any",
                 created_at="2026-11-01T00:00:00Z"))  # type: ignore[arg-type]  # fmt: skip


class Clock:
    def __init__(self) -> None:
        self.now = T0

    def __call__(self) -> float:
        return self.now


class World:
    def __init__(self, tmp_path: Path, *, local_only: bool = False) -> None:
        self.clock = Clock()
        self.gateway = StandInGateway(
            master_key=MASTER,
            salt_key="salt-one",
            providers={"gemini": StandInProvider(GOOD, frozenset({"gemini-2.5-flash"}), 17, 5)},
            config_models=frozenset({"qwen2.5:7b-instruct"}),
            clock=self.clock,
            answer=json.dumps({"note": ANSWER}),
        )
        self.audit = InMemoryModelAdminAudit()
        http = httpx.AsyncClient(base_url="http://litellm:4000", transport=self.gateway.transport(),
                                 headers={"Authorization": f"Bearer {MASTER}"})  # fmt: skip
        self.admin = ModelAdmin(
            installed=Installed(
                providers=[], defaults={}, key_present={}, local_only=local_only, sendable=["O"],
                locals={"extraction": "qwen2.5:7b-instruct", "vision": None,
                        "transcription": None, "embedding": None},
            ),  # fmt: skip
            settings_file=ModelSettingsFile(tmp_path / "model-settings"),
            gateway=GatewayAdmin(http),
            audit=self.audit,
        )
        client = LiteLLMClient(LiteLLMConfig(api_key=MASTER), transport=self.gateway.transport())
        self.model = RoutedModel(
            ModelLiteLLMAdapter(client, embed_model="none"), routes=self.admin.routes(), egress=OPEN
        )
        self.model.follow(self.admin.routes)

    def extract(self) -> Any:
        request = ExtractionRequest(
            document_id=SOURCE_ID,
            text=f"{PROMPT}: what does {SOURCE_ID} say?",
            json_schema={"type": "object"},
            model="qwen2.5:7b-instruct",
            handling=Handling(classification="OFFICIAL", handling_code="O", owning_unit="u",
                              originator="u"),  # fmt: skip
            engine="gemini",
            datasets=["open"],
        )
        return asyncio.run(self.model.extract(request))


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
    c = TestClient(app)
    assert c.post("/v1/admin/models/engines", json={"provider": GEMINI}).status_code == 200
    assert c.put("/v1/admin/models/engines/gemini/key", json={"key": GOOD}).status_code == 200
    return c


def _usage(client: TestClient, start: str = "2026-11-01", end: str = "2026-11-30") -> Any:
    resp = client.get("/v1/admin/models/usage", params={"start": start, "end": end})
    assert resp.status_code == 200, resp.text
    return resp.json()


# --- the figures are the gateway's ------------------------------------------------------------


def test_the_figures_equal_a_planted_gateway_record(client: TestClient, world: World) -> None:
    g = world.gateway
    g.record_usage("2026-11-08", "osprey:gemini/extraction", calls=5, failed=1, prompt=100,
                   completion=40)  # fmt: skip
    g.record_usage("2026-11-09", "osprey:gemini/extraction", calls=2, prompt=10, completion=4)
    g.record_usage("2026-11-09", "osprey:local/vision", calls=3, prompt=30, completion=9)
    # Not ours, or outside the period: never counted.
    g.record_usage("2026-11-08", "User-Agent: python-httpx", calls=99, prompt=999)
    g.record_usage("2026-11-08", "osprey:../x", calls=7, prompt=7)
    g.record_usage("2026-10-31", "osprey:gemini/extraction", calls=1000, prompt=1000)

    view = _usage(client)
    rows = {(r["engine"], r["job"]): r for r in view["rows"]}
    assert set(rows) == {("gemini", "extraction"), ("local", "vision")}
    assert rows[("gemini", "extraction")]["figures"] == {
        "calls": 7, "succeeded": 6, "failed": 1, "prompt_tokens": 110, "completion_tokens": 44,
        "tokens": 154,
    }  # fmt: skip
    assert rows[("gemini", "extraction")]["engine_label"] == "Gemini"
    assert rows[("local", "vision")]["engine_label"] == "This deployment's own model"
    assert view["by_engine"]["local"]["calls"] == 3
    assert view["by_job"]["extraction"]["tokens"] == 154
    assert view["total"]["calls"] == 10 and view["total"]["tokens"] == 193
    one_day = _usage(client, "2026-11-09", "2026-11-09")
    assert one_day["total"]["calls"] == 5


def test_calls_through_the_real_routing_are_counted_by_engine_and_job(
    client: TestClient, world: World
) -> None:
    for _ in range(3):
        assert world.extract().engine == "gemini"
    figures = _usage(client)["by_engine"]["gemini"]
    assert (figures["calls"], figures["prompt_tokens"], figures["completion_tokens"]) == (3, 51, 15)
    assert [r["job"] for r in _usage(client)["rows"]] == ["extraction"]


def test_an_engine_removed_keeps_its_figures_named_as_removed(
    client: TestClient, world: World
) -> None:
    world.gateway.record_usage("2026-11-08", "osprey:openai/vision", calls=1)
    (row,) = _usage(client)["rows"]
    assert row["engine_label"] == "openai (no longer on this deployment)"


@pytest.mark.parametrize(
    ("start", "end", "words"),
    [("2026-11-30", "2026-11-01", "on or before"), ("2025-01-01", "2026-11-30", "at most 366")],
)
def test_a_period_backwards_or_too_long_is_refused_in_words_never_cut_short(
    client: TestClient, start: str, end: str, words: str
) -> None:
    resp = client.get("/v1/admin/models/usage", params={"start": start, "end": end})
    assert resp.status_code == 422 and words in resp.json()["detail"]["detail"]


def test_a_gateway_that_cannot_give_its_usage_is_said_in_fixed_words(
    client: TestClient, world: World
) -> None:
    world.admin._gateway._master = "unused"  # the reader keeps the client's own master key
    world.gateway.master_key = "sk-someone-else-XYZW"  # now our token is refused, echoing it
    resp = client.get("/v1/admin/models/usage")
    assert resp.status_code == 502
    assert resp.json()["detail"]["error"] == "model_usage_unavailable"
    assert "M4ST" not in resp.text and "XYZW" not in resp.text


# --- a limit stops the next request -------------------------------------------------------------


def _limits(client: TestClient, **limits: object) -> httpx.Response:
    return client.put("/v1/admin/models/engines/gemini/limits", json={"limits": limits})


def test_a_request_rate_set_stops_the_next_request_through_the_real_routing(
    client: TestClient, world: World
) -> None:
    assert _limits(client, requests_per_minute=2).status_code == 200
    world.extract()
    world.extract()
    with pytest.raises(ModelLimitReached) as stopped:
        world.extract()
    words = str(stopped.value)
    assert words.startswith("Gemini has reached its limit of requests a minute on this deployment")
    assert "Try again after 10:01 UTC" in words
    # The gateway's refusal named the key's hash: none of it reaches the words.
    refused = [s for s in world.gateway.seen if "chat/completions" in s]
    assert len(refused) == 3
    key = engine_key(MASTER, "gemini")
    assert key not in words and key[-4:] not in words and "sk-" not in words
    assert hashlib.sha256(key.encode()).hexdigest() not in words
    world.clock.now += 61
    assert world.extract().engine == "gemini"


def test_a_token_budget_set_stops_the_next_request_and_says_when_it_returns(
    client: TestClient, world: World
) -> None:
    resp = _limits(client, budget_tokens=50, budget_period="day")
    assert resp.status_code == 200
    (engine,) = resp.json()["engines"]
    assert engine["limits"]["budget_tokens"] == 50
    for _ in range(3):  # 22 tokens each: the third crosses 50 and is answered
        world.extract()
    with pytest.raises(ModelLimitReached) as stopped:
        world.extract()
    assert "Gemini has used its token budget for today" in str(stopped.value)
    assert "sk-" not in str(stopped.value) and "Current cost" not in str(stopped.value)
    assert "from midnight UTC" in str(stopped.value)


def test_what_a_person_sees_when_a_limit_stops_a_request(client: TestClient, world: World) -> None:
    _limits(client, requests_per_minute=1)
    world.extract()
    with pytest.raises(ModelLimitReached) as stopped:
        world.extract()
    answer = asyncio.run(_model_limit_reached_handler(None, stopped.value))  # type: ignore[arg-type]
    body = json.loads(bytes(answer.body))
    assert answer.status_code == 429 and body["error"] == "model_limit_reached"
    assert body["detail"].startswith("Gemini has reached its limit of requests a minute")
    assert int(answer.headers["retry-after"]) >= 1


def test_the_calls_go_with_the_engine_s_own_key_and_local_calls_with_none_of_it(
    client: TestClient, world: World
) -> None:
    world.extract()
    tokens = [token for token, _body in world.gateway.received]
    assert tokens == [engine_key(MASTER, "gemini")]
    assert engine_key(MASTER, "gemini") in world.gateway.virtual_keys()


def test_limits_are_audited_with_each_change_and_shown(client: TestClient, world: World) -> None:
    _limits(client, requests_per_minute=10, budget_tokens=1000, budget_period="month")
    _limits(client, requests_per_minute=20)
    (_first, second) = [e for e in world.audit.entries if e.action == "limits_changed"]
    assert second.changes == {
        "requests_per_minute": {"from": 10, "to": 20},
        "budget_tokens": {"from": 1000, "to": None},
        "budget_period": {"from": "month", "to": None},
    }
    held = world.gateway.virtual_key(engine_key(MASTER, "gemini"))
    assert held is not None and held.rpm_limit == 20 and held.max_budget is None
    shown = client.get("/v1/admin/models").json()["engines"][0]["limits"]
    assert shown["requests_per_minute"] == 20


@pytest.mark.parametrize(
    ("name", "limits", "status"),
    [
        ("nope", {"requests_per_minute": 1}, 404),
        ("gemini", {"budget_tokens": 10}, 422),
        ("gemini", {"requests_per_minute": 0}, 422),
        ("gemini", {"budget_dollars": 5}, 422),
    ],
)
def test_limits_refused_change_nothing(
    client: TestClient, world: World, name: str, limits: dict[str, object], status: int
) -> None:
    resp = client.put(f"/v1/admin/models/engines/{name}/limits", json={"limits": limits})
    assert resp.status_code == status
    held = world.gateway.virtual_key(engine_key(MASTER, "gemini"))
    assert held is not None and held.rpm_limit is None and held.max_budget is None


def test_an_entry_is_priced_a_unit_a_token_so_a_budget_counts_tokens(
    client: TestClient, world: World
) -> None:
    params = world.gateway.stored_params("osprey-gemini-gemini-2.5-flash")
    assert params["input_cost_per_token"] == "1" and params["output_cost_per_token"] == "1"


# --- nothing identifying leaks ------------------------------------------------------------------


def test_no_prompt_answer_key_or_source_id_appears_in_any_usage_response(
    client: TestClient, world: World
) -> None:
    _limits(client, budget_tokens=10_000, budget_period="day")
    world.extract()
    shown = " ".join(
        client.get(path).text
        for path in ("/v1/admin/models/usage", "/v1/admin/models", "/v1/admin/models/history")
    )
    assert _usage(client)["total"]["calls"] == 1  # the call is there, as a count
    for planted in (PROMPT, ANSWER, SOURCE_ID, GOOD, MASTER, engine_key(MASTER, "gemini"),
                    MASTER[-4:], GOOD[-4:]):  # fmt: skip
        assert planted not in shown, planted


def test_no_request_to_the_gateway_carries_a_person_s_id(client: TestClient, world: World) -> None:
    _limits(client, requests_per_minute=100)
    world.extract()
    every = "\n".join(world.gateway.seen)
    assert ADMIN.id not in every and "PERSON-PLANT" not in every
    for _token, body in world.gateway.received:
        assert "user" not in body and "end_user" not in body
        assert body["metadata"] == {"tags": ["osprey:gemini/extraction"]}
