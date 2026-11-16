"""The report sync opens Valkey with the deployment's own settings: its password and TLS as well as
its address (v0.6.0's package test, 16 November 2026).

`services.report_sync.__main__.run` built its client as `Valkey(host=, port=, db=)`, dropping the
password (`VALKEY_PASSWORD`) and TLS (`VALKEY_TLS`) that `ValkeyConfig` carries and that the Conduit
and the worker open Valkey with (`ValkeyConfig.client_kwargs()`). On cloud-platform, where Valkey is
ElastiCache over TLS with a password, the report sync could not reach it: with no dashboard it never
asks Valkey anything, so it stayed ready; the first dashboard registered made its first claim
(`sync.py`'s `valkey.set`) fail with "Connection reset by peer", and it restarted in a loop.

What a mistake would do, and the case that catches it (rule 12):
- the report sync's client without the password or without TLS:
  `test_the_report_sync_opens_valkey_with_its_password_and_tls`, which runs the real `run()` and
  reads the client it really built (no stand-in Valkey: a real client connects only when asked
  something, so building one opens nothing);
- another hand-built client dropping them, in services, the harness or an operational script:
  `test_every_hand_built_valkey_client_takes_the_whole_settings`.

A real Valkey refusing a client without TLS or its password is v0.6.1's (CARRIES)."""

from __future__ import annotations

import ast
import asyncio
from pathlib import Path
from typing import Any

import pytest
import services.report_sync.__main__ as report_sync

CORE = Path(__file__).parents[4] / "OspreyFlow_Core"


class _Stop(Exception):
    pass


class _Mart:
    async def ensure_reader(self, reader: str, password: str) -> None:
        return None

    async def close(self) -> None:
        return None


def _client_run_builds(monkeypatch: pytest.MonkeyPatch, env: dict[str, str]) -> Any:
    """The Valkey client `run()` hands its first pass, from the environment given."""
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    for name in {"VALKEY_PASSWORD", "VALKEY_TLS"} - set(env):
        monkeypatch.delenv(name, raising=False)
    built: list[Any] = []

    async def connect(dsn: str, **_: Any) -> _Mart:
        return _Mart()

    async def first_pass(boards: Any, mart: Any, valkey: Any, *, slot: int) -> Any:
        built.append(valkey)
        raise _Stop

    monkeypatch.setattr(report_sync.Mart, "connect", connect)
    monkeypatch.setattr(report_sync, "sync_once", first_pass)
    settings = {"REPORT_SYNC_TOKEN_URL": "https://login.example.invalid/token",
                "REPORT_SYNC_CONDUIT_URL": "http://api:8000"}  # fmt: skip
    with pytest.raises(_Stop):
        asyncio.run(report_sync.run(settings))
    [client] = built
    return client


def test_the_report_sync_opens_valkey_with_its_password_and_tls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _client_run_builds(monkeypatch, {
        "VALKEY_HOST": "master.standin.cache.amazonaws.com", "VALKEY_PORT": "6379",
        "VALKEY_PASSWORD": "standin-auth-token", "VALKEY_TLS": "true",
    })  # fmt: skip
    pool = client.connection_pool
    assert pool.connection_kwargs.get("host") == "master.standin.cache.amazonaws.com"
    assert pool.connection_kwargs.get("password") == "standin-auth-token"
    assert pool.connection_class.__name__ == "SSLConnection", pool.connection_class


def test_a_valkey_with_neither_is_opened_plainly(monkeypatch: pytest.MonkeyPatch) -> None:
    """Lite's and Small's own Valkey: no password, no TLS, as before."""
    client = _client_run_builds(monkeypatch, {"VALKEY_HOST": "valkey", "VALKEY_PORT": "6379"})
    pool = client.connection_pool
    assert pool.connection_kwargs.get("password") is None
    assert pool.connection_class.__name__ == "Connection"


def _hand_built(path: Path) -> list[int]:
    """The lines where `path` calls `Valkey(...)` with anything but `**<…>.client_kwargs()`."""
    lines = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if not (isinstance(node, ast.Call) and getattr(node.func, "id", None) == "Valkey"):
            continue
        whole = [k for k in node.keywords if k.arg is None]
        takes_settings = (
            len(whole) == 1 and not node.args and len(node.keywords) == 1
            and isinstance(whole[0].value, ast.Call)
            and getattr(whole[0].value.func, "attr", None) == "client_kwargs"
        )  # fmt: skip
        if not takes_settings:
            lines.append(node.lineno)
    return lines


def test_every_hand_built_valkey_client_takes_the_whole_settings() -> None:
    found = {
        str(path.relative_to(CORE)): lines
        for folder in ("services", "harness", "scripts", "packages", "cli")
        for path in sorted((CORE / folder).rglob("*.py"))
        if (lines := _hand_built(path))
    }
    assert found == {}, f"Valkey opened without its password and TLS: {found}"
