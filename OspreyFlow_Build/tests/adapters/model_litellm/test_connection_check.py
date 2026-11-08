"""*Test the connection* (`06_DECISIONS.md` ADR-135 Amendment 2 decision 5): each of the measured
gateway answers is reported in its own fixed words, and no word of the gateway's or the provider's —
which can carry part of a key — ever reaches the result. Run against the stand-in, shown to refuse
as the real gateway does in `test_stand_in_gateway.py` (rule 15).
"""

from __future__ import annotations

import httpx
import pytest

from adapters.model_litellm.connection import WORDS, check_connection, classify
from adapters.model_litellm.stand_in import StandInGateway, StandInProvider

MASTER = "sk-stand-in-master"
GOOD = "sk-good-provider-key"
PLANTED = "sk-PLANTED-wrong-key-7Q4Z"


class Clock:
    now = 0.0

    def __call__(self) -> float:
        return self.now


async def _setup(
    key: str | None,
    model: str = "gemini-2.5-flash",
    token: str = MASTER,
    clock: Clock | None = None,
) -> tuple[StandInGateway, httpx.AsyncClient]:
    gateway = StandInGateway(
        master_key=MASTER,
        salt_key="s",
        providers={"gemini": StandInProvider(GOOD, frozenset({"gemini-2.5-flash"}))},
        clock=clock or Clock(),
    )
    params = {"model": f"gemini/{model}", **({"api_key": key} if key else {})}
    admin = httpx.AsyncClient(
        base_url="http://litellm:4000",
        transport=gateway.transport(),
        headers={"Authorization": f"Bearer {MASTER}"},
    )
    await admin.post(
        "/model/new",
        json={
            "model_name": "gemini/gemini-2.5-flash",
            "litellm_params": params,
            "model_info": {"id": "e"},
        },
    )
    await admin.aclose()
    client = httpx.AsyncClient(
        base_url="http://litellm:4000",
        transport=gateway.transport(),
        headers={"Authorization": f"Bearer {token}"},
    )
    return gateway, client


@pytest.mark.parametrize(
    ("key", "model", "token", "outcome"),
    [
        (GOOD, "gemini-2.5-flash", MASTER, "ok"),
        (PLANTED, "gemini-2.5-flash", MASTER, "key_refused"),
        (None, "gemini-2.5-flash", MASTER, "key_refused"),
        (GOOD, "gemini-ultra", MASTER, "model_not_offered"),
        (GOOD, "gemini-2.5-flash", "sk-wrong-master-ABCD", "gateway_token"),
    ],
)
async def test_each_answer_is_reported_in_its_own_words(
    key: str | None, model: str, token: str, outcome: str
) -> None:
    _, client = await _setup(key, model, token)
    async with client:
        check = await check_connection(client, "gemini/gemini-2.5-flash")
    assert check.outcome == outcome
    assert check.words == WORDS[outcome]  # type: ignore[index]


async def test_a_model_the_gateway_has_no_route_for_says_so() -> None:
    _, client = await _setup(GOOD)
    async with client:
        check = await check_connection(client, "gemini/never-added")
    assert check.outcome == "not_routed"


async def test_a_retest_right_after_a_failure_says_try_again_in_a_minute() -> None:
    gateway, client = await _setup(PLANTED)
    async with client:
        assert (await check_connection(client, "gemini/gemini-2.5-flash")).outcome == "key_refused"
        await client.patch("/model/e/update", json={"litellm_params": {"api_key": GOOD}})
        check = await check_connection(client, "gemini/gemini-2.5-flash")
    assert check.outcome == "cooling_down"
    assert "try again in a minute" in check.words
    assert gateway.asked  # the gateway was asked, and it is the gateway that held it back


async def test_an_unreachable_gateway_is_reported_not_raised() -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    async with httpx.AsyncClient(
        base_url="http://litellm:4000", transport=httpx.MockTransport(refuse)
    ) as client:
        check = await check_connection(client, "gemini/gemini-2.5-flash")
    assert check.outcome == "unreachable" and check.status is None


async def test_the_echoed_key_fragment_never_reaches_the_result() -> None:
    """The stand-in echoes `sk-PLA****7Q4Z`, as the real provider did; nothing of it, nor of the
    proxy token's echo, may be in what the check returns."""
    for key, token in ((PLANTED, MASTER), (GOOD, "sk-wrong-master-7Q4Z")):
        _, client = await _setup(key, token=token)
        async with client:
            check = await check_connection(client, "gemini/gemini-2.5-flash")
        shown = repr(check) + check.words
        assert "7Q4Z" not in shown and "sk-PLA" not in shown


def test_a_rate_limit_that_names_no_cooldown_is_the_provider_limiting_the_key() -> None:
    assert classify(429, '{"error":{"message":"litellm.RateLimitError: quota"}}') == "rate_limited"
    assert classify(503, "Service Unavailable") == "unreachable"
