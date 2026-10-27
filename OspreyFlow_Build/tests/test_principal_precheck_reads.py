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
  (`test_a_token_endpoint_failure_in_the_precheck_is_unavailable`);
- a 200 that is not JSON, a token response with no `access_token` and a list where an object is
  promised escaping `resolve_for_owner` as `JSONDecodeError`/`KeyError`/`AttributeError`, none of
  them a `PrincipalExchangeError` (`test_a_malformed_*_is_unavailable_and_resolves_to_none`);
- a username read that ignores `exact=true` answering several users, or a prefix match, and the
  first being exchanged (`test_the_username_read_*`); the mock answers as a real realm does
  (it honours or ignores `exact`, and refuses an exchange with no `subject_token`, RFC 8693 §2.1:
  `test_the_idp_refuses_an_exchange_without_a_subject_token`)."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from principal_auth import (
    OidcResolverSettings,
    PrincipalExchangeRefused,
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
        exchange: httpx.Response | None = None,
        directory: list[dict[str, Any]] | None = None,
        honours_exact: bool = True,
    ) -> None:
        self.by_id = by_id or httpx.Response(404, json={"error": "User not found"})
        self.by_username = by_username or httpx.Response(200, json=[])
        self.token = token or httpx.Response(200, json={"access_token": "client-token"})
        self.exchange = exchange or httpx.Response(200, json={"access_token": "exchanged"})
        #: When given, the username read is answered from it as a realm answers: `exact=true`
        #: matches the whole username; without it (or where `honours_exact` is false, a proxy or a
        #: version that drops the parameter) the query is a prefix search and may answer several.
        self.directory = directory
        self.honours_exact = honours_exact
        self.exchanges: list[dict[str, str]] = []
        self.refused_exchanges: list[dict[str, str]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url == TOKEN and request.method == "POST":
            body = dict(httpx.QueryParams(request.content.decode()))
            if body.get("grant_type") == "client_credentials":
                return self.token
            if not body.get("subject_token"):
                # RFC 8693 §2.1: REQUIRED. A real Keycloak refuses it outright; so does this.
                self.refused_exchanges.append(body)
                return httpx.Response(403, json={"error": "access_denied"})
            self.exchanges.append(body)
            return self.exchange
        if url.startswith(f"{ADMIN}?"):
            if self.directory is not None:
                wanted = request.url.params.get("username", "")
                exact = self.honours_exact and request.url.params.get("exact") == "true"
                return httpx.Response(
                    200,
                    json=[
                        u
                        for u in self.directory
                        if (u["username"] == wanted if exact else u["username"].startswith(wanted))
                    ],
                )
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


async def test_the_idp_refuses_an_exchange_without_a_subject_token() -> None:
    """The mock must be able to refuse what the real realm refuses (rule 15), or the exchange
    tests below prove only that the code agrees with the mock."""
    idp = Idp()
    async with httpx.AsyncClient(transport=httpx.MockTransport(idp)) as client:
        refused = await client.post(
            TOKEN, data={"grant_type": "urn:ietf:params:oauth:grant-type:token-exchange"}
        )
    assert refused.status_code == 403 and idp.exchanges == [] and len(idp.refused_exchanges) == 1


async def test_every_exchange_carries_a_subject_token(monkeypatch: pytest.MonkeyPatch) -> None:
    idp = Idp(by_username=httpx.Response(200, json=[_user()]))
    resolver = _resolver(idp, monkeypatch)
    await resolver.resolve_for_owner_detailed("analyst.one")
    assert idp.refused_exchanges == []
    assert [e["subject_token"] for e in idp.exchanges] == ["client-token"]


# --- a malformed answer is the unreachable path, never an exception of its own ---------------

_NOT_JSON = httpx.Response(200, text="<html>gateway</html>")


@pytest.mark.parametrize(
    "idp",
    [
        Idp(by_id=_NOT_JSON),
        Idp(by_username=_NOT_JSON),
        Idp(token=_NOT_JSON),
        Idp(token=httpx.Response(200, json={"token_type": "Bearer"})),
        Idp(token=httpx.Response(200, json=["client-token"])),
        Idp(token=httpx.Response(200, json={"access_token": None})),
        Idp(by_username=httpx.Response(200, json=[_user()]), exchange=_NOT_JSON),
        Idp(by_username=httpx.Response(200, json=[_user()]), exchange=httpx.Response(200, json=[])),
        Idp(
            by_username=httpx.Response(200, json=[_user()]),
            exchange=httpx.Response(200, json={"token_type": "Bearer"}),
        ),
        Idp(
            by_username=httpx.Response(200, json=[_user()]),
            exchange=httpx.Response(200, json={"access_token": ""}),
        ),
    ],
    ids=[
        "by-id read not JSON",
        "username read not JSON",
        "client token not JSON",
        "client token without access_token",
        "client token a list",
        "client access_token null",
        "exchange not JSON",
        "exchange a list",
        "exchange without access_token",
        "exchange empty access_token",
    ],
)
async def test_a_malformed_answer_is_unavailable_and_resolves_to_none(
    idp: Idp, monkeypatch: pytest.MonkeyPatch
) -> None:
    resolver = _resolver(idp, monkeypatch)
    with pytest.raises(PrincipalExchangeUnavailable):
        await resolver.resolve_for_owner_detailed("analyst.one")
    assert await resolver.resolve_for_owner("analyst.one") is None


# --- the username read: exactly one user, and the one asked for -------------------------------

ONE = _user(username="analyst.one")
LONGER = _user(id="5b1d0c1e-0000-4000-8000-00000000a002", username="analyst.one.deputy")


async def test_the_username_read_with_exact_honoured_exchanges_the_one_user(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    idp = Idp(directory=[ONE, LONGER])
    resolver = _resolver(idp, monkeypatch)
    await resolver.resolve_for_owner_detailed("analyst.one")
    assert [e["requested_subject"] for e in idp.exchanges] == [SUBJECT_ID]


async def test_the_username_read_that_ignores_exact_and_answers_several_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The real query is `exact=true`; a realm, proxy or version that drops it answers every user
    whose name starts with the text, and the first must not be exchanged as if it were the owner."""
    idp = Idp(directory=[LONGER, ONE], honours_exact=False)
    resolver = _resolver(idp, monkeypatch)
    with pytest.raises(PrincipalExchangeUnavailable):
        await resolver.resolve_for_owner_detailed("analyst.one")
    assert idp.exchanges == []


async def test_the_username_read_answering_only_a_longer_name_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One user, but not the one asked for (a prefix match): not exchanged."""
    idp = Idp(directory=[LONGER], honours_exact=False)
    resolver = _resolver(idp, monkeypatch)
    with pytest.raises(PrincipalExchangeUnavailable):
        await resolver.resolve_for_owner_detailed("analyst.one")
    assert idp.exchanges == []


async def test_the_username_read_answering_no_user_is_still_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    idp = Idp(directory=[LONGER])
    resolver = _resolver(idp, monkeypatch)
    with pytest.raises(PrincipalExchangeRefused):
        await resolver.resolve_for_owner_detailed("analyst.one")
    assert idp.exchanges == []
