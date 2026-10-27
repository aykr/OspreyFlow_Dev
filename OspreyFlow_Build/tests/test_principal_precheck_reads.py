"""The revoked-principal pre-check's reads of the identity provider, over an httpx `MockTransport`
(`06_DECISIONS.md` ADR-043's amendments of 24 and 27 October 2026). Hermetic: no Keycloak. The
live counterparts are in `tests/services/api/test_revoked_principal_precheck.py` (`make idp-test`).

The mock models the real IdP's refusals as well as its grants (rule 15): `users/{id}` answers 404
for an id no user has, `users?username=` answers a list, a realm root answers 200 with an object
that is not a user, and the token endpoint can fail. What a mistake would do, and the case that
catches it:

- the exchange asking for the original string when the pre-check resolved the user by username, so
  the exchange and the pre-check judge different subjects
  (`test_the_exchange_asks_for_the_id_the_precheck_resolved`);
- a 200 that is not the owner's user (a URL left at the realm root) passing everyone
  (`test_a_200_that_is_not_the_owners_user_is_unavailable_not_a_pass`,
  `test_the_username_read_must_answer_a_list`);
- the pre-check's token failure escaping as a raw httpx error, not the unreachable path
  (`test_a_token_endpoint_failure_in_the_precheck_is_unavailable`)."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from principal_auth import (
    OidcResolverSettings,
    PrincipalExchangeUnavailable,
    PrincipalResolver,
    PrincipalRevoked,
)
from schemas.domain import Principal

ADMIN = "http://idp.test/admin/realms/osprey/users"
TOKEN = "http://idp.test/realms/osprey/protocol/openid-connect/token"
SUBJECT_ID = "5b1d0c1e-0000-4000-8000-00000000a001"


class Idp:
    """A transport answering the three calls the resolver makes, keeping what it was asked."""

    def __init__(
        self,
        *,
        by_id: httpx.Response | None = None,
        by_username: httpx.Response | None = None,
        token: httpx.Response | None = None,
    ) -> None:
        self.by_id = by_id or httpx.Response(404, json={"error": "User not found"})
        self.by_username = by_username or httpx.Response(200, json=[])
        self.token = token or httpx.Response(200, json={"access_token": "client-token"})
        self.exchanges: list[dict[str, str]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url == TOKEN and request.method == "POST":
            body = dict(httpx.QueryParams(request.content.decode()))
            if body.get("grant_type") == "client_credentials":
                return self.token
            self.exchanges.append(body)
            return httpx.Response(200, json={"access_token": "exchanged"})
        if url.startswith(f"{ADMIN}?"):
            return self.by_username
        if url.startswith(f"{ADMIN}/"):
            return self.by_id
        return httpx.Response(404)


def _resolver(idp: Idp, monkeypatch: pytest.MonkeyPatch) -> PrincipalResolver:
    resolver = PrincipalResolver(
        OidcResolverSettings(
            oidc_jwks_url="http://idp.test/certs",
            oidc_token_exchange_url=TOKEN,
            oidc_token_exchange_client_id="osprey-conduit",
            oidc_token_exchange_client_secret="secret",
            oidc_admin_users_url=ADMIN,
        )
    )
    resolver._exchange_http = httpx.AsyncClient(transport=httpx.MockTransport(idp))
    monkeypatch.setattr(
        resolver, "resolve", lambda token: Principal(id="p", clearance="OFFICIAL", org_unit="u")
    )
    return resolver


def _user(**fields: Any) -> dict[str, Any]:
    return {"id": SUBJECT_ID, "username": "analyst.one", "enabled": True, **fields}


async def test_the_exchange_asks_for_the_id_the_precheck_resolved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    idp = Idp(by_username=httpx.Response(200, json=[_user()]))
    resolver = _resolver(idp, monkeypatch)
    await resolver.resolve_for_owner_detailed("analyst.one")
    assert [e["requested_subject"] for e in idp.exchanges] == [SUBJECT_ID]


async def test_the_exchange_for_an_owner_found_by_id_asks_for_that_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    idp = Idp(by_id=httpx.Response(200, json=_user()))
    resolver = _resolver(idp, monkeypatch)
    await resolver.resolve_for_owner_detailed(SUBJECT_ID)
    assert [e["requested_subject"] for e in idp.exchanges] == [SUBJECT_ID]


async def test_a_disabled_owner_found_by_username_is_revoked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    idp = Idp(by_username=httpx.Response(200, json=[_user(enabled=False)]))
    resolver = _resolver(idp, monkeypatch)
    with pytest.raises(PrincipalRevoked):
        await resolver.resolve_for_owner_detailed("analyst.one")
    assert idp.exchanges == []


@pytest.mark.parametrize(
    "answer",
    [
        httpx.Response(200, json={"realm": "osprey", "enabled": True}),
        httpx.Response(200, json=_user(id="someone-else")),
        httpx.Response(200, json=[_user()]),
    ],
    ids=["realm root", "another user's id", "a list from the by-id read"],
)
async def test_a_200_that_is_not_the_owners_user_is_unavailable_not_a_pass(
    answer: httpx.Response, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A URL left at the realm root answers 200 with an object whose `enabled` is true: every owner
    would pass. The real by-id read answers the user, whose id is the one asked for."""
    idp = Idp(by_id=answer)
    resolver = _resolver(idp, monkeypatch)
    with pytest.raises(PrincipalExchangeUnavailable):
        await resolver.resolve_for_owner_detailed(SUBJECT_ID)
    assert idp.exchanges == []


async def test_the_username_read_must_answer_a_list(monkeypatch: pytest.MonkeyPatch) -> None:
    idp = Idp(by_username=httpx.Response(200, json={"realm": "osprey", "enabled": True}))
    resolver = _resolver(idp, monkeypatch)
    with pytest.raises(PrincipalExchangeUnavailable):
        await resolver.resolve_for_owner_detailed("analyst.one")
    assert idp.exchanges == []


async def test_a_token_endpoint_failure_in_the_precheck_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    idp = Idp(token=httpx.Response(503, text="unavailable"))
    resolver = _resolver(idp, monkeypatch)
    with pytest.raises(PrincipalExchangeUnavailable):
        await resolver._refuse_if_revoked("analyst.one")
