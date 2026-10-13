"""The first administrator of a cloud deployment, with a one-time code (ADR-114 Amendment 10
point 4).

A Lite install signs its owner in with demo accounts whose passwords are in `deployment.env`. A
Small server has no demo accounts: its first administrator is made here, as B4's invitations make
people — no password of their own, a temporary one-time code, and the update-password step at their
first sign-in. The code is printed on stdout and nowhere else: the server's first boot puts it in
the cloud's secret store, from which `ospreyflow install --mode small --cloud …` shows it once and
deletes it. It is made with Keycloak's own admin tool inside its container (`KCADM_CREATE`).

**Clearance:** the scheme's highest *(mine)*. An administrator cannot give anyone a clearance above
their own (B4's ceiling), so a first administrator below the top would cap every account the
deployment ever has.

    python -m harness.first_admin --deployment deploy/generated/small --code-file /run/…/code
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from harness.realm import ADMIN_ROLE
from ontology.handling import HandlingScheme, load_uk_le_scheme

#: The same letters and shape as an invitation's code (`services.api.identity_admin`): no 0/O or
#: 1/I, sixteen letters in four groups, 80 bits.
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def one_time_code() -> str:
    letters = "".join(secrets.choice(CODE_ALPHABET) for _ in range(16))
    return "-".join(letters[i : i + 4] for i in range(0, 16, 4))


def first_administrator(
    username: str, *, code: str, scheme: HandlingScheme, email: str | None = None
) -> dict[str, Any]:
    user: dict[str, Any] = {
        "username": username,
        "enabled": True,
        "emailVerified": False,
        "attributes": {
            "clearance": [scheme.classification[-1]],
            "org_unit": ["administration"],
            "receivable_handling_codes": list(scheme.handling_codes),
            "roles": [ADMIN_ROLE],
        },
        "requiredActions": ["UPDATE_PASSWORD"],
        "credentials": [{"type": "password", "value": code, "temporary": True}],
    }
    if email:
        user["email"] = email
    return user


class FirstAdministratorRefused(RuntimeError):
    """The account was not made; the message says why."""


#: Run inside the Keycloak container, which carries its own admin tool and its bootstrap admin's
#: credentials in its environment — so nothing here needs Keycloak's port, which the deployment
#: never publishes. The account arrives as `OSPREY_FIRST_ADMIN` (JSON), never on a command line.
#: `kcadm.sh` refuses an existing username ("Conflict detected"): the account is never replaced,
#: since that would sign its holder out.
KCADM_CREATE = (
    "/opt/keycloak/bin/kcadm.sh config credentials --server http://localhost:8080 "
    '--realm master --user "$KC_BOOTSTRAP_ADMIN_USERNAME" '
    '--password "$KC_BOOTSTRAP_ADMIN_PASSWORD" --config /tmp/kcadm.config >/dev/null '
    '&& printf %s "$OSPREY_FIRST_ADMIN" | /opt/keycloak/bin/kcadm.sh create users '
    '-r "$OSPREY_REALM" -f - --config /tmp/kcadm.config'
)


def create_first_administrator(
    container_exec: Sequence[str],
    *,
    keycloak: str = "keycloak",
    realm: str = "osprey",
    username: str = "admin",
    email: str | None = None,
) -> str:
    """Makes the account and returns its one-time code; refuses, in words, if it was not made."""
    code = one_time_code()
    user = first_administrator(username, code=code, scheme=load_uk_le_scheme(), email=email)
    argv = [*container_exec, "-e", "OSPREY_FIRST_ADMIN", "-e", "OSPREY_REALM", keycloak,
            "sh", "-c", KCADM_CREATE]  # fmt: skip
    env = {**os.environ, "OSPREY_FIRST_ADMIN": json.dumps(user), "OSPREY_REALM": realm}
    done = subprocess.run(argv, env=env, capture_output=True, text=True, check=False)  # noqa: S603
    if done.returncode != 0:
        said = (done.stderr or done.stdout).strip().splitlines()
        why = said[-1] if said else f"exit {done.returncode}"
        if "Conflict" in why or "exists" in why:
            why = f"{username!r} already exists in the realm; it was not changed"
        raise FirstAdministratorRefused(f"the first administrator was not made: {why}")
    return code


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="harness.first_admin", description=__doc__)
    parser.add_argument("--deployment", type=Path, required=True, help="the deployment folder")
    parser.add_argument("--username", default="admin")
    parser.add_argument("--email")
    parser.add_argument(
        "--code-file", type=Path,
        help="write the code here (mode 600) for the first boot to hand to the secret store; "
        "without it the code is printed, once",
    )  # fmt: skip
    args = parser.parse_args(argv)
    compose = ["docker", "compose", "--env-file", str(args.deployment / "deployment.env"),
               "-f", str(args.deployment / "compose.yaml"), "exec", "-T"]  # fmt: skip
    try:
        code = create_first_administrator(compose, username=args.username, email=args.email)
    except FirstAdministratorRefused as refused:
        print(str(refused), file=sys.stderr)
        return 1
    if args.code_file is None:
        print(f"The first administrator is {args.username}. Their one-time code: {code}")
        print("They choose their own password at their first sign-in; the code is not kept.")
        return 0
    descriptor = os.open(args.code_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as file:
        file.write(code)
    print(f"The first administrator is {args.username}; their one-time code is in {args.code_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
