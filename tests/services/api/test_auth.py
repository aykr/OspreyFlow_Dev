"""`PrincipalResolver` — `docs/03_CONDUIT_MIDDLEWARE.md` §6's OIDC-to-
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
from services.api.auth import PrincipalResolutionError, PrincipalResolver
from services.api.config import ApiConfig, PostgresConfig, ValkeyConfig

from tests.conftest import DEFAULT_KID, default_claims, sign_token


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
        supersede_job_degree_threshold=500,
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
