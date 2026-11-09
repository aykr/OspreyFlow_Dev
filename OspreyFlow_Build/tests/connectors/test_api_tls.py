"""The API connector's TLS against a real TLS server (`06_DECISIONS.md` ADR-140 Amendment 15
decision 6; the orchestrator's review of Amendment 15, item 2). `httpx.MockTransport` ignores
`verify`, so the other API tests cannot see TLS at all. Here a local HTTPS server on this machine
holds a certificate a synthetic CA signed for one name; the connector is used as a deployment uses
it, with no transport of the test's own: its own trust (the system's store and the connection's CA),
the request sent to the checked address with the host's name kept for SNI and the certificate's
name.

What a mistake would do, and the case that catches it:
- TLS that verifies nothing (`verify=False`, or no name check) — the untrusted-CA and other-name
  cases read rows, and the server is sent the request;
- the connection's CA dropped — `test_an_api_reads_over_tls_from_a_server_its_ca_signed` is refused;
- the name not kept for SNI and the name check (the certificate checked against the address) — the
  same case is refused.
"""

from __future__ import annotations

import asyncio
import json
import ssl
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from services.ingest.connectors.reads import ConnectorRefused, read_api

from schemas.sources import ApiConnectionSettings, ApiRead
from tests.connectors.tls_fixture import Ca, make_ca

NAME = "telco-tls.fixture.example"
ROWS = [{"number": "07700900001", "network": "Synthetic Mobile"}]


class _HttpsServer:
    """HTTPS on 127.0.0.1 for one certificate; counts the requests it was sent, and their hosts."""

    def __init__(self, cert_pem: bytes, key_pem: bytes, tmp: Path) -> None:
        (tmp / "server.crt").write_bytes(cert_pem)
        (tmp / "server.key").write_bytes(key_pem)
        self.context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        self.context.load_cert_chain(tmp / "server.crt", tmp / "server.key")
        self.requests = 0
        self.hosts: list[str] = []
        self.port = 0
        self._server: asyncio.Server | None = None

    async def start(self) -> None:
        self._server = await asyncio.start_server(
            self._client, "127.0.0.1", 0, ssl=self.context
        )
        self.port = self._server.sockets[0].getsockname()[1]

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()

    async def _client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            head = await reader.readuntil(b"\r\n\r\n")
        except (OSError, ssl.SSLError, asyncio.IncompleteReadError, asyncio.LimitOverrunError):
            writer.close()
            return
        self.requests += 1
        for line in head.decode("latin-1").split("\r\n"):
            if line.lower().startswith("host:"):
                self.hosts.append(line.split(":", 1)[1].strip())
        body = json.dumps({"data": ROWS}).encode()
        writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
                     b"Content-Length: " + str(len(body)).encode() + b"\r\n"
                     b"Connection: close\r\n\r\n" + body)  # fmt: skip
        await writer.drain()
        writer.close()


@pytest.fixture
def ca() -> Ca:
    return make_ca()


async def _serving(name: str, ca: Ca, tmp: Path) -> AsyncIterator[_HttpsServer]:
    server = _HttpsServer(*ca.server(name), tmp)
    await server.start()
    try:
        yield server
    finally:
        await server.stop()


async def _read(server: _HttpsServer, ca_pem: str | None) -> int:
    settings = ApiConnectionSettings(
        base_url=f"https://{NAME}:{server.port}", ca_certificate=ca_pem
    )
    read = await read_api(
        settings, ApiRead(path="/v1/numbers", records_at="data"), secret=None,
        allowed_hosts=[NAME], before_request=lambda _url: ["127.0.0.1"],
    )  # fmt: skip
    return len(read.rows)


async def test_an_api_reads_over_tls_from_a_server_its_ca_signed(ca: Ca, tmp_path: Path) -> None:
    async for server in _serving(NAME, ca, tmp_path):
        assert await _read(server, ca.pem) == len(ROWS)
        assert server.requests == 1
        assert server.hosts == [f"{NAME}:{server.port}"]  # the name kept for the Host header


async def test_an_api_refuses_a_certificate_from_a_ca_it_does_not_trust(
    ca: Ca, tmp_path: Path
) -> None:
    async for server in _serving(NAME, ca, tmp_path):
        with pytest.raises(ConnectorRefused, match="certificate could not be verified"):
            await _read(server, None)
        assert server.requests == 0


async def test_an_api_refuses_a_certificate_for_another_name(ca: Ca, tmp_path: Path) -> None:
    async for server in _serving("other.fixture.example", ca, tmp_path):
        with pytest.raises(ConnectorRefused, match="certificate could not be verified"):
            await _read(server, ca.pem)
        assert server.requests == 0
