"""The Conduit's Postgres connection for a managed database (`05_DEPLOYMENT.md` §3a).

A password made by Secrets Manager or Key Vault may hold any character, and a managed server
requires TLS. Live against the throwaway Postgres: a login whose password holds every character a
URL gives meaning to connects through `PostgresConfig.dsn`.
"""

from __future__ import annotations

import uuid

import asyncpg
import pytest
from services.api.config import PostgresConfig

AWKWARD = "p@ss/w:rd?#%&+ =ä"


async def test_a_password_with_url_characters_connects() -> None:
    admin = PostgresConfig.from_env()
    role = f"dsn_{uuid.uuid4().hex[:8]}"
    conn = await asyncpg.connect(admin.dsn)
    try:
        await conn.execute(f"CREATE ROLE {role} LOGIN PASSWORD '{AWKWARD}'")
        config = PostgresConfig(
            host=admin.host, port=admin.port, user=role, password=AWKWARD, database=admin.database
        )
        other = await asyncpg.connect(config.dsn)
        assert await other.fetchval("SELECT current_user") == role
        await other.close()
    finally:
        await conn.execute(f"DROP ROLE IF EXISTS {role}")
        await conn.close()


def test_tls_is_asked_for_when_the_deployment_names_it(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("POSTGRES_SSLMODE", "require")
    assert PostgresConfig.from_env().dsn.endswith("?sslmode=require")
    monkeypatch.delenv("POSTGRES_SSLMODE")
    assert "sslmode" not in PostgresConfig.from_env().dsn
