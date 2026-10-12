"""Keycloak in production mode, its data in the deployment's Postgres (`06_DECISIONS.md` ADR-114
decision 12, Amendment 5 / stage B4a): an account survives a restart.

Measured first against Keycloak 26.0.8 and Postgres 16.4 (12 October 2026): `start` on plain HTTP with
`KC_HOSTNAME` imports the realm once ("already exists. Import skipped" afterwards), keeps a user
created later across a recreated container, and keeps the bootstrap admin of its first start — a
recreated container's new bootstrap password is refused (401).

What a mistake would do, and the case that catches it:
- Keycloak left in `start-dev` or on its built-in database, so a restart loses every account —
  `test_keycloak_runs_in_production_on_its_own_database`;
- Keycloak starting before its database and role exist — `test_its_database_is_made_before_keycloak_starts`;
- the database made once with a password that later drifts from the env file —
  `test_the_database_step_is_idempotent_and_keeps_the_password_in_step`;
- a secret the compose file requires that `apply` never writes (Keycloak's database password, or any
  other) — `test_every_secret_the_compose_file_requires_is_minted_by_apply`;
- the backup dumping Keycloak's database beside the identity item, so a restore loads people twice —
  `test_the_backup_leaves_keycloaks_database_to_the_identity_item`.
"""

from __future__ import annotations

import re
from typing import Any

import yaml
from harness import backup
from harness.render import render
from tools.layout import CORE

from schemas.deployment import OspreyConfig


def _services() -> dict[str, Any]:
    config = OspreyConfig.model_validate({"reporting": {"sync": True, "superset": True}})
    compose = render(config, resolver=lambda _image: "sha256:" + "0" * 64).artefacts["compose.yaml"]
    return yaml.safe_load(compose)["services"]


def test_keycloak_runs_in_production_on_its_own_database() -> None:
    keycloak = _services()["keycloak"]
    assert keycloak["command"][0] == "start" and "start-dev" not in keycloak["command"]
    assert "--import-realm" in keycloak["command"]
    assert "--features=token-exchange" in keycloak["command"]
    env = keycloak["environment"]
    assert env["KC_DB"] == "postgres"
    assert env["KC_DB_URL"] == "jdbc:postgresql://postgres:5432/keycloak"
    assert env["KC_DB_USERNAME"] == "keycloak"
    assert env["KC_DB_PASSWORD"].startswith("${OSPREY_KEYCLOAK_DB_PASSWORD:?")
    assert env["KC_HTTP_ENABLED"] == "true"


def test_its_database_is_made_before_keycloak_starts() -> None:
    services = _services()
    assert services["keycloak"]["depends_on"]["keycloak-db"] == {
        "condition": "service_completed_successfully"
    }
    step = services["keycloak-db"]
    assert step["image"] == services["postgres"]["image"], "the deployment's own Postgres client"
    assert step["restart"] == "no"
    assert step["depends_on"] == {"postgres": {"condition": "service_healthy"}}
    assert "ports" not in step


def test_the_database_step_is_idempotent_and_keeps_the_password_in_step() -> None:
    script = " ".join(_services()["keycloak-db"]["command"])
    assert "IF NOT EXISTS" in script or "NOT EXISTS" in script
    assert "ALTER ROLE keycloak" in script, "a password changed in the env file reaches the role"
    assert "CREATE DATABASE keycloak OWNER keycloak" in script
    assert "OSPREY_KEYCLOAK_DB_PASSWORD" in script and "kcpw" not in script


def test_every_secret_the_compose_file_requires_is_minted_by_apply() -> None:
    compose = yaml.safe_dump(_services())
    required = set(re.findall(r"\$\{([A-Z_]+):\?", compose))
    minted = set(
        re.findall(r'f"([A-Z_]+)=\{', (CORE / "harness" / "apply.py").read_text(encoding="utf-8"))
    )
    assert "OSPREY_KEYCLOAK_DB_PASSWORD" in required
    assert required <= minted, required - minted


def test_the_backup_leaves_keycloaks_database_to_the_identity_item() -> None:
    assert backup.KEYCLOAK_DATABASE == "keycloak"
    assert backup.databases_to_dump(["ospreyflow", "keycloak", "superset"]) == [
        "ospreyflow",
        "superset",
    ]
