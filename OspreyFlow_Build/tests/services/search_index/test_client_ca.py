"""ADR-150 decision 7, offline: the one client trusts the CA bundle a deployment names in
`SSL_CERT_FILE`, `AWS_CA_BUNDLE` or `REQUESTS_CA_BUNDLE` (first set wins, in that order), as the
AWS SDK and `requests` do, so an OpenSearch behind a private CA (a cluster's own, or a TLS-inspecting
proxy's) is reached, beside the system's own roots; a named bundle that is not there is refused in
words, never quietly dropped.

Against a real TLS server on 127.0.0.1 whose certificate a throwaway CA signed (`tls_fixture`, made
fresh per test): with no bundle named, the handshake is refused, as any client trusting only the
public roots refuses it (rule 15: the stand-in refuses what the real one refuses).
"""

from __future__ import annotations

import asyncio
import json
import ssl
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from opensearchpy import ConnectionError as OpenSearchConnectionError

from services.search_index.client import SearchIndexConfig, SearchIndexConfigError, search_client
from tests.connectors.tls_fixture import make_ca

VARIABLES = ("SSL_CERT_FILE", "AWS_CA_BUNDLE", "REQUESTS_CA_BUNDLE")
ANSWER = json.dumps({"cluster_name": "fixture", "version": {"number": "2.17.1"}}).encode()


@pytest.fixture
async def tls_server(tmp_path: Path) -> AsyncIterator[tuple[str, Path]]:
    """An HTTPS server on 127.0.0.1 answering every request with a cluster's `GET /`; its URL and
    the throwaway CA's bundle."""
    ca = make_ca()
    cert, key = ca.server("localhost")
    (tmp_path / "server.pem").write_bytes(cert)
    (tmp_path / "server.key").write_bytes(key)
    bundle = tmp_path / "ca.pem"
    bundle.write_text(ca.pem)
    context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    context.load_cert_chain(tmp_path / "server.pem", tmp_path / "server.key")

    async def answer(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            await reader.readuntil(b"\r\n\r\n")
            writer.write(
                b"HTTP/1.1 200 OK\r\ncontent-type: application/json\r\n"
                + f"content-length: {len(ANSWER)}\r\nconnection: close\r\n\r\n".encode()
                + ANSWER
            )
            await writer.drain()
        except (ConnectionError, asyncio.IncompleteReadError, ssl.SSLError):
            pass
        finally:
            writer.close()

    server = await asyncio.start_server(answer, "127.0.0.1", 0, ssl=context)
    port = server.sockets[0].getsockname()[1]
    try:
        yield f"https://localhost:{port}", bundle
    finally:
        server.close()
        await server.wait_closed()


def _environment(monkeypatch: pytest.MonkeyPatch, url: str, **named: str) -> None:
    """The process environment as a deployment sets it: the client is built from it, as the worker,
    the rebuild and the drift check build theirs (`search_client()` with no argument)."""
    for variable in (*VARIABLES, "SSL_CERT_DIR", "OPENSEARCH_SIGNING"):
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.setenv("OPENSEARCH_URL", url)
    for variable, value in named.items():
        monkeypatch.setenv(variable, value)


async def _get_root() -> object:
    client = search_client()
    try:
        return await client.info()
    finally:
        await client.close()


@pytest.mark.parametrize("variable", VARIABLES)
async def test_the_bundle_a_deployment_names_is_trusted(
    variable: str, tls_server: tuple[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    url, bundle = tls_server
    _environment(monkeypatch, url, **{variable: str(bundle)})
    assert (await _get_root())["cluster_name"] == "fixture"  # type: ignore[index]


async def test_with_no_bundle_named_the_private_ca_is_refused(
    tls_server: tuple[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    url, _ = tls_server
    _environment(monkeypatch, url)
    with pytest.raises(OpenSearchConnectionError, match="CERTIFICATE_VERIFY_FAILED|certificate"):
        await _get_root()


async def test_the_first_named_wins(
    tls_server: tuple[str, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`SSL_CERT_FILE` before `AWS_CA_BUNDLE` before `REQUESTS_CA_BUNDLE`: a wrong bundle first
    is refused even with the right one later."""
    url, bundle = tls_server
    other = tmp_path / "other.pem"
    other.write_text(make_ca().pem)
    _environment(monkeypatch, url, AWS_CA_BUNDLE=str(other), REQUESTS_CA_BUNDLE=str(bundle))
    assert SearchIndexConfig.from_env().ca_certs == str(other)
    with pytest.raises(OpenSearchConnectionError):
        await _get_root()


async def test_ssl_cert_file_wins_over_the_others(
    tls_server: tuple[str, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    url, bundle = tls_server
    other = tmp_path / "other.pem"
    other.write_text(make_ca().pem)
    _environment(monkeypatch, url, SSL_CERT_FILE=str(other), AWS_CA_BUNDLE=str(bundle))
    assert SearchIndexConfig.from_env().ca_certs == str(other)
    with pytest.raises(OpenSearchConnectionError):
        await _get_root()


def test_a_named_bundle_that_is_not_there_is_refused_in_words(tmp_path: Path) -> None:
    missing = tmp_path / "absent.pem"
    with pytest.raises(SearchIndexConfigError, match="AWS_CA_BUNDLE"):
        SearchIndexConfig.from_env({"AWS_CA_BUNDLE": str(missing)})
