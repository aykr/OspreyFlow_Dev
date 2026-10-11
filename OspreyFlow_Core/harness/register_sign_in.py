"""Add the launcher's sign-in to a Keycloak that is already running.

`06_DECISIONS.md` ADR-051. A realm import runs only when Keycloak first starts against an empty
database, so a deployment applied before the launcher had a sign-in holds a realm with no
`osprey-launcher` or `osprey-harness` client and no `osprey-demo-admin` subject, and re-rendering
`realm.json` changes nothing there. This registers them through the admin API, from the **same
rendered realm** a fresh `apply --demo-analyst` builds (`harness.realm.render_realm`), so a running
deployment cannot drift from a new one.

Safe to run again. An existing client or subject is left alone; the demo admin's password is kept
if `deployment.env` already names one (Keycloak's database is not persisted, so after a restart the
subject is gone while the file still names a password, and running this makes the file true again).
The password is written to `deployment.env` only after Keycloak has accepted it, and is never
printed.

    python -m harness.register_sign_in            # from the repository root, PYTHONPATH=.:packages
"""

from __future__ import annotations

import argparse
from pathlib import Path

from harness import keycloak_admin
from harness.keycloak_admin import RealmConfigurationFailed
from harness.realm import (
    DEMO_ADMIN_SUBJECT,
    DEMO_ANALYST_SUBJECT,
    DEMO_ENGINEER_SUBJECT,
    DEMO_REPORT_VIEWER_SUBJECT,
    HARNESS_CLIENT_ID,
    LAUNCHER_CLIENT_ID,
    LOGIN_THEME_NAME,
    REALM_DISPLAY_NAME,
    SUPERSET_CLIENT_ID,
    WITHDRAWN_DEMO_ROLES,
    generate_client_secret,
    render_realm,
    superset_client,
)
from harness.render import DEFAULT_CONFIG_PATH, DEFAULT_OUT_ROOT, load_config
from schemas.deployment import OspreyConfig

ADMIN_PASSWORD_KEY = "OSPREY_KEYCLOAK_ADMIN_PASSWORD"
DEMO_ANALYST_PASSWORD_KEY = "OSPREY_DEMO_ANALYST_PASSWORD"
DEMO_ADMIN_PASSWORD_KEY = "OSPREY_DEMO_ADMIN_PASSWORD"
#: ADR-113 decision 8: the two personas added beside the analyst and the admin.
DEMO_PERSONA_PASSWORD_KEYS = {
    DEMO_ENGINEER_SUBJECT: "OSPREY_DEMO_ENGINEER_PASSWORD",
    DEMO_REPORT_VIEWER_SUBJECT: "OSPREY_DEMO_REPORT_VIEWER_PASSWORD",
}


def _read_env(env_path: Path) -> dict[str, str]:
    try:
        text = env_path.read_text(encoding="utf-8")
    except OSError as error:
        raise RealmConfigurationFailed(
            f"cannot read {env_path.name} ({error}) — apply the deployment first, or point "
            "--out-root at the folder that holds its deployment.env"
        ) from error
    values: dict[str, str] = {}
    for line in text.splitlines():
        name, _, value = line.partition("=")
        if name and not name.startswith("#"):
            values[name.strip()] = value.strip()
    return values


def _write_env_value(env_path: Path, key: str, value: str) -> None:
    lines = env_path.read_text(encoding="utf-8").splitlines()
    replaced = False
    for index, line in enumerate(lines):
        if line.partition("=")[0].strip() == key:
            lines[index] = f"{key}={value}"
            replaced = True
    if not replaced:
        lines.append(f"{key}={value}")
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def register(*, issuer: str, realm: str, env_path: Path, config: OspreyConfig) -> list[str]:
    """Returns one plain-language line per thing done. Raises `RealmConfigurationFailed` naming
    what Keycloak refused, or that it could not be reached — those are different next steps."""
    values = _read_env(env_path)
    admin_password = values.get(ADMIN_PASSWORD_KEY)
    if not admin_password:
        raise RealmConfigurationFailed(
            f"{env_path.name} has no {ADMIN_PASSWORD_KEY} — it was not written by `apply`"
        )
    try:
        token = keycloak_admin.admin_token(
            issuer=issuer, admin_user="admin", admin_password=admin_password
        )
    except keycloak_admin.AdminLoginRefused as error:
        folder = env_path.parent
        raise RealmConfigurationFailed(
            f"Keycloak refused the administrator password in {env_path.name}. That usually means "
            "the running Keycloak was started from an earlier render of the deployment than the "
            f"one now in {folder.name}/, so the file and Keycloak disagree. To bring them back in "
            f"step, recreate Keycloak from the current file:\n\n"
            f"    docker compose -f {folder}/compose.yaml --env-file {folder}/{env_path.name} "
            "up -d --force-recreate keycloak\n\n"
            "then run this again. Keycloak keeps nothing between recreations, so any account "
            "created after its first start is gone and has to be created again."
        ) from error

    rendered = render_realm(config, realm_name=realm, demo_analyst=True)
    (admin,) = [u for u in rendered["users"] if u["username"] == DEMO_ADMIN_SUBJECT]
    lines: list[str] = []

    keycloak_admin.ensure_unmanaged_attributes(issuer=issuer, realm=realm, token=token)
    lines.append(
        keycloak_admin.ensure_service_account_roles(issuer=issuer, realm=realm, token=token)
    )
    superset_secret = values.get("SUPERSET_OIDC_CLIENT_SECRET")
    if superset_secret:
        # ADR-111 Amendment 2: Superset's sign-in, only when the deployment runs Superset.
        origin = values.get("SUPERSET_PUBLIC_ORIGIN", "http://localhost:8088")
        lines.append(
            f"sign-in client {SUPERSET_CLIENT_ID}: "
            + keycloak_admin.ensure_client(
                issuer=issuer, realm=realm, token=token,
                client={**superset_client(origin), "secret": superset_secret},
            )
        )  # fmt: skip
    for client_id in (LAUNCHER_CLIENT_ID, HARNESS_CLIENT_ID):
        (client,) = [c for c in rendered["clients"] if c["clientId"] == client_id]
        lines.append(
            f"sign-in client {client_id}: "
            + keycloak_admin.ensure_client(issuer=issuer, realm=realm, token=token, client=client)
        )
    lines.append(
        f"account {DEMO_ADMIN_SUBJECT}: "
        + keycloak_admin.ensure_user(issuer=issuer, realm=realm, token=token, user=admin)
    )

    lines.append(
        keycloak_admin.ensure_realm_look(
            issuer=issuer,
            realm=realm,
            token=token,
            theme=LOGIN_THEME_NAME,
            display_name=REALM_DISPLAY_NAME,
        )
    )

    password = values.get(DEMO_ADMIN_PASSWORD_KEY) or generate_client_secret()
    keycloak_admin.set_user_password(
        issuer=issuer,
        realm=realm,
        token=token,
        username=DEMO_ADMIN_SUBJECT,
        password=password,
    )
    _write_env_value(env_path, DEMO_ADMIN_PASSWORD_KEY, password)
    lines.append(f"password for {DEMO_ADMIN_SUBJECT} set; it is in {env_path.name}")

    # The demo analyst's password is set through the admin API once, by `apply`, and Keycloak keeps
    # nothing between restarts, so a restart drops it while the file still names it. Only when the
    # deployment was applied with a demo analyst (the file names a password): none is invented.
    analyst_password = values.get(DEMO_ANALYST_PASSWORD_KEY)
    if analyst_password:
        (analyst,) = [u for u in rendered["users"] if u["username"] == DEMO_ANALYST_SUBJECT]
        lines.append(
            f"account {DEMO_ANALYST_SUBJECT}: "
            + keycloak_admin.ensure_user(issuer=issuer, realm=realm, token=token, user=analyst)
        )
        keycloak_admin.set_user_password(
            issuer=issuer,
            realm=realm,
            token=token,
            username=DEMO_ANALYST_SUBJECT,
            password=analyst_password,
        )
        lines.append(f"password for {DEMO_ANALYST_SUBJECT} set; it is in {env_path.name}")
        # ADR-113 decision 8, on a demonstration deployment only (the analyst's password marks
        # one): the two further personas, each with its own password, made once and kept.
        for username, key in DEMO_PERSONA_PASSWORD_KEYS.items():
            (persona,) = [u for u in rendered["users"] if u["username"] == username]
            lines.append(
                f"account {username}: "
                + keycloak_admin.ensure_user(issuer=issuer, realm=realm, token=token, user=persona)
            )
            persona_password = values.get(key) or generate_client_secret()
            keycloak_admin.set_user_password(
                issuer=issuer,
                realm=realm,
                token=token,
                username=username,
                password=persona_password,
            )
            _write_env_value(env_path, key, persona_password)
            lines.append(f"password for {username} set; it is in {env_path.name}")
    # Roles a ruling took away from a demo account — the one removal registration makes.
    for username, roles in WITHDRAWN_DEMO_ROLES.items():
        lines.append(
            f"account {username}: "
            + keycloak_admin.withdraw_roles(
                issuer=issuer, realm=realm, token=token, username=username, roles=roles
            )
        )
    return lines


def print_summary(lines: list[str], env_path: Path) -> None:
    print("Sign-in registered on the running identity provider:")
    for line in lines:
        print(f"  - {line}")
    print(
        f"\n  Sign in as {DEMO_ADMIN_SUBJECT} for the Admin console. Its password is the value of "
        f"{DEMO_ADMIN_PASSWORD_KEY}\n  in {env_path}. It is not printed here."
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--profile", default="local-lite")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--out-root", type=Path, default=DEFAULT_OUT_ROOT)
    parser.add_argument("--keycloak-url", default="http://127.0.0.1:8081")
    parser.add_argument("--realm", default="osprey")
    args = parser.parse_args(argv)

    env_path = args.out_root / args.profile / "deployment.env"
    try:
        lines = register(
            issuer=args.keycloak_url,
            realm=args.realm,
            env_path=env_path,
            config=load_config(args.config),
        )
    except RealmConfigurationFailed as error:
        print(f"Could not register sign-in: {error}")
        return 1
    print_summary(lines, env_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
