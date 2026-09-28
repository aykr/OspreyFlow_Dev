"""Mints a bearer token and a JWKS fixture for a local, non-pytest Conduit —
the concrete mechanism that makes `DEMO_GUIDE.md` §3 (bringing up a demo
environment) runnable by someone who is not running the test suite.

**DEV-ONLY. Never present in any deployment image, by construction, not by
convention.** `services/api/Dockerfile` and `services/ingest/Dockerfile` —
the only two Dockerfiles in this repository — `COPY` only `packages/` and
`services/`; neither touches `scripts/`, and this module imports nothing
from `packages/`, so there is no dependency edge by which building an image
today, or carelessly tomorrow, could pull this file or its logic in. If a
future service genuinely needs something this module does, that need is
itself the signal to move the shared piece into `packages/` deliberately —
not a reason to reach for this one. `trivy image` will not catch a
violation of this if one is ever introduced: shipping the capability to
mint a token for any clearance level is not a vulnerability with a CVE, it
is a capability, and the containment argument here is structural (never
copied in) and procedural (never given a path in), not tooling-detected.

**Why this is safe even if the file itself leaked onto a real host.** A
token this script mints is only dangerous against a Conduit whose own
`OIDC_JWKS_URL` has been pointed at *this script's own, freshly generated,
ephemeral* keypair. A correctly configured deployment points that variable
at a real IdP's JWKS endpoint (Keycloak, `03_CONDUIT_MIDDLEWARE.md`);
against that, this script's tokens are cryptographically meaningless
regardless of what claims they carry. Misuse needs two deliberate steps —
get this script onto a host, *and* repoint a real deployment's trust root
at its output — not one accident. The runtime banner below exists so
nobody mistakes this output for something safe to paste into a real
system; it is not a technical lock, because no such lock survives a
determined operator with the source in front of them.

**Reuses `tests/conftest.py`'s own signing logic rather than re-deriving
it** (`sign_token`, `default_claims`) — the same "a script now wraps what
started as a pytest-only helper" correction already made for `revert_load`
(Phase 2), the local-basemap build (Checkpoint 1) and `seed_hmp_fixture`
(Phase 5), which already sets the precedent of a `scripts/` module
importing directly from `tests/` rather than duplicating a fixture. The
keypair-generation and JWKS-writing logic below is not reused the same way
— `tests/conftest.py`'s own `keypair`/`jwks_dir` fixtures are
`@pytest.fixture`-shaped, not plain callables — so it is written fresh
here.

**Write, don't serve.** `PyJWKClient` (the OIDC client `services/api/
auth.py` uses) rejects any URI scheme but `http`/`https` — a bare
`file://` JWKS is not a supported scheme (`services/api/config.py`'s own
`OIDC_JWKS_URL` docstring already says so). This script writes the public
JWKS to `--jwks-path` and prints the one-line command to serve that
directory (`python3 -m http.server`) rather than becoming a server itself
— the same "do one job, print the result, exit" shape `seed_hmp_fixture.py`
already uses; a script that served forever would be a different kind of
tool than the three corrections this one continues.

**The keypair is reused across invocations, not regenerated every time.**
If `--jwks-path`'s own private-key sidecar file already exists, this run
signs against it instead of generating a fresh one — so a second
invocation with different claims (a different clearance, say) mints a
second, independently useful token without invalidating a JWKS a Conduit
is already trusting mid-session. Delete the sidecar file to force a fresh
keypair.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm
from tests.conftest import DEFAULT_KID, default_claims, sign_token

_BANNER = """\
================================================================================
 DEV-ONLY TOKEN MINTER
 This mints a bearer token for ANY clearance and org-unit you ask for,
 signed by a throwaway key this script just generated (or already holds).
 It is only dangerous if a real deployment's OIDC_JWKS_URL is pointed at
 this script's own output. Never do that, and never copy this script onto
 a deployed host. See this file's own module docstring for the full
 containment argument.
================================================================================
"""


def _private_key_path(jwks_path: Path) -> Path:
    return jwks_path.with_suffix(jwks_path.suffix + ".private_key.pem")


def _load_or_generate_private_key(path: Path) -> rsa.RSAPrivateKey:
    if path.exists():
        return serialization.load_pem_private_key(path.read_bytes(), password=None)
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    path.write_bytes(
        private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    path.chmod(0o600)
    return private_key


def _write_jwks(jwks_path: Path, private_key: rsa.RSAPrivateKey) -> None:
    jwk = RSAAlgorithm.to_jwk(private_key.public_key(), as_dict=True)
    jwk["kid"] = DEFAULT_KID
    jwk["use"] = "sig"
    jwk["alg"] = "RS256"
    jwks_path.parent.mkdir(parents=True, exist_ok=True)
    jwks_path.write_text(json.dumps({"keys": [jwk]}, indent=2))


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.mint_dev_token",
        description=(
            "Mints a signed bearer token and writes a matching JWKS file, for starting a "
            "local Conduit/Glass session outside pytest. DEV-ONLY — see this file's own "
            "module docstring before using it against anything but a local, throwaway setup."
        ),
    )
    parser.add_argument(
        "--jwks-path", required=True, help="Where to write the public JWKS document."
    )
    parser.add_argument("--sub", default="analyst-1")
    parser.add_argument("--clearance", default="OFFICIAL")
    parser.add_argument("--org-unit", default="unit-1")
    parser.add_argument(
        "--receivable-handling-codes",
        default="",
        help="Comma-separated; empty by default, matching default_claims.",
    )
    parser.add_argument("--roles", default="analyst", help="Comma-separated.")
    parser.add_argument(
        "--ttl-hours",
        type=float,
        default=8.0,
        help=(
            "5 minutes (tests/conftest.py's own default_claims) is right for an assertion "
            "that runs in milliseconds and useless for a person working a session — 8 hours "
            "is a full working day, not a security boundary this script is trying to hold."
        ),
    )
    return parser.parse_args(argv)


def _run(args: argparse.Namespace) -> int:
    sys.stderr.write(_BANNER)

    jwks_path = Path(args.jwks_path)
    private_key = _load_or_generate_private_key(_private_key_path(jwks_path))
    _write_jwks(jwks_path, private_key)

    handling_codes = [c for c in args.receivable_handling_codes.split(",") if c]
    roles = [r for r in args.roles.split(",") if r]
    now = int(time.time())
    claims = default_claims(
        sub=args.sub,
        clearance=args.clearance,
        org_unit=args.org_unit,
        receivable_handling_codes=handling_codes,
        roles=roles,
        iat=now,
        exp=now + int(args.ttl_hours * 3600),
    )
    token = sign_token(private_key, claims)

    jwks_dir = jwks_path.parent if str(jwks_path.parent) else Path(".")
    print(f"JWKS written to {jwks_path}")
    print(f"Serve it with: python3 -m http.server 8888 --directory {jwks_dir}")
    print(f"Then: OIDC_JWKS_URL=http://localhost:8888/{jwks_path.name}")
    print()
    print(f"Token (claims: {claims}):")
    print(token)
    return 0


def main(argv: list[str] | None = None) -> int:
    return _run(_parse_args(argv if argv is not None else sys.argv[1:]))


if __name__ == "__main__":
    raise SystemExit(main())
