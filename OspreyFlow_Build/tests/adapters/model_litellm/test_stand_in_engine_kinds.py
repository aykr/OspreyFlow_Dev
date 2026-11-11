"""The stand-in's two new upstreams refuse as the real ones do, before any test of *Admin › Models*'
engine kinds is trusted against them (`06_DECISIONS.md` ADR-135 Amendment 4; `CLAUDE.md` rule 15's
second worked example: a fixture models the dependency's refusals, not only its grants).

- **The client's own AI gateway** (OpenAI-compatible, reached through LiteLLM's `openai/` route at
  its address): no token, a wrong token, a model it does not offer.
- **Bedrock in London**, signed by the gateway pod's own identity (the namespace's IAM role): no
  identity at all, a role the account does not allow, a region other than London, a model not
  offered, throttling.

Each request is the shape `GatewayAdmin.add_entry` writes and `check_connection` sends; each
refusal is the status and words LiteLLM gives back, so `connection.classify` sees what it would.
"""

from __future__ import annotations

from typing import Any

import httpx

from adapters.model_litellm.connection import classify
from adapters.model_litellm.stand_in import (
    StandInBedrock,
    StandInClientGateway,
    StandInGateway,
)

MASTER = "sk-stand-in-master"
TOKEN = "gw-token-for-the-client-gateway"
PLANTED = "gw-PLANTED-wrong-token-7Q4Z"
BASE = "https://ai-gateway.client.example/v1"
ROLE = "arn:aws:iam::000000000000:role/osprey-gateway"
CLAUDE = "anthropic.claude-3-haiku-20240307-v1:0"


def _gateway(*, role: str | None = ROLE, token: str | None = TOKEN) -> StandInGateway:
    return StandInGateway(
        master_key=MASTER,
        salt_key="salt-one",
        providers={},
        client_gateways={BASE: StandInClientGateway(token, frozenset({"gpt-4o-mini"}))},
        bedrock=StandInBedrock(allowed_roles=frozenset({ROLE}), offered_models=frozenset({CLAUDE})),
        workload_role=role,
    )


def _client(gateway: StandInGateway) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url="http://litellm:4000",
        transport=gateway.transport(),
        headers={"Authorization": f"Bearer {MASTER}"},
    )


async def _add(client: httpx.AsyncClient, model_name: str, params: dict[str, Any]) -> None:
    resp = await client.post(
        "/model/new",
        json={"model_name": model_name, "litellm_params": params,
              "model_info": {"id": "osprey-" + model_name.replace("/", "-")}},
    )  # fmt: skip
    assert resp.status_code == 200


async def _chat(client: httpx.AsyncClient, model: str) -> httpx.Response:
    return await client.post(
        "/chat/completions",
        json={"model": model, "messages": [{"role": "user", "content": "Reply with OK."}],
              "max_tokens": 1},
    )  # fmt: skip


async def _with_token(gateway: StandInGateway, token: str | None, model: str) -> httpx.Response:
    async with _client(gateway) as client:
        params: dict[str, Any] = {"model": f"openai/{model}", "api_base": BASE}
        if token is not None:
            await client.post("/credentials", json={
                "credential_name": "osprey-acme", "credential_values": {"api_key": token},
                "credential_info": {}})  # fmt: skip
            params["litellm_credential_name"] = "osprey-acme"
        await _add(client, f"acme/{model}", params)
        return await _chat(client, f"acme/{model}")


# --- the client's own gateway ------------------------------------------------------------------


async def test_the_client_gateway_answers_its_own_token_at_its_own_address() -> None:
    gateway = _gateway()
    ok = await _with_token(gateway, TOKEN, "gpt-4o-mini")
    assert ok.status_code == 200
    assert gateway.sent == [(BASE, TOKEN)]


async def test_the_client_gateway_with_no_token_is_refused_before_anything_is_sent() -> None:
    # LiteLLM's OpenAI client will not send a request without a key (measured on the pinned image
    # for the provider route, the same client): an IAM-role engine on this route is refused here.
    gateway = _gateway()
    refused = await _with_token(gateway, None, "gpt-4o-mini")
    assert refused.status_code == 500 and "api_key client option must be set" in refused.text
    assert classify(refused.status_code, refused.text) == "key_refused"
    assert gateway.sent == []


async def test_the_client_gateway_refuses_a_wrong_token_and_echoes_part_of_it() -> None:
    gateway = _gateway()
    refused = await _with_token(gateway, PLANTED, "gpt-4o-mini")
    assert refused.status_code == 401
    assert PLANTED[-4:] in refused.text  # what the Conduit must never pass on
    assert classify(refused.status_code, refused.text) == "key_refused"


async def test_the_client_gateway_refuses_a_model_it_does_not_offer() -> None:
    refused = await _with_token(_gateway(), TOKEN, "gpt-5-unoffered")
    assert refused.status_code == 404
    assert classify(refused.status_code, refused.text) == "model_not_offered"


async def test_an_address_with_no_gateway_behind_it_is_not_reachable() -> None:
    gateway = _gateway()
    async with _client(gateway) as client:
        await _add(client, "acme/gpt-4o-mini",
                   {"model": "openai/gpt-4o-mini", "api_base": "https://elsewhere.example/v1",
                    "api_key": TOKEN})  # fmt: skip
        refused = await _chat(client, "acme/gpt-4o-mini")
    assert classify(refused.status_code, refused.text) == "unreachable"


# --- Bedrock by the namespace's IAM role --------------------------------------------------------


async def _bedrock(gateway: StandInGateway, *, region: str = "eu-west-2",
                   model: str = CLAUDE) -> httpx.Response:  # fmt: skip
    async with _client(gateway) as client:
        await _add(client, f"bedrock/{model}",
                   {"model": f"bedrock/{model}", "aws_region_name": region})  # fmt: skip
        return await _chat(client, f"bedrock/{model}")


async def test_bedrock_answers_the_gateway_pod_s_own_role_in_london_with_no_key() -> None:
    gateway = _gateway()
    ok = await _bedrock(gateway)
    assert ok.status_code == 200
    assert gateway.signed == [(ROLE, "eu-west-2")]


async def test_bedrock_with_no_identity_on_the_gateway_pod_is_refused() -> None:
    refused = await _bedrock(_gateway(role=None))
    assert refused.status_code == 500 and "Unable to locate credentials" in refused.text
    assert classify(refused.status_code, refused.text) == "key_refused"


async def test_bedrock_refuses_a_role_the_account_does_not_allow() -> None:
    refused = await _bedrock(_gateway(role="arn:aws:iam::000000000000:role/someone-else"))
    assert refused.status_code == 403 and "not authorized to perform" in refused.text
    assert classify(refused.status_code, refused.text) == "key_refused"


async def test_bedrock_refuses_a_region_other_than_london() -> None:
    refused = await _bedrock(_gateway(), region="us-east-1")
    assert refused.status_code == 403 and "explicit deny" in refused.text
    assert classify(refused.status_code, refused.text) == "key_refused"


async def test_bedrock_refuses_a_model_it_does_not_offer() -> None:
    refused = await _bedrock(_gateway(), model="anthropic.claude-unoffered-v9:0")
    assert refused.status_code == 400 and "model identifier is invalid" in refused.text
    assert classify(refused.status_code, refused.text) == "model_not_offered"


async def test_bedrock_refuses_when_the_role_does_not_trust_the_gateway_s_service_account() -> None:
    gateway = _gateway()
    assert gateway.bedrock is not None
    gateway.bedrock.trusts_service_account = False
    refused = await _bedrock(gateway)
    assert refused.status_code == 500 and "AssumeRoleWithWebIdentity" in refused.text
    assert classify(refused.status_code, refused.text) == "key_refused"
    assert gateway.signed == []


async def test_bedrock_refuses_a_model_offered_only_through_an_inference_profile() -> None:
    gateway = _gateway()
    assert gateway.bedrock is not None
    gateway.bedrock.profile_only_models = frozenset({CLAUDE})
    refused = await _bedrock(gateway)
    assert refused.status_code == 400 and "on-demand throughput" in refused.text
    assert classify(refused.status_code, refused.text) == "model_not_offered"


async def test_bedrock_throttling_is_a_rate_limit_not_a_cooldown() -> None:
    gateway = _gateway()
    assert gateway.bedrock is not None
    gateway.bedrock.throttled = True
    refused = await _bedrock(gateway)
    assert refused.status_code == 429
    assert classify(refused.status_code, refused.text) == "rate_limited"
