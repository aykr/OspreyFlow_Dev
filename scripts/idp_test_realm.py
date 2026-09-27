"""Stand up a real Keycloak carrying **this repository's own realm**, for the token-exchange tests.

**Why this exists.** `tests/services/api/test_revoked_principal_precheck.py`'s five cases guard
`PrincipalResolver`'s OAuth2 Token Exchange and the revoked-principal precheck. Round 13c found
they had **never run, in any tier**: nothing in the repository set `OSPREY_TEST_KEYCLOAK_URL`, and
the realm they needed lived in a `/tmp/kcsetup.py` that was never in the tree. Owner ruling R8
ordered them made to run. That matters more than the usual coverage argument, because this is the
exact code path `CLAUDE.md` rule 15's second worked example records as having been "built" for two
days while never once working against a real identity provider — the tests written so that could
not recur were themselves never executed.

**It renders the deployment realm, not a test realm.** `harness/realm.py` already emits everything
these tests need, and `harness/keycloak_admin.py` already applies the parts a realm import cannot
carry:

| What the tests need | Where it already comes from |
| --- | --- |
| `osprey-conduit`, impersonation + view-users | `render_realm` declares it;
|                                              | `grant_service_account_roles` grants |
| `osprey-unprivileged`, holding neither | `render_realm` declares it |
| An enabled subject | `render_realm`'s `VERIFY_SUBJECT` |
| A **disabled** subject | `render_realm`'s `REVOKED_SUBJECT`, disabled on purpose |
| Both clients' secrets | `grant_service_account_roles` sets them after import |

Using a purpose-built realm instead would reintroduce precisely the defect ADR-043 shipped with: a
fixture that accepts what the real dependency refuses. The realm under test is the realm a real
`harness.apply` deploys.

**The secret is a fixture value and stays one.** `probe-secret` is written into a throwaway
container that exists for the length of one test run and is never a deployment credential;
`harness.realm.generate_client_secret` remains what mints real ones.

Usage — normally through `make idp-test`, which also runs the tests and tears down:

    python -m scripts.idp_test_realm --write-realm /tmp/kc/realm.json
    # start Keycloak with that realm imported, then:
    python -m scripts.idp_test_realm --configure --issuer http://localhost:8082
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from harness.keycloak_admin import grant_service_account_roles
from harness.realm import render_realm_json

from schemas.deployment import OspreyConfig

#: A throwaway container's credentials, for the length of one test run. See the module docstring.
ADMIN_USER = "admin"
ADMIN_PASSWORD = "admin"
PROBE_SECRET = "probe-secret"
REALM_NAME = "osprey"


def _minimal_config() -> OspreyConfig:
    """The smallest config `render_realm` will accept.

    The realm document does not depend on storage roots, images or ports — only on the clients,
    subjects and mappers the generator hard-codes — so defaults are honest here rather than a
    shortcut. If that ever stops being true, this call fails loudly rather than rendering a realm
    that quietly differs from a deployment's.
    """
    return OspreyConfig()


def write_realm(destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(render_realm_json(_minimal_config(), realm_name=REALM_NAME), "utf-8")
    return destination


def wait_for_keycloak(issuer: str, *, timeout_seconds: float = 180.0) -> None:
    """Block until the realm answers, or fail by name.

    Polls the realm's own OIDC discovery document rather than the container's health endpoint:
    health goes green when the server is up, which is *before* the realm import has finished, and
    configuring a realm that does not exist yet fails with a 404 that reads like a wrong URL.
    """
    deadline = time.monotonic() + timeout_seconds
    url = f"{issuer}/realms/{REALM_NAME}/.well-known/openid-configuration"
    last = ""
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=5) as response:
                if response.status == 200:
                    return
                last = f"status {response.status}"
        except (urllib.error.HTTPError, urllib.error.URLError, OSError) as error:
            last = str(error)
        time.sleep(2)
    raise SystemExit(
        f"Keycloak's {REALM_NAME!r} realm did not become available at {issuer} within "
        f"{timeout_seconds:.0f}s — last: {last}"
    )


def configure(issuer: str) -> None:
    """Apply what a realm import cannot carry — the same call `harness/apply.py` makes."""
    grant_service_account_roles(
        issuer=issuer,
        realm=REALM_NAME,
        admin_user=ADMIN_USER,
        admin_password=ADMIN_PASSWORD,
        client_secret=PROBE_SECRET,
    )


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m scripts.idp_test_realm")
    parser.add_argument("--write-realm", type=Path, help="render the realm document to this path")
    parser.add_argument(
        "--configure", action="store_true", help="apply grants and client secrets after import"
    )
    parser.add_argument(
        "--issuer", default="http://localhost:8082", help="the running Keycloak's base URL"
    )
    parser.add_argument(
        "--print-subjects",
        action="store_true",
        help="print the realm's own subject and client names as JSON",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])

    if args.write_realm:
        print(f"realm written to {write_realm(args.write_realm)}")
    if args.configure:
        wait_for_keycloak(args.issuer)
        configure(args.issuer)
        print(f"configured {args.issuer} — grants applied, client secrets set")
    if args.print_subjects:
        from harness.realm import (
            CONDUIT_CLIENT_ID,
            REVOKED_SUBJECT,
            UNPRIVILEGED_CLIENT_ID,
            VERIFY_SUBJECT,
        )

        print(
            json.dumps(
                {
                    "conduit_client": CONDUIT_CLIENT_ID,
                    "unprivileged_client": UNPRIVILEGED_CLIENT_ID,
                    "enabled_subject": VERIFY_SUBJECT,
                    "disabled_subject": REVOKED_SUBJECT,
                },
                indent=2,
            )
        )
    if not (args.write_realm or args.configure or args.print_subjects):
        raise SystemExit("nothing to do — pass --write-realm, --configure or --print-subjects")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
