"""ADR-150 decision 7: on cloud-platform the client signs every request with SigV4 for service `es`
(the owner's ruling for step 3a, 13 November 2026). A stand-in domain on this machine answers as an
Amazon OpenSearch domain without fine-grained access control does: 403 to a request that is unsigned,
signed for another service or region, or signed with a key it does not know; 200 only to one whose
signature it recomputes itself from the request it received (botocore's SigV4 over the same method,
path, query, headers and body). Its refusals are modelled, not only its grant (rule 15)."""

from __future__ import annotations

import re
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from botocore.credentials import Credentials

from services.search_index.client import SearchIndexConfig, search_client

KEY, SECRET, REGION = "AKIDSTANDIN", "secret-the-domain-knows", "eu-west-2"
_AUTH = re.compile(
    r"AWS4-HMAC-SHA256 Credential=(?P<key>[^/]+)/(?P<date>\d{8})/(?P<region>[^/]+)/(?P<service>[^/]+)"
    r"/aws4_request, SignedHeaders=(?P<signed>[^,]+), Signature=(?P<sig>[0-9a-f]+)"
)


class _Domain(BaseHTTPRequestHandler):
    def log_message(self, *args: object) -> None:  # quiet
        return

    def _refuse(self, why: str) -> None:
        body = f'{{"message":"{why}"}}'.encode()
        self.send_response(403)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 - http.server's name
        got = _AUTH.fullmatch(self.headers.get("authorization", ""))
        if got is None:
            return self._refuse("unsigned")
        if (got["key"], got["region"], got["service"]) != (KEY, REGION, "es"):
            return self._refuse("signed for another key, region or service")
        host = self.headers["host"]
        request = AWSRequest(method="GET", url=f"http://{host}{self.path}", data=b"")
        for name in got["signed"].split(";"):
            request.headers[name] = self.headers[name]
        request.context["timestamp"] = self.headers["x-amz-date"]
        signer = SigV4Auth(Credentials(KEY, SECRET), "es", REGION)
        canonical = signer.canonical_request(request)
        expected = signer.signature(signer.string_to_sign(request, canonical), request)
        if expected != got["sig"]:
            return self._refuse("the signature does not match")
        body = b'{"version":{"distribution":"opensearch","number":"2.17.1"}}'
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture
def domain() -> Iterator[str]:
    server = HTTPServer(("127.0.0.1", 0), _Domain)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()


async def _info(url: str, monkeypatch: pytest.MonkeyPatch, *, signing: str, secret: str = SECRET) -> int:
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", KEY)
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", secret)
    monkeypatch.delenv("AWS_SESSION_TOKEN", raising=False)
    monkeypatch.setenv("AWS_CONFIG_FILE", "/nonexistent")
    monkeypatch.setenv("AWS_SHARED_CREDENTIALS_FILE", "/nonexistent")
    env = {"OPENSEARCH_URL": url, "OPENSEARCH_SIGNING": signing, "OPENSEARCH_REGION": REGION}
    client = search_client(SearchIndexConfig.from_env(env))
    try:
        await client.info()
        return 200
    except Exception as exc:  # noqa: BLE001 - the status the domain answered is what is asserted
        return int(getattr(exc, "status_code", 0) or 0)
    finally:
        await client.close()


async def test_a_sigv4_client_is_answered(domain: str, monkeypatch: pytest.MonkeyPatch) -> None:
    assert await _info(domain, monkeypatch, signing="sigv4") == 200


async def test_an_unsigned_client_is_refused(domain: str, monkeypatch: pytest.MonkeyPatch) -> None:
    assert await _info(domain, monkeypatch, signing="none") == 403


async def test_a_client_signing_with_a_key_the_domain_does_not_know_is_refused(
    domain: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert await _info(domain, monkeypatch, signing="sigv4", secret="another-secret") == 403
