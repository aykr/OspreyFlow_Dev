"""`_authenticate_websocket` (`services/api/app.py`) — the `/stream`
WebSocket's own auth path, exercised against a real signed JWT and a real
JWKS fixture (same pattern as `test_auth.py`), via a minimal fake standing
in for the one `WebSocket` surface this function actually touches
(`.headers`, `.query_params`, `.app.state.principal_resolver`,
`.app.state.valkey`) — not a live ASGI connection, since nothing here
needs one.

`06_DECISIONS.md` ADR-050 objection 8, built: the `?token=` bearer-in-URL path Checkpoint 2 added
is **refused outright**, replaced by `?ticket=`, a short-lived single-use value redeemed through
`services.api.ws_ticket.redeem_ws_ticket` (its own real Valkey mechanics — `GETDEL`, the TTL, the
principal round-trip — are `tests/services/api/test_ws_ticket.py`'s own live-service tests;
`redeem_ws_ticket` is faked here, deliberately, so this file stays fast and tests only
`_authenticate_websocket`'s own dispatch: header vs. ticket, and what happens when neither or both
resolve).
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from services.api.app import _authenticate_websocket
from services.api.auth import PrincipalResolutionError, PrincipalResolver
from services.api.config import ApiConfig, PostgresConfig, ValkeyConfig

from schemas.domain import Principal
from tests.conftest import default_claims, sign_token

Keypair = tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]

_TICKET_PRINCIPAL = Principal(id="ticket-analyst", clearance="OFFICIAL", org_unit="unit-1")


class _FakeAppState:
    def __init__(self, resolver: PrincipalResolver) -> None:
        self.principal_resolver = resolver
        # `_authenticate_websocket`'s own ticket path reads `.app.state.valkey`, but never touches
        # it beyond passing it straight to `redeem_ws_ticket`, which every test below fakes — a
        # real client is never constructed and this placeholder is never called.
        self.valkey = None


class _FakeApp:
    def __init__(self, resolver: PrincipalResolver) -> None:
        self.state = _FakeAppState(resolver)


class _FakeWebSocket:
    """The only surface `_authenticate_websocket` touches."""

    def __init__(
        self,
        resolver: PrincipalResolver,
        *,
        headers: dict[str, str] | None = None,
        query_params: dict[str, str] | None = None,
    ) -> None:
        self.headers = headers or {}
        self.query_params = query_params or {}
        self.app = _FakeApp(resolver)


def _resolver(jwks_url: str) -> PrincipalResolver:
    return PrincipalResolver(
        ApiConfig(
            valkey=ValkeyConfig(host="localhost", port=6379, db=0),
            postgres=PostgresConfig(
                host="localhost", port=5432, user="x", password="x", database="x"
            ),
            oidc_jwks_url=jwks_url,
            oidc_audience=None,
            oidc_issuer=None,
            oidc_algorithms=("RS256",),
            oidc_jwks_ttl_seconds=300.0,
            oidc_token_exchange_url=None,
            oidc_token_exchange_client_id=None,
            oidc_token_exchange_client_secret=None,
            supersede_job_degree_threshold=500,
            osprey_config_path="osprey.yaml",
            analytics_db_path=":memory:",
            hotlist_alert_policy="strict",
            export_manifest_policy="disclose",
        )
    )


async def test_authorization_header_resolves_a_principal(keypair: Keypair, jwks_url: str) -> None:
    private_key, _ = keypair
    token = sign_token(private_key, default_claims())
    ws = _FakeWebSocket(_resolver(jwks_url), headers={"authorization": f"Bearer {token}"})

    principal = await _authenticate_websocket(ws)  # type: ignore[arg-type]

    assert principal.id == "analyst-1"


async def test_a_valid_ticket_resolves_the_bound_principal(jwks_url: str) -> None:
    """The browser path: no `Authorization` header at all, `?ticket=` instead."""
    ws = _FakeWebSocket(_resolver(jwks_url), query_params={"ticket": "a-real-looking-ticket"})

    with patch(
        "services.api.app.redeem_ws_ticket", return_value=_TICKET_PRINCIPAL
    ) as fake_redeem:
        principal = await _authenticate_websocket(ws)  # type: ignore[arg-type]

    assert principal == _TICKET_PRINCIPAL
    fake_redeem.assert_awaited_once_with(None, "a-real-looking-ticket")


async def test_an_expired_or_already_redeemed_ticket_is_refused(jwks_url: str) -> None:
    """`redeem_ws_ticket` returns `None` for exactly this case (see its own docstring) — the
    real shape a reused or timed-out ticket takes, not a hand-picked exception."""
    ws = _FakeWebSocket(_resolver(jwks_url), query_params={"ticket": "already-used"})

    with patch("services.api.app.redeem_ws_ticket", return_value=None):
        with pytest.raises(PrincipalResolutionError):
            await _authenticate_websocket(ws)  # type: ignore[arg-type]


async def test_a_bearer_token_in_the_url_is_refused_not_merely_deprioritised(
    keypair: Keypair, jwks_url: str
) -> None:
    """ADR-050 objection 8's own closing line: "a bearer token in the URL is refused." The
    query parameter `_authenticate_websocket` reads is `ticket`, not `token` — a real signed JWT
    placed under the old `?token=` name is not a ticket, `redeem_ws_ticket` is never even asked
    about it (there is no `ticket` param to ask about), and the connection is refused exactly as
    if nothing had been sent at all. This is the real shape rule 15 asks for: the planted
    violation is the literal request Checkpoint 2's own client used to send, not a fabricated
    stand-in for "a token in a URL."
    """
    private_key, _ = keypair
    token = sign_token(private_key, default_claims())
    ws = _FakeWebSocket(_resolver(jwks_url), query_params={"token": token})

    with patch("services.api.app.redeem_ws_ticket") as fake_redeem:
        with pytest.raises(PrincipalResolutionError):
            await _authenticate_websocket(ws)  # type: ignore[arg-type]

    fake_redeem.assert_not_awaited()


async def test_the_header_wins_when_both_are_present() -> None:
    """Documents the precedence `app.py`'s docstring states — a
    non-browser client that *can* set the header is tried first."""
    # An invalid resolver call would raise before reaching the ticket branch at all if the header
    # is checked first and found valid; this test only needs to prove header presence
    # short-circuits ticket handling, so an empty (unfaked) ticket path alongside a (deliberately
    # unresolvable) header is enough to prove the branch taken, not the resolution outcome.
    ws = _FakeWebSocket(
        PrincipalResolver(
            ApiConfig(
                valkey=ValkeyConfig(host="localhost", port=6379, db=0),
                postgres=PostgresConfig(
                    host="localhost", port=5432, user="x", password="x", database="x"
                ),
                oidc_jwks_url="http://localhost:1/jwks.json",
                oidc_audience=None,
                oidc_issuer=None,
                oidc_algorithms=("RS256",),
                oidc_jwks_ttl_seconds=300.0,
                oidc_token_exchange_url=None,
                oidc_token_exchange_client_id=None,
                oidc_token_exchange_client_secret=None,
                supersede_job_degree_threshold=500,
                osprey_config_path="osprey.yaml",
                analytics_db_path=":memory:",
                hotlist_alert_policy="strict",
                export_manifest_policy="disclose",
            )
        ),
        headers={"authorization": "Bearer not-a-real-token"},
        query_params={"ticket": "also-ignored"},
    )

    with patch("services.api.app.redeem_ws_ticket") as fake_redeem:
        with pytest.raises(PrincipalResolutionError):
            await _authenticate_websocket(ws)  # type: ignore[arg-type]

    fake_redeem.assert_not_awaited()


async def test_neither_header_nor_ticket_is_rejected(jwks_url: str) -> None:
    ws = _FakeWebSocket(_resolver(jwks_url))

    with pytest.raises(PrincipalResolutionError):
        await _authenticate_websocket(ws)  # type: ignore[arg-type]
