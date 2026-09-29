"""Browser sign-in against the realm: `harness/oidc.py` (`06_DECISIONS.md` ADR-051).

Every case runs the real code against a real loopback provider that can refuse
(`tests/harness/fake_idp.py`), one bent condition at a time, and each names the failure it would
catch. Two outcomes are kept apart on purpose (ADR-044): the provider unreachable, and the provider
saying no.
"""

from __future__ import annotations

import time
import urllib.parse
from collections.abc import Iterator

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from harness.oidc import (
    IdentityProviderUnreachable,
    LoginAttempts,
    SessionStore,
    SignInConfig,
    SignInRefused,
)

from harness import oidc
from tests.harness.fake_idp import AuthorisationRefused, FakeIdentityProvider

CLIENT = "osprey-harness"
REDIRECT = "http://localhost:7000/callback"
USERS = {"ada": ["osprey-admin"], "grace": ["analyst"], "nobody": []}


@pytest.fixture
def idp() -> Iterator[FakeIdentityProvider]:
    provider = FakeIdentityProvider(client_id=CLIENT, redirect_uri=REDIRECT, users=dict(USERS))
    try:
        yield provider
    finally:
        try:
            provider.stop()
        except Exception:  # already stopped by the test
            pass


def _config(idp: FakeIdentityProvider) -> SignInConfig:
    return SignInConfig(
        issuer=idp.issuer,
        client_id=CLIENT,
        redirect_uri=REDIRECT,
        post_logout_uri="http://localhost:7000/",
    )


def _sign_in(
    idp: FakeIdentityProvider, username: str = "ada", attempts: LoginAttempts | None = None
):
    """The whole browser round trip, returning (config, attempts, callback query)."""
    config = _config(idp)
    attempts = attempts or LoginAttempts()
    callback = idp.authorise(attempts.start(config), username=username)
    query = {
        k: v[0] for k, v in urllib.parse.parse_qs(urllib.parse.urlparse(callback).query).items()
    }
    return config, attempts, query


def _finish(idp: FakeIdentityProvider, username: str = "ada"):
    config, attempts, query = _sign_in(idp, username)
    return oidc.complete(config, code=query["code"], attempt=attempts.finish(query["state"]))


# --- the address the browser is sent to ---


def test_the_sign_in_address_asks_for_code_and_pkce_s256_with_the_exact_redirect(
    idp: FakeIdentityProvider,
) -> None:
    """Catches a plain-challenge or missing-challenge request (an intercepted code would then be
    redeemable), a loose redirect, and a secret leaking into a public client's address."""
    url = LoginAttempts().start(_config(idp))
    query = {k: v[0] for k, v in urllib.parse.parse_qs(urllib.parse.urlparse(url).query).items()}

    assert url.startswith(idp.issuer + "/protocol/openid-connect/auth?")
    assert query["response_type"] == "code"
    assert query["client_id"] == CLIENT
    assert query["redirect_uri"] == REDIRECT
    assert query["code_challenge_method"] == "S256"
    assert query["code_challenge"] and query["state"] and query["nonce"]
    assert "secret" not in url
    assert "code_verifier" not in url, "the verifier must stay in this process"


def test_two_sign_ins_never_share_state_nonce_or_challenge(idp: FakeIdentityProvider) -> None:
    attempts = LoginAttempts()
    first = urllib.parse.parse_qs(urllib.parse.urlparse(attempts.start(_config(idp))).query)
    second = urllib.parse.parse_qs(urllib.parse.urlparse(attempts.start(_config(idp))).query)
    for key in ("state", "nonce", "code_challenge"):
        assert first[key] != second[key]


# --- the happy path, and what identity it yields ---


def test_a_full_sign_in_yields_the_subject_username_and_roles(idp: FakeIdentityProvider) -> None:
    identity = _finish(idp, "ada")
    assert identity.username == "ada"
    assert identity.subject == "sub-ada"
    assert identity.roles == ("osprey-admin",)
    assert identity.has_role("osprey-admin")


def test_an_account_with_no_roles_claim_content_has_no_roles_rather_than_failing(
    idp: FakeIdentityProvider,
) -> None:
    assert _finish(idp, "nobody").roles == ()


# --- refusals by the provider ---


def test_a_wrong_pkce_verifier_is_refused_by_the_provider_as_a_refusal(
    idp: FakeIdentityProvider,
) -> None:
    """Catches a client that sends a different verifier from the one it hashed: the provider says
    no, and that is `SignInRefused`, not 'unreachable'."""
    config, attempts, query = _sign_in(idp)
    attempt = attempts.finish(query["state"])
    attempt.verifier = "not-the-verifier-that-was-hashed"

    with pytest.raises(SignInRefused) as refused:
        oidc.complete(config, code=query["code"], attempt=attempt)
    assert refused.value.reason == "code_rejected"


def test_a_code_cannot_be_redeemed_twice(idp: FakeIdentityProvider) -> None:
    config, attempts, query = _sign_in(idp)
    attempt = attempts.finish(query["state"])
    oidc.complete(config, code=query["code"], attempt=attempt)

    with pytest.raises(SignInRefused):
        oidc.complete(config, code=query["code"], attempt=attempt)


def test_the_provider_refuses_a_redirect_that_is_not_the_registered_one(
    idp: FakeIdentityProvider,
) -> None:
    """The fixture models the realm's exact-redirect rule, so a client built with any other
    redirect cannot get a code at all."""
    config = SignInConfig(
        issuer=idp.issuer,
        client_id=CLIENT,
        redirect_uri="http://localhost:7000/somewhere-else",
        post_logout_uri="http://localhost:7000/",
    )
    with pytest.raises(AuthorisationRefused):
        idp.authorise(LoginAttempts().start(config), username="ada")


# --- state ---


def test_an_unknown_state_is_refused() -> None:
    with pytest.raises(SignInRefused) as refused:
        LoginAttempts().finish("never-issued")
    assert refused.value.reason == "unknown_or_expired_state"


def test_a_state_can_be_used_once(idp: FakeIdentityProvider) -> None:
    """Catches a callback that can be replayed with the same state."""
    _, attempts, query = _sign_in(idp)
    attempts.finish(query["state"])
    with pytest.raises(SignInRefused):
        attempts.finish(query["state"])


def test_a_state_expires(idp: FakeIdentityProvider) -> None:
    now = [1000.0]
    attempts = LoginAttempts(clock=lambda: now[0])
    _, _, query = _sign_in(idp, attempts=attempts)
    now[0] += oidc.ATTEMPT_TTL_SECONDS + 1
    with pytest.raises(SignInRefused):
        attempts.finish(query["state"])


def test_started_sign_ins_are_bounded(idp: FakeIdentityProvider) -> None:
    attempts = LoginAttempts()
    for _ in range(oidc.MAX_ATTEMPTS + 50):
        attempts.start(_config(idp))
    assert len(attempts._attempts) <= oidc.MAX_ATTEMPTS


# --- the ID token must verify ---


@pytest.mark.parametrize(
    ("override", "reason"),
    [
        ({"aud": "osprey-glass"}, "token_invalid"),  # minted for another client
        ({"aud": "osprey-conduit"}, "token_invalid"),
        ({"iss": "http://evil.example/realms/osprey"}, "token_invalid"),
        ({"exp": int(time.time()) - 60}, "token_invalid"),
        ({"nonce": "somebody-elses"}, "nonce_mismatch"),
        ({"roles": "osprey-admin"}, "roles_claim_malformed"),  # a string is not a list of roles
        ({"roles": [1, 2]}, "roles_claim_malformed"),
    ],
)
def test_a_token_that_does_not_verify_is_refused(
    idp: FakeIdentityProvider, override: dict, reason: str
) -> None:
    idp.claim_overrides = override
    with pytest.raises(SignInRefused) as refused:
        _finish(idp)
    assert refused.value.reason == reason


def test_a_token_signed_with_another_key_is_refused(idp: FakeIdentityProvider) -> None:
    idp.sign_with_other_key = True
    with pytest.raises(SignInRefused) as refused:
        _finish(idp)
    assert refused.value.reason == "token_invalid"


def test_an_unsigned_token_is_refused(idp: FakeIdentityProvider) -> None:
    """The `alg: none` shape. Catches a verifier that accepts whatever algorithm the token names."""
    config, attempts, query = _sign_in(idp)
    attempt = attempts.finish(query["state"])
    now = int(time.time())
    forged = jwt.encode(
        {
            "iss": idp.issuer,
            "aud": CLIENT,
            "sub": "x",
            "nonce": attempt.nonce,
            "iat": now,
            "exp": now + 60,
            "roles": ["osprey-admin"],
        },
        key=None,
        algorithm="none",
    )
    with pytest.raises(SignInRefused):
        oidc.verify_id_token(config, forged, nonce=attempt.nonce)


def test_a_response_with_no_id_token_is_refused(idp: FakeIdentityProvider) -> None:
    idp.omit_id_token = True
    with pytest.raises(SignInRefused) as refused:
        _finish(idp)
    assert refused.value.reason == "no_id_token"


def test_a_token_missing_a_required_claim_is_refused(idp: FakeIdentityProvider) -> None:
    config, attempts, query = _sign_in(idp)
    attempt = attempts.finish(query["state"])
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    bare = jwt.encode({"iss": idp.issuer, "aud": CLIENT}, key, algorithm="RS256")
    with pytest.raises(SignInRefused):
        oidc.verify_id_token(config, bare, nonce=attempt.nonce)


# --- unreachable is not refused ---


def test_a_provider_server_error_is_reported_as_unreachable_not_as_a_refusal(
    idp: FakeIdentityProvider,
) -> None:
    """ADR-044. Catches folding every failure into 'wrong account': the operator would then try
    other accounts when the fix is to start the stack."""
    idp.token_status = 500
    with pytest.raises(IdentityProviderUnreachable):
        _finish(idp)


def test_a_provider_that_says_no_at_the_token_endpoint_is_a_refusal_not_unreachable(
    idp: FakeIdentityProvider,
) -> None:
    idp.token_status = 400
    with pytest.raises(SignInRefused):
        _finish(idp)


def test_a_provider_that_is_not_there_is_unreachable(idp: FakeIdentityProvider) -> None:
    config, attempts, query = _sign_in(idp)
    attempt = attempts.finish(query["state"])
    idp.stop()

    with pytest.raises(IdentityProviderUnreachable):
        oidc.complete(config, code=query["code"], attempt=attempt)
    with pytest.raises(IdentityProviderUnreachable):
        oidc.probe(config)


def test_the_probe_passes_when_the_provider_is_up(idp: FakeIdentityProvider) -> None:
    oidc.probe(_config(idp))


# --- sessions ---


def _identity() -> oidc.Identity:
    return oidc.Identity(subject="s", username="ada", roles=("osprey-admin",))


def test_a_session_is_found_by_its_token_and_not_by_a_guess() -> None:
    store = SessionStore()
    token = store.create(_identity())
    assert store.get(token) == _identity()
    assert store.get(token + "x") is None
    assert store.get("") is None
    assert store.get(None) is None


def test_a_session_expires_at_its_absolute_time_however_often_it_is_used() -> None:
    now = [0.0]
    store = SessionStore(ttl_seconds=100.0, clock=lambda: now[0])
    token = store.create(_identity())
    now[0] = 99.0
    assert store.get(token) is not None
    now[0] = 100.0
    assert store.get(token) is None, "use must not extend the session"


def test_destroying_a_session_ends_it() -> None:
    store = SessionStore()
    token = store.create(_identity())
    store.destroy(token)
    assert store.get(token) is None


def test_sessions_are_bounded_and_the_newest_survive() -> None:
    now = [0.0]
    store = SessionStore(clock=lambda: now[0])
    tokens = []
    for _ in range(oidc.MAX_SESSIONS + 10):
        now[0] += 1
        tokens.append(store.create(_identity()))
    assert store.get(tokens[-1]) is not None
    assert store.get(tokens[0]) is None
    assert len(store._sessions) <= oidc.MAX_SESSIONS


def test_the_logout_address_names_the_client_and_the_registered_return_address(
    idp: FakeIdentityProvider,
) -> None:
    """Keycloak 26 refuses a logout with neither `client_id` nor a token hint; without this the
    person would 'sign out' and be silently signed straight back in by the provider's own cookie."""
    parsed = urllib.parse.urlparse(_config(idp).logout_url)
    query = urllib.parse.parse_qs(parsed.query)
    assert parsed.path.endswith("/protocol/openid-connect/logout")
    assert query["client_id"] == [CLIENT]
    assert query["post_logout_redirect_uri"] == ["http://localhost:7000/"]
