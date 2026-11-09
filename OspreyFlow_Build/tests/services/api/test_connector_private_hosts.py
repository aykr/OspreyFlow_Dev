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
  `test_an_administrator_names_a_listed_private_connection_and_not_an_unlisted_one`;
- a cloud's metadata service inside a private range (AWS's `fd00:ec2::254`, Alibaba's
  `100.100.100.200`) admitted by a broad entry —
  `test_no_list_admits_a_metadata_service_inside_a_range`;
- the deployment's own networks (Docker's bridge, its gateway, `host.docker.internal`, a cluster's
  services) admitted by a client's LAN range — `test_no_list_admits_the_deployments_own_networks`
  and `test_the_own_networks_are_read_from_the_route_tables`;
- a name resolving to several addresses admitted by its first —
  `test_every_address_a_name_resolves_to_is_judged`;
- an IPv6 form carrying an IPv4 address judged by its IPv6 form —
  `test_an_ipv6_form_is_judged_by_the_ipv4_address_it_carries`;
- the read path not reading the list, or a SQL connection re-resolving the name after the check
  (DNS rebinding) — `test_the_read_checks_read_the_list_and_sql_connects_to_the_checked_address`;
- a name that does not resolve read anyway — `test_a_sql_host_that_does_not_resolve_is_refused`;
- a client CA that is not a certificate kept — `test_a_connections_ca_certificate_is_a_certificate`.
"""

from __future__ import annotations

import ipaddress
import ssl
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from services.api import connector_reads
from services.api.app import app
from services.api.connector_reads import (
    Readers,
    check_connection,
    refuse_connection_hosts,
    refuse_host,
)
from services.api.sources import InMemorySourceStore
from services.ingest.connectors.reads import ConnectorRefused

from schemas.deployment import ConnectorsConfig, OspreyConfig
from schemas.domain import Principal
from schemas.sources import ApiConnectionSettings, Connection, SqlConnectionSettings

ANSWERS: dict[str, list[str]] = {
    "nomis.client.example": ["10.20.30.40"],
    "crm.client.example": ["10.99.0.7"],
    "ula.client.example": ["fd12:3456::7"],
    "shared.client.example": ["100.64.3.2"],
    "loop.client.example": ["127.0.0.1"],
    "meta.client.example": ["169.254.169.254"],
    "telco.example": ["93.184.215.14"],
    "aws.client.example": ["fd00:ec2::254"],
    "ali.client.example": ["100.100.100.200"],
    "bridge.client.example": ["172.18.0.5"],
    "dockerhost.client.example": ["192.168.65.254"],
    "lan.client.example": ["172.20.4.9"],
    "mixed.client.example": ["10.20.30.40", "10.99.0.7"],
    "public-and-private.client.example": ["93.184.215.14", "10.20.30.40"],
    "mapped.client.example": ["::ffff:127.0.0.1"],
    "nat64.client.example": ["64:ff9b::a9fe:a9fe"],
    "sixtofour.client.example": ["2002:7f00:1::"],
    "mapped-private.client.example": ["::ffff:10.20.30.40"],
    "compat.client.example": ["::7f00:1"],
    "sitelocal.client.example": ["fec0::1"],
    "reserved.client.example": ["100::1"],
}


@pytest.fixture(autouse=True)
def dns(monkeypatch: pytest.MonkeyPatch) -> dict[str, list[str]]:
    """What each name resolves to, by the test: no lookup leaves the machine."""
    monkeypatch.setattr(connector_reads, "resolve_host", lambda host: ANSWERS.get(host, []))
    monkeypatch.setattr(connector_reads, "own_networks", lambda: [])
    monkeypatch.delenv("OSPREY_CONNECTOR_PRIVATE", raising=False)
    return ANSWERS


def _listed(monkeypatch: pytest.MonkeyPatch, *entries: str) -> None:
    monkeypatch.setenv("OSPREY_CONNECTOR_PRIVATE", ",".join(entries))


@pytest.mark.parametrize("kind", ["sql", "api"])
def test_an_unlisted_private_address_is_refused(kind: str, monkeypatch: pytest.MonkeyPatch) -> None:
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
    _listed(monkeypatch, "loop.client.example", "meta.client.example")
    for host in ("loop.client.example", "meta.client.example"):
        with pytest.raises(ConnectorRefused, match="resolves inside"):
            refuse_host("sql", host, allowed_hosts=None)


@pytest.mark.parametrize(
    "entry",
    ["127.0.0.0/8", "127.0.0.1", "169.254.169.254", "169.254.0.0/16", "0.0.0.0/0", "::1",
     "fe80::/10", "10.0.0.0/7", "8.8.8.8", "postgres", "localhost", "db.localhost",
     "*.client.example", "http://db.client.example", "fd00:ec2::/32", "fd00:ec2::254",
     "100.100.0.0/16", "100.100.100.200", "host.docker.internal", "api.osprey.svc",
     "api.osprey.svc.cluster.local", "172.16.0.0/11"],
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


def test_no_list_admits_a_metadata_service_inside_a_range(monkeypatch: pytest.MonkeyPatch) -> None:
    _listed(monkeypatch, "fd00::/8", "100.64.0.0/10", "aws.client.example", "ali.client.example")
    for host in ("aws.client.example", "ali.client.example"):
        with pytest.raises(ConnectorRefused, match="resolves inside"):
            refuse_host("api", host, allowed_hosts=None)
    # The same entries still admit an ordinary address in those ranges.
    assert refuse_host("api", "shared.client.example", allowed_hosts=None) == ["100.64.3.2"]
    assert refuse_host("api", "ula.client.example", allowed_hosts=None) == ["fd12:3456::7"]


def test_no_list_admits_the_deployments_own_networks(monkeypatch: pytest.MonkeyPatch) -> None:
    """A client's LAN range that happens to hold Docker's bridge or the host's address admits
    neither, by network or by name; an address of the client's outside them still is."""
    own = [ipaddress.ip_network("172.18.0.0/16"), ipaddress.ip_network("192.168.65.254/32")]
    monkeypatch.setattr(connector_reads, "own_networks", lambda: own)
    _listed(monkeypatch, "172.16.0.0/12", "192.168.0.0/16", "bridge.client.example")
    for host in ("bridge.client.example", "dockerhost.client.example"):
        with pytest.raises(ConnectorRefused, match="resolves inside"):
            refuse_host("sql", host, allowed_hosts=None)
    assert refuse_host("sql", "lan.client.example", allowed_hosts=None) == ["172.20.4.9"]
    for platform in ("host.docker.internal", "api.osprey.svc.cluster.local"):
        with pytest.raises(ValidationError):
            SqlConnectionSettings(host=platform, database="d", user="u", secret="S")


def test_the_own_networks_are_read_from_the_route_tables(tmp_path: Path) -> None:
    """A synthetic route table as Linux writes it: the bridge's network, and the gateway (on Docker,
    the host itself); IPv6's link-local and multicast routes left out."""
    route = tmp_path / "route"
    route.write_text(
        "Iface\tDestination\tGateway\tFlags\tRefCnt\tUse\tMetric\tMask\tMTU\tWindow\tIRTT\n"
        "eth0\t00000000\t010012AC\t0003\t0\t0\t0\t00000000\t0\t0\t0\n"
        "eth0\t000012AC\t00000000\t0001\t0\t0\t0\t0000FFFF\t0\t0\t0\n"
    )
    route6 = tmp_path / "ipv6_route"
    route6.write_text(
        "fd000000000000000000000000000000 40 00000000000000000000000000000000 00 "
        "00000000000000000000000000000000 00000100 00000000 00000000 00000001 eth0\n"
        "fe800000000000000000000000000000 40 00000000000000000000000000000000 00 "
        "00000000000000000000000000000000 00000100 00000000 00000000 00000001 eth0\n"
    )
    found = connector_reads._proc_routes(str(route), str(route6))
    assert ipaddress.ip_network("172.18.0.0/16") in found
    assert ipaddress.ip_network("172.18.0.1/32") in found
    assert ipaddress.ip_network("fd00::/64") in found
    assert not any(n.version == 6 and n.network_address.is_link_local for n in found)
    assert connector_reads._proc_routes(str(tmp_path / "none"), str(tmp_path / "none6")) == []


def test_every_address_a_name_resolves_to_is_judged(monkeypatch: pytest.MonkeyPatch) -> None:
    _listed(monkeypatch, "10.20.0.0/16")
    with pytest.raises(ConnectorRefused, match="resolves inside"):
        refuse_host("sql", "mixed.client.example", allowed_hosts=None)  # 10.99.0.7 unlisted
    assert refuse_host("sql", "public-and-private.client.example", allowed_hosts=None) == [
        "93.184.215.14", "10.20.30.40"]  # fmt: skip


def test_an_ipv6_form_is_judged_by_the_ipv4_address_it_carries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    names = ("mapped.client.example", "nat64.client.example", "sixtofour.client.example")
    _listed(monkeypatch, *names)
    for host in names:  # loopback and the metadata service, carried in IPv6
        with pytest.raises(ConnectorRefused, match="resolves inside"):
            refuse_host("api", host, allowed_hosts=None)
    _listed(monkeypatch, "10.20.0.0/16")
    assert refuse_host("api", "mapped-private.client.example", allowed_hosts=None) == [
        "::ffff:10.20.30.40"]  # fmt: skip


def _sql_connection(host: str) -> Connection:
    return Connection(
        id="conn-1", kind="sql", name="Client", created_by="adm-1", created_at=datetime.now(UTC),
        settings=SqlConnectionSettings(host=host, database="nomis", user="reader", secret="NOMIS"),
        datasets=["ds-a"],
    )  # fmt: skip


async def test_the_read_checks_read_the_list_and_sql_connects_to_the_checked_address(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test connection and every read go through `Readers`: the list is read there, and asyncpg is
    sent to the address that was checked, the host's name kept for TLS's name check, so a name
    rebound after the check is never connected to."""
    monkeypatch.setenv("OSPREY_CONNECTION_SECRET_NOMIS", "fixture-only")
    monkeypatch.setenv("OSPREY_CONNECTOR_SECRETS", "NOMIS")  # declared (Amendment 15)
    seen: list[dict[str, Any]] = []

    async def connect(**kw: Any) -> Any:
        seen.append(kw)
        ANSWERS["nomis.client.example"] = ["127.0.0.1"]  # rebound once checked
        raise OSError("the fixture connects nowhere")

    readers = Readers(sql_connect=connect, allowed_hosts=["nomis.client.example"])
    unlisted = await check_connection(_sql_connection("nomis.client.example"), readers)
    assert not unlisted.ok and "resolves inside" in unlisted.words and not seen
    _listed(monkeypatch, "10.20.0.0/16")
    monkeypatch.setitem(ANSWERS, "nomis.client.example", ["10.20.30.40"])
    await check_connection(_sql_connection("nomis.client.example"), readers)
    assert seen[0]["host"] == "10.20.30.40"
    assert seen[0]["ssl"].server_name == "nomis.client.example"
    # The API's own pin reads the same list.
    monkeypatch.setitem(ANSWERS, "crm.client.example", ["10.20.9.9"])
    api = Readers(allowed_hosts=["crm.client.example"])
    assert api.pin("https://crm.client.example/v1") == ["10.20.9.9"]
    _listed(monkeypatch, "10.99.0.0/16")
    with pytest.raises(ConnectorRefused, match="resolves inside"):
        api.pin("https://crm.client.example/v1")


def test_a_sql_host_that_does_not_resolve_is_refused() -> None:
    readers = Readers(allowed_hosts=["gone.client.example"])
    with pytest.raises(ConnectorRefused, match="does not resolve"):
        readers.sql_addresses("gone.client.example")


def test_a_connections_ca_certificate_is_a_certificate() -> None:
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Synthetic client CA")])
    now = datetime.now(UTC)
    cert = (
        x509.CertificateBuilder().subject_name(name).issuer_name(name)
        .public_key(key.public_key()).serial_number(1)
        .not_valid_before(now).not_valid_after(now.replace(year=now.year + 1))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )  # fmt: skip
    pem = cert.public_bytes(serialization.Encoding.PEM).decode()
    kept = SqlConnectionSettings(host="db.client.example", database="d", user="u", secret="S",
                                 ca_certificate=pem)  # fmt: skip
    assert kept.ca_certificate == pem.strip()
    assert ApiConnectionSettings(base_url="https://crm.client.example", ca_certificate=pem)
    key_pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                serialization.NoEncryption()).decode()  # fmt: skip
    for wrong in ("not a certificate", key_pem, pem + key_pem,
                  "-----BEGIN CERTIFICATE-----\nAAAA\n-----END CERTIFICATE-----"):  # fmt: skip
        with pytest.raises(ValidationError):
            SqlConnectionSettings(host="db.client.example", database="d", user="u", secret="S",
                                  ca_certificate=wrong)  # fmt: skip
    with pytest.raises(ValidationError, match="verify-full"):
        SqlConnectionSettings(host="db.client.example", database="d", user="u", secret="S",
                              tls="require", ca_certificate=pem)  # fmt: skip


def test_reserved_and_site_local_ipv6_are_inside(monkeypatch: pytest.MonkeyPatch) -> None:
    """Python counts `::/96` (IPv4-compatible, `::7f00:1` is loopback) and `fec0::/10` (site-local)
    as global; both are refused, listed or not (the orchestrator's review of Amendment 15,
    item 3)."""
    from schemas.sources import address_is_inside

    for address in ("::7f00:1", "::a14:1e28", "fec0::1", "100::1"):
        assert address_is_inside(ipaddress.ip_address(address)), address
    assert not address_is_inside(ipaddress.ip_address("2a00:1450:4009:81f::200e"))
    for host in ("compat.client.example", "sitelocal.client.example", "reserved.client.example"):
        with pytest.raises(ConnectorRefused, match="resolves inside"):
            refuse_host("api", host, allowed_hosts=None)
    _listed(monkeypatch, "compat.client.example", "sitelocal.client.example")
    for host in ("compat.client.example", "sitelocal.client.example"):
        with pytest.raises(ConnectorRefused, match="resolves inside"):
            refuse_host("sql", host, allowed_hosts=None)


def test_the_resolver_s_order_is_kept_and_unreachable_families_left_out(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`resolve_host` keeps getaddrinfo's own order (not text order, which puts `2001:…` before
    `93.…`) and asks for `AI_ADDRCONFIG`, so a family with no route is left out."""
    import socket

    asked: dict[str, Any] = {}

    def getaddrinfo(host: str, port: Any, **kw: Any) -> list[Any]:
        asked.update(kw)
        return [(socket.AF_INET, 1, 6, "", ("93.184.215.14", 0)),
                (socket.AF_INET6, 1, 6, "", ("2606:2800:220:1::1", 0, 0, 0)),
                (socket.AF_INET, 1, 6, "", ("93.184.215.14", 0))]  # fmt: skip

    monkeypatch.undo()  # the real resolve_host, its lookup stood in for
    monkeypatch.setattr(connector_reads.socket, "getaddrinfo", getaddrinfo)
    assert connector_reads.resolve_host("dual.example") == ["93.184.215.14", "2606:2800:220:1::1"]
    assert asked["flags"] & socket.AI_ADDRCONFIG


async def test_sql_reaches_each_checked_address_in_order_and_signs_in_at_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Items 4 and 11, and the lane review that followed: each checked address is first only reached
    over TCP, nothing sent; asyncpg is given the first that answers and no other, so whatever then
    fails (a sign-in refused, a timeout or reset after the password went, a certificate) is final
    and no second server is ever sent the password."""
    import asyncpg
    from services.ingest.connectors.sql_connector import check_sql_connection

    v6, v4 = "2a00:1450:4009:81f::200e", "93.184.215.14"
    reachable: dict[str, bool] = {v6: False, v4: True}
    probed: list[str] = []
    signed: list[str] = []

    async def reach(address: str, port: int) -> bool:
        probed.append(address)
        return reachable[address]

    class _Conn:
        async def fetchrow(self, _sql: str) -> dict[str, Any]:
            return {"superuser": False, "owned": 0, "writable": 0}

        async def close(self) -> None:
            return None

    failure: BaseException | None = None

    async def connect(**kw: Any) -> Any:
        signed.append(kw["host"])
        if failure is not None:
            raise failure
        return _Conn()

    settings = SqlConnectionSettings(host="dual.client.example", database="nomis", user="reader",
                                     secret="NOMIS")  # fmt: skip

    async def test() -> Any:
        probed.clear()
        signed.clear()
        return await check_sql_connection(settings, secret="pw", connect=connect,
                                          addresses=[v6, v4], reach=reach)  # fmt: skip

    tested = await test()
    assert tested.ok, tested.words
    assert probed == [v6, v4] and signed == [v4]
    reachable[v6] = True
    for failure, words in (
        (asyncpg.InvalidPasswordError("password authentication failed"), "refused the sign-in"),
        (TimeoutError(), "could not be reached"),
        (ConnectionResetError("reset by peer"), "could not be reached"),
        (ssl.SSLCertVerificationError("certificate verify failed"),
         "certificate could not be verified"),
    ):  # fmt: skip
        refused = await test()
        assert not refused.ok and words in refused.words, (failure, refused.words)
        assert "would not speak TLS" not in refused.words
        assert signed == [v6], (failure, signed)  # never the second address
    failure = None
    reachable[v6] = reachable[v4] = False
    none = await test()
    assert not none.ok and "any address" in none.words and signed == []


async def test_an_api_request_tries_each_checked_address_in_order() -> None:
    import httpx
    from services.ingest.connectors.reads import read_api

    from schemas.sources import ApiRead

    tried: list[str] = []

    def answer(request: httpx.Request) -> httpx.Response:
        tried.append(request.url.host)
        if ":" in request.url.host:
            raise httpx.ConnectError("Network is unreachable", request=request)
        return httpx.Response(200, json={"data": [{"n": 1}]})

    addresses = ["2a00:1450:4009:81f::200e", "93.184.215.14"]
    read = await read_api(
        ApiConnectionSettings(base_url="https://crm.client.example"),
        ApiRead(path="/v1/n", records_at="data"), secret=None,
        allowed_hosts=["crm.client.example"], transport=httpx.MockTransport(answer),
        before_request=lambda _url: list(addresses),
    )  # fmt: skip
    assert len(read.rows) == 1 and tried == addresses


async def test_an_api_request_stops_at_a_refusal_and_never_sends_the_second_address() -> None:
    """An answer (401, any status), a TLS failure or a certificate refusal at the first address is
    final: the second is never sent the request or the bearer token (decision 10)."""
    import httpx
    from services.ingest.connectors.reads import read_api

    from schemas.sources import ApiRead

    first, second = "2a00:1450:4009:81f::200e", "93.184.215.14"
    tried: list[str] = []

    async def read(fail: Any) -> None:
        tried.clear()

        def answer(request: httpx.Request) -> httpx.Response:
            tried.append(request.url.host)
            if request.url.host == first:
                return fail(request)
            return httpx.Response(200, json={"data": [{"n": 1}]})

        await read_api(
            ApiConnectionSettings(base_url="https://crm.client.example", auth="bearer",
                                  secret="CRM"),
            ApiRead(path="/v1/n", records_at="data"), secret="synthetic-token",
            allowed_hosts=["crm.client.example"], transport=httpx.MockTransport(answer),
            before_request=lambda _url: [first, second],
        )  # fmt: skip

    def tls_error(request: httpx.Request) -> httpx.Response:
        try:
            raise ssl.SSLError("wrong version number")
        except ssl.SSLError as exc:
            raise httpx.ConnectError("handshake failed", request=request) from exc

    def unverified(request: httpx.Request) -> httpx.Response:
        try:
            raise ssl.SSLCertVerificationError("certificate verify failed")
        except ssl.SSLError as exc:
            raise httpx.ConnectError("handshake failed", request=request) from exc

    for fail, words in (
        (lambda r: httpx.Response(401), "refused the sign-in"),
        (lambda r: httpx.Response(500), "not 200"),
        (tls_error, "TLS handshake failed"),
        (unverified, "certificate could not be verified"),
    ):
        with pytest.raises(ConnectorRefused, match=words):
            await read(fail)
        assert tried == [first], (words, tried)


@pytest.mark.parametrize("name", ["nomis", "NOMIS-REPLICA", "1NOMIS", "", "NOMIS,CRM", "A" * 65])
def test_osprey_yaml_refuses_a_secret_name_that_is_not_one(name: str) -> None:
    with pytest.raises(ValidationError):
        ConnectorsConfig(secrets=[name])
    assert ConnectorsConfig(secrets=["NOMIS_REPLICA"]).secrets == ["NOMIS_REPLICA"]
