"""R1's OpenSearch domain stand-in (v0.5.2, for v052-r1 on kind; ADR-148 Amendment 13): the S3, STS and KMS
stand-in (`tests/fixtures/cloud_platform/s3_standin.py`) answers as the namespace's OpenSearch domain too, so
the domain checks the very sessions its STS issued by web identity (IRSA), as the real one checks IAM's.

A request to the domain's host is **verified as service `es`** (SigV4: the signature over the canonical request,
the payload's hash, the session's token, its expiry, the clock), **authorised by the domain's access policy**
(the roles it admits, the namespace's alone), and only then **proxied** to the OpenSearch behind it. Each
refusal is the domain's own, 403 with a JSON `message`, and never reaches OpenSearch.

The requests are signed as rules' search client signs them (ADR-150 decision 7: opensearch-py's
`AWSV4SignerAsyncAuth`, botocore's SigV4 for service `es`, headers `content-type`, `host`,
`x-amz-content-sha256`, `x-amz-date` and `x-amz-security-token`), with botocore itself, not a hand-written
signer (rule 15).
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import threading
import urllib.error
import urllib.request
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from botocore.credentials import Credentials

from tests.fixtures.cloud_platform.s3_standin import Principal, Role, StandIn, mint_token, serve

ISSUER_SECRET = "issuer-secret"
SEARCH_ROLE = "arn:aws:iam::123456789012:role/ospreyflow-poc-service"
OTHER_ROLE = "arn:aws:iam::123456789012:role/ospreyflow-poc-backup"
DOMAIN = "vpc-ospreyflow-poc-search-abc123.eu-west-2.es.amazonaws.com"


class _OpenSearch(BaseHTTPRequestHandler):
    """The OpenSearch behind the stand-in: answers with what reached it, and counts it."""

    seen: list[dict[str, Any]] = []

    def _answer(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        body = raw.decode(errors="replace")
        self.seen.append({"method": self.command, "path": self.path, "body": body,
                          "authorization": self.headers.get("Authorization"),
                          "encoding": self.headers.get("Content-Encoding")})  # fmt: skip
        data = json.dumps({"reached": self.path, "method": self.command}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    do_GET = do_POST = do_PUT = do_DELETE = _answer  # noqa: N815 - http.server's names

    def log_message(self, *args: Any) -> None:
        pass


@pytest.fixture
def domain(tmp_path: Path) -> Iterator[tuple[str, StandIn]]:
    _OpenSearch.seen = []
    upstream = ThreadingHTTPServer(("127.0.0.1", 0), _OpenSearch)
    threading.Thread(target=upstream.serve_forever, daemon=True).start()
    stand_in = StandIn(root=tmp_path)
    for arn, subject in ((SEARCH_ROLE, "system:serviceaccount:ospreyflow-poc:ospreyflow"),
                         (OTHER_ROLE, "system:serviceaccount:ospreyflow-poc:ospreyflow-backup")):  # fmt: skip
        stand_in.roles[arn] = Role(arn=arn, policies=[], issuer_secret=ISSUER_SECRET, subject=subject)
    stand_in.configure_domains([{"host": DOMAIN, "roles": [SEARCH_ROLE],
                                 "upstream": f"http://127.0.0.1:{upstream.server_address[1]}"}])  # fmt: skip
    server = serve(stand_in)
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}", stand_in
    finally:
        server.shutdown()
        upstream.shutdown()


def _session(stand_in: StandIn, role: str = SEARCH_ROLE) -> Principal:
    subject = stand_in.roles[role].subject
    return stand_in.assume_role_with_web_identity(
        {"RoleArn": role, "WebIdentityToken": mint_token(ISSUER_SECRET, sub=subject), "RoleSessionName": "pod"}
    )


def _signed(session: Principal, method: str, path: str, body: bytes = b"", *, service: str = "es",
            region: str = "eu-west-2", secret: str | None = None, token: bool = True) -> AWSRequest:  # fmt: skip
    """As opensearch-py's AWSV4SignerAsyncAuth signs: the payload's hash among the headers."""
    request = AWSRequest(method=method, url=f"https://{DOMAIN}{path}", data=body, headers={
        "content-type": "application/json", "x-amz-content-sha256": hashlib.sha256(body).hexdigest()})  # fmt: skip
    credentials = Credentials(session.access_key, secret or session.secret, session.token if token else None)
    SigV4Auth(credentials, service, region).add_auth(request)
    return request


def _send(base: str, request: AWSRequest | None, *, path: str = "/", body: bytes = b"",
          tamper: bytes | None = None) -> tuple[int, dict[str, Any]]:  # fmt: skip
    """Over loopback, with the domain's name as the request's Host, as the pods reach it on kind."""
    # The Host the pods send on kind (the domain's name, which CoreDNS points at the stand-in); botocore
    # signs over it from the URL and leaves the header to the client.
    headers = {**(dict(request.headers.items()) if request is not None else {}), "Host": DOMAIN}
    method = request.method if request is not None else "GET"
    url = base + (request.url.split(DOMAIN, 1)[1] if request is not None else path)
    data = tamper if tamper is not None else (request.body if request is not None else body) or None
    sent = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(sent) as answer:
            return answer.status, json.loads(answer.read())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read())


def test_a_request_signed_by_the_namespace_s_role_reaches_opensearch(domain: tuple[str, StandIn]) -> None:
    base, stand_in = domain
    session = _session(stand_in)
    status, answer = _send(base, _signed(session, "GET", "/_cluster/health"))
    assert (status, answer["reached"]) == (200, "/_cluster/health")
    body = json.dumps({"query": {"match": {"name": "Ledger"}}}).encode()
    status, answer = _send(base, _signed(session, "POST", "/ospreyflow/_search?size=10", body))
    assert (status, answer["reached"]) == (200, "/ospreyflow/_search?size=10")
    assert _OpenSearch.seen[-1]["body"] == body.decode()


@pytest.mark.parametrize(
    ("case", "words"),
    [
        ("unsigned", "is not authorized"),
        ("another secret", "signature we calculated does not match"),
        ("signed for s3", "Credential should be scoped to correct service: 'es'"),
        ("another region", "eu-west-2"),
        ("no session token", "security token included in the request is invalid"),
        ("the body changed after signing", "signature we calculated does not match"),
        ("another role's session", "is not authorized to perform: es:ESHttpGet"),
    ],
)
def test_the_domain_refuses_what_it_refuses_and_opensearch_never_sees_it(
    domain: tuple[str, StandIn], case: str, words: str
) -> None:
    base, stand_in = domain
    session = _session(stand_in)
    request: AWSRequest | None
    tamper = None
    if case == "unsigned":
        request = None
    elif case == "another secret":
        request = _signed(session, "GET", "/", secret="not-the-secret")
    elif case == "signed for s3":
        request = _signed(session, "GET", "/", service="s3")
    elif case == "another region":
        request = _signed(session, "GET", "/", region="eu-west-1")
    elif case == "no session token":
        request = _signed(session, "GET", "/", token=False)
    elif case == "the body changed after signing":
        request = _signed(session, "POST", "/ospreyflow/_search", b'{"size": 1}')
        tamper = b'{"size": 9999}'
    else:
        request = _signed(_session(stand_in, OTHER_ROLE), "GET", "/")
    status, answer = _send(base, request, tamper=tamper)
    assert status == 403, answer
    assert words in answer["message"], answer
    assert _OpenSearch.seen == []


def test_an_expired_session_is_refused(domain: tuple[str, StandIn]) -> None:
    base, stand_in = domain
    session = _session(stand_in)
    stand_in.expire(session.access_key)
    status, answer = _send(base, _signed(session, "GET", "/"))
    assert status == 403 and "expired" in answer["message"]
    assert _OpenSearch.seen == []


def test_s3_on_the_same_stand_in_is_as_it_was(domain: tuple[str, StandIn]) -> None:
    """The domain is chosen by the request's Host alone: an S3 request is S3's as before."""
    base, _ = domain
    request = urllib.request.Request(base + "/a-bucket/key", method="GET")
    with pytest.raises(urllib.error.HTTPError) as refused:
        urllib.request.urlopen(request)
    assert refused.value.code == 403
    assert b"<Code>AccessDenied</Code>" in refused.value.read()


# -- what the domain admits and refuses beyond the signature (the review of 6998234) --


@pytest.mark.parametrize(
    "path",
    ["/ospreyflow-*/_search", "/a,b/_search", "/ospreyflow/_doc/person:123",
     "/ospreyflow/_doc/a%2Fb", "/ospreyflow/./_search", "/ospreyflow/_search/"],
)  # fmt: skip
def test_paths_botocore_signs_for_es_are_admitted(domain: tuple[str, StandIn], path: str) -> None:
    """For every service but S3, SigV4's canonical URI is the path normalised and percent-encoded
    again (botocore's `SigV4Auth`); a stand-in hashing the wire path refuses a wildcard index, a
    comma list or an id with ':' that the real domain admits, and would invite a client "fix"."""
    base, stand_in = domain
    status, answer = _send(base, _signed(_session(stand_in), "GET", path))
    assert status == 200, answer
    assert _OpenSearch.seen and _OpenSearch.seen[-1]["path"] == path


def _at(stand_in: StandIn, offset: dt.timedelta) -> None:
    now = stand_in.clock()
    stand_in.clock = lambda: now + offset


@pytest.mark.parametrize(("minutes", "admitted"), [(4, True), (-4, True), (6, False), (-6, False)])
def test_the_domain_allows_five_minutes_of_clock_skew_not_s3s_fifteen(
    domain: tuple[str, StandIn], minutes: int, admitted: bool
) -> None:
    base, stand_in = domain
    request = _signed(_session(stand_in), "GET", "/_cluster/health")
    _at(stand_in, dt.timedelta(minutes=minutes))
    status, answer = _send(base, request)
    if admitted:
        assert status == 200, answer
    else:
        assert status == 403 and "Signature expired" in answer["message"], answer
        assert _OpenSearch.seen == []


@pytest.mark.parametrize(
    ("size", "admitted"), [(10 * 1024 * 1024, True), (10 * 1024 * 1024 + 1, False)]
)
def test_a_body_over_the_poc_domains_ten_mib_is_refused_413(
    domain: tuple[str, StandIn], size: int, admitted: bool
) -> None:
    """t3.medium.search's largest request payload is 10 MiB; a bulk over it is the domain's 413,
    whoever signed it, never passed on to OpenSearch."""
    base, stand_in = domain
    body = b"{" + b" " * (size - 2) + b"}"
    status, answer = _send(base, _signed(_session(stand_in), "POST", "/_bulk", body))
    if admitted:
        assert status == 200, answer
    else:
        assert status == 413 and "10485760" in answer["Message"], answer
        assert _OpenSearch.seen == []


def test_a_refusal_names_the_account_and_the_domain(domain: tuple[str, StandIn]) -> None:
    base, stand_in = domain
    status, answer = _send(base, _signed(_session(stand_in, OTHER_ROLE), "GET", "/"))
    assert status == 403
    assert "arn:aws:es:eu-west-2:123456789012:domain/ospreyflow-poc-search/" in answer["message"], (
        answer
    )


def test_a_compressed_body_reaches_opensearch_with_its_encoding(
    domain: tuple[str, StandIn],
) -> None:
    """opensearch-py's `http_compress` sends gzip, `content-encoding: gzip`: passed on with it."""
    import gzip

    base, stand_in = domain
    body = gzip.compress(b'{"size": 1}')
    headers = {"content-type": "application/json", "content-encoding": "gzip",
               "x-amz-content-sha256": hashlib.sha256(body).hexdigest()}  # fmt: skip
    url = f"https://{DOMAIN}/ospreyflow/_search"
    request = AWSRequest(method="POST", url=url, data=body, headers=headers)
    session = _session(stand_in)
    SigV4Auth(
        Credentials(session.access_key, session.secret, session.token), "es", "eu-west-2"
    ).add_auth(request)
    status, answer = _send(base, request)
    assert status == 200, answer
    assert _OpenSearch.seen[-1]["encoding"] == "gzip"


def test_each_domain_request_is_logged_with_who_and_the_answer(
    domain: tuple[str, StandIn], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """R1's run reads the stand-in's log as its evidence that the domain admitted the service
    role and refused the rest (`r1_kind.checks`): one line per domain request, who, the answer."""
    monkeypatch.setenv("S3_STANDIN_LOG", "1")
    base, stand_in = domain
    _send(base, _signed(_session(stand_in), "GET", "/_cluster/health"))
    _send(base, _signed(_session(stand_in, OTHER_ROLE), "GET", "/_cluster/health"))
    _send(base, None, path="/_cluster/health")
    lines = [line for line in capsys.readouterr().err.splitlines() if line.startswith("domain: ")]
    assert lines == [
        f"domain: {DOMAIN} GET /_cluster/health 200 {SEARCH_ROLE}",
        f"domain: {DOMAIN} GET /_cluster/health 403 {OTHER_ROLE}",
        f"domain: {DOMAIN} GET /_cluster/health 403 anonymous",
    ]


def test_r1s_domain_probe_signs_as_a_pod_does_and_reports_both_answers(
    domain: tuple[str, StandIn],
) -> None:
    """The probe `r1_kind.checks` runs in a pod of the namespace, run here against the stand-in
    with a session's credentials in the environment (IRSA's, resolved): signed admitted, unsigned
    refused; another role's session refused; a closed port 9200 reported closed."""
    import subprocess
    import sys

    base, stand_in = domain
    # The probe asks by OPENSEARCH_URL's own host, here loopback: the domain answers on it too.
    [(host, behind)] = stand_in.domains.items()
    both = [{"host": h, "roles": behind["roles"], "upstream": behind["upstream"]}
            for h in (host, "127.0.0.1")]  # fmt: skip
    stand_in.configure_domains(both)
    gates = Path(__file__).parents[1] / "process/lanes/platform/gates"
    sys.path.insert(0, str(gates))
    try:
        import r1_kind
    finally:
        sys.path.remove(str(gates))
    said = {}
    for role in (SEARCH_ROLE, OTHER_ROLE):
        session = _session(stand_in, role)
        env = {"PATH": "/usr/bin:/bin", "AWS_ACCESS_KEY_ID": session.access_key,
               "AWS_SECRET_ACCESS_KEY": session.secret, "AWS_SESSION_TOKEN": session.token or "",
               "AWS_REGION": "eu-west-2", "R1_DIRECT": "127.0.0.1:9",
               "OPENSEARCH_URL": base}  # fmt: skip
        done = subprocess.run([sys.executable, "-c", r1_kind.DOMAIN_PROBE], env=env,
                              capture_output=True, text=True, timeout=60)  # fmt: skip
        assert done.returncode == 0, done.stderr
        said[role] = json.loads(done.stdout.strip().splitlines()[-1])
    mine, other = said[SEARCH_ROLE], said[OTHER_ROLE]
    assert mine["signed"][0] == 200 and mine["unsigned"][0] == 403 and mine["direct"] == "closed"
    assert other["signed"][0] == 403 and "not authorized" in other["signed"][1]
    assert [s["path"] for s in _OpenSearch.seen] == ["/_cluster/health"]
