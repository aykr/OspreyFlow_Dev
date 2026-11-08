"""The stand-in gateway records usage and enforces limits as the measured one does (`CLAUDE.md` rule
15; `06_DECISIONS.md` ADR-135 Amendment 3, "Measured first"). Each case is a request shape the
Conduit's own code sends; each refusal is the measured one, so no test of the Conduit against the
stand-in can pass by the stand-in being more permissive than the pinned gateway.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest

from adapters.model_litellm.stand_in import StandInGateway, StandInProvider

MASTER = "sk-stand-in-master"
GOOD = "sk-good-provider-key"
ENGINE_KEY = "sk-osprey-engine-key-WXYZ"
#: 8 November 2026, 10:00 UTC.
T0 = datetime(2026, 11, 8, 10, 0, tzinfo=UTC).timestamp()


class Clock:
    def __init__(self) -> None:
        self.now = T0

    def __call__(self) -> float:
        return self.now


def _gateway(clock: Clock) -> StandInGateway:
    gateway = StandInGateway(
        master_key=MASTER,
        salt_key="salt-one",
        providers={"gemini": StandInProvider(GOOD, frozenset({"gemini-2.5-flash"}), 17, 5)},
        config_models=frozenset({"qwen2.5:7b-instruct"}),
        clock=clock,
    )
    return gateway


def _client(gateway: StandInGateway, token: str = MASTER) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url="http://litellm:4000",
        transport=gateway.transport(),
        headers={"Authorization": f"Bearer {token}"},
    )


async def _entry(admin: httpx.AsyncClient, *, priced: bool = True, rpm: int | None = None) -> None:
    params: dict[str, Any] = {"model": "gemini/gemini-2.5-flash", "api_key": GOOD}
    if priced:
        params |= {"input_cost_per_token": 1, "output_cost_per_token": 1}
    if rpm is not None:
        params["rpm"] = rpm
    resp = await admin.post("/model/new", json={
        "model_name": "gemini/gemini-2.5-flash", "litellm_params": params,
        "model_info": {"id": "osprey-gemini-gemini-2.5-flash"},
    })  # fmt: skip
    assert resp.status_code == 200


async def _chat(client: httpx.AsyncClient, tag: str = "osprey:gemini/extraction",
                model: str = "gemini/gemini-2.5-flash") -> httpx.Response:  # fmt: skip
    return await client.post("/chat/completions", json={
        "model": model, "messages": [{"role": "user", "content": "hi"}],
        "metadata": {"tags": [tag]},
    })  # fmt: skip


async def test_each_call_is_recorded_under_its_tags_by_day_with_no_text() -> None:
    clock = Clock()
    gateway = _gateway(clock)
    async with _client(gateway) as admin:
        await _entry(admin)
        assert (await _chat(admin)).status_code == 200
        assert (await _chat(admin, "osprey:local/vision", "qwen2.5:7b-instruct")).status_code == 200
        assert (await _chat(admin, model="nope")).status_code == 400  # recorded as a failure
        resp = await admin.get(
            "/tag/daily/activity", params={"start_date": "2026-11-01", "end_date": "2026-11-30"}
        )
    assert resp.status_code == 200
    (day,) = resp.json()["results"]
    entities = day["breakdown"]["entities"]
    assert day["date"] == "2026-11-08"
    m = entities["osprey:gemini/extraction"]["metrics"]
    assert (m["api_requests"], m["successful_requests"], m["failed_requests"]) == (2, 1, 1)
    assert (m["prompt_tokens"], m["completion_tokens"], m["total_tokens"]) == (17, 5, 22)
    assert entities["osprey:local/vision"]["metrics"]["api_requests"] == 1
    # The gateway adds its own User-Agent tags (measured), which a reader must leave out.
    assert any(t.startswith("User-Agent: ") for t in entities)
    assert "hi" not in resp.text


async def test_the_activity_needs_both_dates_and_an_empty_period_is_empty() -> None:
    gateway = _gateway(Clock())
    async with _client(gateway) as admin:
        assert (await admin.get("/tag/daily/activity")).status_code == 400
        reversed_ = await admin.get(
            "/tag/daily/activity", params={"start_date": "2026-11-30", "end_date": "2026-11-01"}
        )
    assert reversed_.status_code == 200 and reversed_.json()["results"] == []


async def test_only_the_master_key_reads_the_activity() -> None:
    gateway = _gateway(Clock())
    async with _client(gateway) as admin:
        assert (await admin.post("/key/generate", json={"key": ENGINE_KEY})).status_code == 200
    async with _client(gateway, ENGINE_KEY) as engine:
        resp = await engine.get(
            "/tag/daily/activity", params={"start_date": "2026-11-01", "end_date": "2026-11-30"}
        )
    assert resp.status_code == 401 and "Only proxy admin" in resp.text


async def test_a_rate_on_a_model_entry_is_not_enforced() -> None:
    gateway = _gateway(Clock())
    async with _client(gateway) as admin:
        await _entry(admin, rpm=2)
        answers = [(await _chat(admin)).status_code for _ in range(4)]
    assert answers == [200, 200, 200, 200]


async def test_keys_are_made_found_updated_and_deleted_as_measured() -> None:
    gateway = _gateway(Clock())
    async with _client(gateway) as admin:
        assert (await admin.get("/key/info", params={"key": ENGINE_KEY})).status_code == 404
        assert (await admin.post("/key/update", json={"key": ENGINE_KEY})).status_code == 404
        assert (await admin.post("/key/delete", json={"keys": [ENGINE_KEY]})).status_code == 404
        made = await admin.post("/key/generate", json={"key": ENGINE_KEY, "key_alias": "a"})
        assert made.status_code == 200
        again = await admin.post("/key/generate", json={"key": "sk-other", "key_alias": "a"})
        assert again.status_code == 400 and "already exists" in again.text
        updated = await admin.post("/key/update", json={"key": ENGINE_KEY, "rpm_limit": 3})
        # Measured: the update's answer carries the key itself.
        assert updated.status_code == 200 and ENGINE_KEY in updated.text
        info = await admin.get("/key/info", params={"key": ENGINE_KEY})
        assert info.json()["info"]["rpm_limit"] == 3
        assert (await admin.post("/key/delete", json={"keys": [ENGINE_KEY]})).status_code == 200
    async with _client(gateway, ENGINE_KEY) as engine:
        gone = await _chat(engine)
    assert gone.status_code == 401 and "WXYZ" in gone.text


async def test_a_key_s_request_rate_refuses_once_reached_naming_its_hash() -> None:
    clock = Clock()
    gateway = _gateway(clock)
    async with _client(gateway) as admin:
        await _entry(admin)
        await admin.post("/key/generate", json={"key": ENGINE_KEY, "rpm_limit": 2})
    async with _client(gateway, ENGINE_KEY) as engine:
        answers = [await _chat(engine) for _ in range(3)]
        assert [a.status_code for a in answers] == [200, 200, 429]
        refused = answers[2].json()["error"]
        assert refused["type"] == "throttling_error"
        assert "Limit type: requests" in refused["message"]
        assert hashlib.sha256(ENGINE_KEY.encode()).hexdigest() in refused["message"]
        clock.now += 61
        assert (await _chat(engine)).status_code == 200


async def test_a_key_s_token_rate_answers_the_crossing_call_and_refuses_the_next() -> None:
    gateway = _gateway(Clock())
    async with _client(gateway) as admin:
        await _entry(admin)
        await admin.post("/key/generate", json={"key": ENGINE_KEY, "tpm_limit": 30})
    async with _client(gateway, ENGINE_KEY) as engine:
        answers = [await _chat(engine) for _ in range(3)]
    assert [a.status_code for a in answers] == [200, 200, 429]
    assert "Limit type: tokens" in answers[2].json()["error"]["message"]


async def test_a_token_budget_answers_the_crossing_call_refuses_the_next_and_resets() -> None:
    clock = Clock()
    gateway = _gateway(clock)
    async with _client(gateway) as admin:
        await _entry(admin)  # one unit a token, as the Conduit prices every hosted entry
        await admin.post("/key/generate", json={
            "key": ENGINE_KEY, "key_alias": "osprey-engine-gemini", "max_budget": 50,
            "budget_duration": "1d",
        })  # fmt: skip
    async with _client(gateway, ENGINE_KEY) as engine:
        answers = [await _chat(engine) for _ in range(4)]
        assert [a.status_code for a in answers] == [200, 200, 200, 429]
        refused = answers[3].json()["error"]
        assert refused["type"] == "budget_exceeded"
        assert "sk-...WXYZ" in refused["message"]  # it echoes the key's last four
        clock.now = datetime(2026, 11, 9, 0, 0, 1, tzinfo=UTC).timestamp()
        assert (await _chat(engine)).status_code == 200
    async with _client(gateway) as admin:
        resp = await admin.get(
            "/tag/daily/activity", params={"start_date": "2026-11-08", "end_date": "2026-11-08"}
        )
    m = resp.json()["results"][0]["breakdown"]["entities"]["osprey:gemini/extraction"]["metrics"]
    assert (m["api_requests"], m["failed_requests"]) == (4, 1)  # the budget's refusal is a failure


@pytest.mark.parametrize(("duration", "resets"), [("1d", "2026-11-09T00:00:00+00:00"),
                                                  ("30d", "2026-12-01T00:00:00+00:00")])
async def test_a_budget_resets_as_measured(duration: str, resets: str) -> None:
    gateway = _gateway(Clock())
    async with _client(gateway) as admin:
        await _entry(admin)
        await admin.post("/key/generate", json={
            "key": ENGINE_KEY, "max_budget": 1000, "budget_duration": duration})  # fmt: skip
        async with _client(gateway, ENGINE_KEY) as engine:
            await _chat(engine)
        info = await admin.get("/key/info", params={"key": ENGINE_KEY})
    assert info.json()["info"]["budget_reset_at"] == resets


async def test_an_unpriced_entry_spends_nothing_so_its_budget_never_stops_it() -> None:
    gateway = _gateway(Clock())
    async with _client(gateway) as admin:
        await _entry(admin, priced=False)
        await admin.post("/key/generate", json={"key": ENGINE_KEY, "max_budget": 1,
                                                "budget_duration": "1d"})  # fmt: skip
    async with _client(gateway, ENGINE_KEY) as engine:
        assert [(await _chat(engine)).status_code for _ in range(3)] == [200, 200, 200]
