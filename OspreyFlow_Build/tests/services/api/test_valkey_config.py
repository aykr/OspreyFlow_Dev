"""A cloud's managed Valkey is reached with its password and over TLS — `spec/05_DEPLOYMENT.md` §3b
(`external.valkey`: ElastiCache, Azure Cache for Redis), ADR-114 Amendment 12.

The Conduit and the worker open Valkey from one place (`ValkeyConfig.client_kwargs`), so neither can
leave out what the other sends. The handshake itself was proved against a password-and-TLS Valkey
8.0 in a container; these cases pin what is asked for.
"""

from __future__ import annotations

import pytest
from services.api.config import ValkeyConfig


def test_the_deployments_own_valkey_is_reached_plainly(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("VALKEY_PASSWORD", "VALKEY_TLS"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("VALKEY_HOST", "valkey")
    assert ValkeyConfig.from_env().client_kwargs() == {"host": "valkey", "port": 6379, "db": 0}


def test_a_managed_valkey_is_reached_with_its_password_over_tls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VALKEY_HOST", "cache.example.internal")
    monkeypatch.setenv("VALKEY_PORT", "6380")
    monkeypatch.setenv("VALKEY_PASSWORD", "from-the-secret")
    monkeypatch.setenv("VALKEY_TLS", "true")
    assert ValkeyConfig.from_env().client_kwargs() == {
        "host": "cache.example.internal",
        "port": 6380,
        "db": 0,
        "password": "from-the-secret",
        "ssl": True,
    }


def test_the_password_is_never_in_the_settings_text(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VALKEY_PASSWORD", "from-the-secret")
    assert "from-the-secret" not in repr(ValkeyConfig.from_env())
