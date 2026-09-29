"""`PrincipalResolver` — `spec/03_CONDUIT_MIDDLEWARE.md` §6's OIDC-to-
`Principal` resolution, exercised end to end against a real RS256 keypair
and a real JWKS document, with no live IdP.

**`OIDC_JWKS_URL` is http(s), not `file://`, even for this fixture.**
`PyJWKClient` (this codebase's OIDC client — `services/api/auth.py`)
deliberately rejects any URI scheme but `http`/`https`, precisely so a
`jku` header or misconfigured URL can never be turned into a local file
read; that guard would be pointless if this project's own tests routed
around it with a scheme it refuses in production. So the JWKS fixture
(`tests/conftest.py`) is a real (loopback, ephemeral-port) HTTP server,
and the exact same code path this test exercises is the one a real
Keycloak realm's JWKS endpoint exercises later — the point of the "JWKS
source is a config point" requirement in the first place.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm
from services.api.auth import (
    PrincipalExchangeRefused,
    PrincipalExchangeUnavailable,
    PrincipalResolutionError,
    PrincipalResolver,
)
from services.api.config import ApiConfig, PostgresConfig, ValkeyConfig

from tests.conftest import (
    DEFAULT_KID,
    TOKEN_EXCHANGE_CLIENT_ID,
    TOKEN_EXCHANGE_CLIENT_SECRET,
    TokenExchangeRegistry,
    default_claims,
    sign_token,
)


def _config(jwks_url: str, **overrides: object) -> ApiConfig:
    defaults: dict[str, object] = dict(
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
    defaults.update(overrides)
    return ApiConfig(**defaults)  # type: ignore[arg-type]


def test_a_validly_signed_token_resolves_to_the_expected_principal(
    keypair: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey], jwks_url: str
) -> None:
    private_key, _ = keypair
    resolver = PrincipalResolver(_config(jwks_url))
    token = sign_token(private_key, default_claims(receivable_handling_codes=["R"]))

    principal = resolver.resolve(token)

    assert principal.id == "analyst-1"
    assert principal.clearance == "OFFICIAL"
    assert principal.org_unit == "unit-1"
    assert principal.receivable_handling_codes == ["R"]
    assert principal.roles == ["analyst"]


def test_a_token_signed_by_a_different_key_is_rejected(jwks_url: str) -> None:
    other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    resolver = PrincipalResolver(_config(jwks_url))
    # Signed with a key whose public half was never published to the JWKS
    # under this `kid` — `get_signing_key_from_jwt` still finds `kid` (it
    # matches by id, not by whether the signature verifies), so this
    # exercises signature verification itself, not key lookup.
    token = sign_token(other_key, default_claims())

    with pytest.raises(PrincipalResolutionError):
        resolver.resolve(token)


def test_an_expired_token_is_rejected(
    keypair: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey], jwks_url: str
) -> None:
    private_key, _ = keypair
    resolver = PrincipalResolver(_config(jwks_url))
    token = sign_token(
        private_key,
        default_claims(iat=int(time.time()) - 3600, exp=int(time.time()) - 1800),
    )

    with pytest.raises(PrincipalResolutionError):
        resolver.resolve(token)


def test_a_token_missing_the_clearance_claim_is_rejected_not_defaulted(
    keypair: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey], jwks_url: str
) -> None:
    """`01_DOMAIN_MODEL.md` §2.2's default-deny already makes a missing
    clearance claim harmless if defaulted — but a silent "sees nothing"
    principal is a worse failure to debug than an explicit 401, so the
    resolver raises instead of defaulting."""
    private_key, _ = keypair
    resolver = PrincipalResolver(_config(jwks_url))
    claims = default_claims()
    del claims["clearance"]
    token = sign_token(private_key, claims)

    with pytest.raises(PrincipalResolutionError):
        resolver.resolve(token)


def test_an_unknown_kid_triggers_a_jwks_refresh_and_then_succeeds(
    jwks_dir: tuple[Path, str], keypair: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]
) -> None:
    """Key rotation: a token signed with a key not yet in the cached JWKS
    (because it rotated in *after* the resolver's last fetch) must still
    resolve, via `PyJWKClient`'s built-in refresh-on-unknown-kid — proving
    the resolver doesn't cache the JWKS forever or require a restart on
    rotation."""
    directory, url = jwks_dir
    old_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    old_jwk = RSAAlgorithm.to_jwk(old_key.public_key(), as_dict=True)
    old_jwk.update(kid="old-key", use="sig", alg="RS256")
    jwks_path = directory / "jwks.json"
    jwks_path.write_text(json.dumps({"keys": [old_jwk]}))

    resolver = PrincipalResolver(_config(url))
    # `PyJWKClient`'s unknown-kid refresh has its own cooldown — a real,
    # deliberate rate limit against a client hammering the endpoint with
    # bad `kid`s — separate from this test's concern (that the refresh
    # mechanism itself works). Disabling it here is a test-only knob, not
    # a change to what `PrincipalResolver` configures in production.
    resolver._jwk_client.cooldown_duration = 0
    # Prime the resolver's cache against the JWKS as it stood before rotation.
    resolver.resolve(sign_token(old_key, default_claims(), kid="old-key"))

    # Rotate: a new key appears under a new `kid`, the old one remains.
    new_key, _ = keypair
    new_jwk = RSAAlgorithm.to_jwk(new_key.public_key(), as_dict=True)
    new_jwk.update(kid=DEFAULT_KID, use="sig", alg="RS256")
    jwks_path.write_text(json.dumps({"keys": [old_jwk, new_jwk]}))

    principal = resolver.resolve(sign_token(new_key, default_claims(), kid=DEFAULT_KID))

    assert principal.id == "analyst-1"


# --- audience verification (06_DECISIONS.md ADR-050 objection 1) -------------------------------


def test_a_token_signed_for_a_different_client_is_refused_not_accepted(
    keypair: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey], jwks_url: str
) -> None:
    """ADR-050 objection 1: a public client (the Glass) makes it reachable from a browser for a
    token minted for an unrelated application in the same realm to be accepted as a principal, if
    the Conduit does not verify audience. `harness/render.py` now writes `OIDC_AUDIENCE` into every
    rendered deployment's environment (`harness/preflight/oidc_audience.py` gates its presence) —
    this is the Conduit-side half of that guarantee: once configured, a token whose `aud` names
    something else is refused, not resolved to a `Principal` anyway.

    Rule 15: removing the conditional in `PrincipalResolver.resolve` (hardcoding `verify_aud` to
    `False`) makes this test fail — verified directly while writing it, then reverted.
    """
    private_key, _ = keypair
    resolver = PrincipalResolver(_config(jwks_url, oidc_audience="osprey-conduit"))
    token = sign_token(private_key, default_claims(aud="some-other-client"))

    with pytest.raises(PrincipalResolutionError):
        resolver.resolve(token)


def test_a_token_signed_for_the_configured_audience_still_resolves(
    keypair: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey], jwks_url: str
) -> None:
    """The positive case beside the refusal above — a configured audience must not become a second
    way to reject every real sign-in."""
    private_key, _ = keypair
    resolver = PrincipalResolver(_config(jwks_url, oidc_audience="osprey-conduit"))
    token = sign_token(private_key, default_claims(aud="osprey-conduit"))

    principal = resolver.resolve(token)

    assert principal.id == "analyst-1"


# --- resolve_for_owner / resolve_for_owner_detailed (06_DECISIONS.md ADR-043) -------------------


def _config_with_exchange(jwks_url: str, token_exchange_url: str, **overrides: object) -> ApiConfig:
    return _config(
        jwks_url,
        oidc_token_exchange_url=token_exchange_url,
        oidc_token_exchange_client_id=TOKEN_EXCHANGE_CLIENT_ID,
        oidc_token_exchange_client_secret=TOKEN_EXCHANGE_CLIENT_SECRET,
        **overrides,
    )


async def test_principal_for_owner_returns_exactly_that_owners_own_claims_not_a_broader_principal(
    keypair: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey],
    jwks_url: str,
    token_exchange_url: str,
    token_exchange_registry: TokenExchangeRegistry,
) -> None:
    """The containment test — this phase's own named exit requirement,
    mirroring `tests/services/api/test_evaluation.py::
    test_a_monitor_never_evaluates_with_a_principal_broader_than_its_owner`'s own reasoning: an
    outcome assertion cannot catch a broader-principal bug, only inspecting the actual returned
    object can. Two real principals, A (narrow) and B (broad) — resolving A must return exactly
    A's own claims, never B's, checked against A's independently-minted ground truth (a token
    signed for A directly, run through `resolve()` on its own, never through the exchange path
    under test) rather than trusting the exchange to prove itself correct."""
    private_key, _ = keypair
    principal_a_claims = default_claims(
        sub="analyst-narrow", clearance="OFFICIAL", org_unit="unit-1", roles=["analyst"]
    )
    principal_b_claims = default_claims(
        sub="analyst-broad", clearance="TOP_SECRET", org_unit="unit-9", roles=["admin"]
    )
    token_exchange_registry.register("analyst-narrow", principal_a_claims)
    token_exchange_registry.register("analyst-broad", principal_b_claims)

    resolver = PrincipalResolver(_config_with_exchange(jwks_url, token_exchange_url))
    ground_truth = resolver.resolve(sign_token(private_key, principal_a_claims))

    resolved = await resolver.resolve_for_owner("analyst-narrow")

    assert resolved is not None
    assert resolved.id == ground_truth.id == "analyst-narrow"
    assert resolved.clearance == ground_truth.clearance == "OFFICIAL"
    assert resolved.org_unit == ground_truth.org_unit == "unit-1"
    assert resolved.roles == ground_truth.roles == ["analyst"]
    # The actual containment claim: resolving A never returns B's own broader fields.
    assert resolved.clearance != principal_b_claims["clearance"]
    assert resolved.org_unit != principal_b_claims["org_unit"]
    assert resolved.roles != principal_b_claims["roles"]


async def test_a_revoked_principal_is_refused_not_treated_as_unreachable(
    keypair: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey],
    jwks_url: str,
    token_exchange_url: str,
    token_exchange_registry: TokenExchangeRegistry,
) -> None:
    """`06_DECISIONS.md` ADR-044's own still-undecided question is whether a *caller* should treat
    refusal and unreachability differently — this test only pins that the distinction exists at
    this layer, via the two named exception types, regardless of what a future caller does with
    it."""
    token_exchange_registry.register("analyst-narrow", default_claims(sub="analyst-narrow"))
    resolver = PrincipalResolver(_config_with_exchange(jwks_url, token_exchange_url))
    await resolver.resolve_for_owner_detailed("analyst-narrow")  # sanity: registered, succeeds

    token_exchange_registry.disable("analyst-narrow")

    with pytest.raises(PrincipalExchangeRefused):
        await resolver.resolve_for_owner_detailed("analyst-narrow")
    # The collapsed, caller-facing form used by every real producer today.
    assert await resolver.resolve_for_owner("analyst-narrow") is None


async def test_an_unreachable_token_exchange_endpoint_is_unavailable_not_refused(
    jwks_url: str,
) -> None:
    resolver = PrincipalResolver(
        _config_with_exchange(jwks_url, "http://127.0.0.1:1/token-exchange")
    )

    with pytest.raises(PrincipalExchangeUnavailable):
        await resolver.resolve_for_owner_detailed("analyst-narrow")
    assert await resolver.resolve_for_owner("analyst-narrow") is None


async def test_an_unconfigured_deployment_is_unavailable_not_refused(jwks_url: str) -> None:
    """`oidc_token_exchange_url` unset (`None`, the default) — `06_DECISIONS.md` ADR-043's own
    "narrower-but-honest" default for a deployment that has not configured exchange at all."""
    resolver = PrincipalResolver(_config(jwks_url))

    with pytest.raises(PrincipalExchangeUnavailable):
        await resolver.resolve_for_owner_detailed("analyst-narrow")
    assert await resolver.resolve_for_owner("analyst-narrow") is None
