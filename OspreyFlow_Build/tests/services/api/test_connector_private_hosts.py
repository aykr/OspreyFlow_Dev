"""An operator admits a client's private database or API to the connectors, by name or network, in
`osprey.yaml` (`06_DECISIONS.md` ADR-140 Amendment 15, the owner's ruling (a) of 9 November 2026).
Everything not listed stays refused as Amendment 13 refuses it, and some addresses no list
can admit: this machine, a link-local address (a cloud's metadata service), an unspecified,
multicast or reserved one, and the deployment's own dotless service names.

The list is `connectors.private_hosts` in `osprey.yaml`, checked by the deployment's schema,
rendered by `apply` as `OSPREY_CONNECTOR_PRIVATE`, and read by `refuse_host` at the real call
site: when an administrator names a connection, and before every connection or request.

What a mistake would do, and the case that catches it:
- a private address admitted with no list, or by an entry naming another host or network —
  `test_an_unlisted_private_address_is_refused`;
- a listed host or network still refused, so the ruling is not built —
  `test_a_listed_private_host_or_network_is_admitted`;
- a list that reaches this machine or the metadata service, by an entry for it or by a listed name
  resolving there — `test_no_list_admits_this_machine_or_the_metadata_service` and
  `test_osprey_yaml_refuses_an_entry_no_list_may_hold`;
- the list never reaching the Conduit — `test_apply_renders_the_list_for_the_conduit`;
- the save route refusing a listed host, or keeping an unlisted one —
  `test_an_administrator_names_a_listed_private_connection_and_not_an_unlisted_one`.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from services.api import connector_reads
from services.api.app import app
from services.api.connector_reads import refuse_connection_hosts, refuse_host
from services.api.sources import InMemorySourceStore
from services.ingest.connectors.reads import ConnectorRefused

from schemas.deployment import ConnectorsConfig, OspreyConfig
from schemas.domain import Principal
from schemas.sources import ApiConnectionSettings, SqlConnectionSettings

ANSWERS: dict[str, list[str]] = {
    "nomis.client.example": ["10.20.30.40"],
    "crm.client.example": ["10.99.0.7"],
    "ula.client.example": ["fd12:3456::7"],
    "shared.client.example": ["100.64.3.2"],
    "loop.client.example": ["127.0.0.1"],
    "meta.client.example": ["169.254.169.254"],
    "telco.example": ["93.184.215.14"],
}


@pytest.fixture(autouse=True)
def dns(monkeypatch: pytest.MonkeyPatch) -> dict[str, list[str]]:
    """What each name resolves to, by the test: no lookup leaves the machine."""
    monkeypatch.setattr(connector_reads, "resolve_host", lambda host: ANSWERS.get(host, []))
    monkeypatch.delenv("OSPREY_CONNECTOR_PRIVATE", raising=False)
    return ANSWERS


def _listed(monkeypatch: pytest.MonkeyPatch, *entries: str) -> None:
    monkeypatch.setenv("OSPREY_CONNECTOR_PRIVATE", ",".join(entries))


@pytest.mark.parametrize("kind", ["sql", "api"])
def test_an_unlisted_private_address_is_refused(
    kind: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    for host in ("nomis.client.example", "ula.client.example", "shared.client.example"):
        with pytest.raises(ConnectorRefused, match="resolves inside"):
            refuse_host(kind, host, allowed_hosts=None)
    _listed(monkeypatch, "crm.client.example", "10.20.0.0/16")
    for host in ("ula.client.example", "shared.client.example"):
        with pytest.raises(ConnectorRefused, match="resolves inside"):
            refuse_host(kind, host, allowed_hosts=None)
    # crm is listed by name, but a network entry admits only what resolves into that network.
    _listed(monkeypatch, "10.20.0.0/16")
    with pytest.raises(ConnectorRefused, match="resolves inside"):
        refuse_host(kind, "crm.client.example", allowed_hosts=None)


@pytest.mark.parametrize("kind", ["sql", "api"])
def test_a_listed_private_host_or_network_is_admitted(
    kind: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    _listed(monkeypatch, "nomis.client.example", "fd12:3456::/32", "100.64.0.0/10")
    assert refuse_host(kind, "nomis.client.example", allowed_hosts=None) == ["10.20.30.40"]
    assert refuse_host(kind, "ula.client.example", allowed_hosts=None) == ["fd12:3456::7"]
    assert refuse_host(kind, "shared.client.example", allowed_hosts=None) == ["100.64.3.2"]
    # The egress allow-list is still asked, as for any host.
    with pytest.raises(ConnectorRefused, match="egress allow-list"):
        refuse_host(kind, "nomis.client.example", allowed_hosts=["telco.example"])
    refuse_host(kind, "nomis.client.example", allowed_hosts=["nomis.client.example"])


def test_no_list_admits_this_machine_or_the_metadata_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Even if `osprey.yaml`'s check were bypassed (a hand-edited `deployment.env`), the Conduit
    admits only a private address: a listed name resolving to loopback or link-local is refused."""
    _listed(monkeypatch, "loop.client.example", "meta.client.example", "127.0.0.0/8",
            "169.254.0.0/16", "0.0.0.0/0", "postgres", "localhost")  # fmt: skip
    for host in ("loop.client.example", "meta.client.example", "postgres", "localhost"):
        with pytest.raises(ConnectorRefused):
            refuse_host("sql", host, allowed_hosts=None)
    with pytest.raises(ConnectorRefused):
        refuse_host("api", "nomis.client.example", allowed_hosts=None)  # 0.0.0.0/0 admits nothing


@pytest.mark.parametrize(
    "entry",
    ["127.0.0.0/8", "127.0.0.1", "169.254.169.254", "169.254.0.0/16", "0.0.0.0/0", "::1",
     "fe80::/10", "10.0.0.0/7", "8.8.8.8", "postgres", "localhost", "db.localhost",
     "*.client.example", "http://db.client.example"],
)  # fmt: skip
def test_osprey_yaml_refuses_an_entry_no_list_may_hold(entry: str) -> None:
    with pytest.raises(ValidationError):
        ConnectorsConfig(private_hosts=[entry])


def test_apply_renders_the_list_for_the_conduit() -> None:
    from harness.render import _render_env as render_env

    entries = ["nomis.client.example", "10.20.0.0/16", "fd12:3456::/32"]
    config = OspreyConfig(connectors=ConnectorsConfig(private_hosts=entries))
    env = render_env(config)
    assert "OSPREY_CONNECTOR_PRIVATE=nomis.client.example,10.20.0.0/16,fd12:3456::/32\n" in env
    assert "OSPREY_CONNECTOR_PRIVATE" not in render_env(OspreyConfig())


PEOPLE = {"admin": Principal(id="adm-1", clearance="SECRET", org_unit="unit-1",
                             roles=["osprey-admin"])}  # fmt: skip


class _Resolver:
    def resolve(self, token: str) -> Principal:
        return PEOPLE[token]


class _Audit:
    async def record(self, **kwargs: Any) -> None:
        return None


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[TestClient]:
    monkeypatch.setenv("OSPREY_INGEST_ROOT", str(tmp_path))
    for name, value in {"principal_resolver": _Resolver(), "sources": InMemorySourceStore(),
                        "audit": _Audit()}.items():  # fmt: skip
        monkeypatch.setattr(app.state, name, value, raising=False)
    yield TestClient(app, raise_server_exceptions=False)


def test_an_administrator_names_a_listed_private_connection_and_not_an_unlisted_one(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def name(host: str, secret: str) -> Any:
        body = {"kind": "sql", "name": f"Client {host}", "datasets": ["ds-a"],
                "settings": {"kind": "sql", "host": host, "database": "nomis", "user": "reader",
                             "secret": secret}}  # fmt: skip
        return client.post("/v1/admin/connections", json=body,
                           headers={"Authorization": "Bearer admin"})  # fmt: skip

    refused = name("nomis.client.example", "NOMIS_A")
    assert refused.status_code == 422 and "resolves inside" in refused.text
    _listed(monkeypatch, "nomis.client.example")
    kept = name("nomis.client.example", "NOMIS_B")
    assert kept.status_code == 201, kept.text
    assert name("crm.client.example", "CRM").status_code == 422


def test_the_save_check_and_the_read_check_read_the_same_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _listed(monkeypatch, "10.20.0.0/16")
    refuse_connection_hosts(SqlConnectionSettings(host="nomis.client.example", database="nomis",
                                                  user="reader", secret="NOMIS"))  # fmt: skip
    with pytest.raises(ConnectorRefused, match="resolves inside"):
        refuse_connection_hosts(ApiConnectionSettings(base_url="https://crm.client.example"))
    assert datetime.now(UTC)  # (the module's imports kept honest)
