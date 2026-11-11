"""A recorded S3 behind the real botocore client, for the deployment's own listing client
(`connector_reads.CloudS3Store`; the orchestrator's review of L1.9, round 1, items 6 and 8;
`process/CLAUDE.md` rule 15).

The client is the one `cloud_s3_store` builds: botocore's own S3 client, which serialises each
request, signs it and parses each answer exactly as against S3. Only the network is replaced, by a
`before-send` handler answering `ListObjectsV2` in S3's own XML (AWS's API reference). It honours
`MaxKeys` and `ContinuationToken` as S3 does (at most 1,000 keys a page), and **refuses what S3
refuses**, including what SeaweedFS, the live stand-in, never says:

- a bucket that does not exist (`NoSuchBucket`, 404), and a principal not granted it
  (`AccessDenied`, 403);
- a bucket in another region than the client signs for: `PermanentRedirect` (301, naming the
  bucket's own endpoint) and `AuthorizationHeaderMalformed` (400, naming its region). SeaweedFS has
  no regions, so these are confirmed only on the client's platform (part 2).

It records each request's host, its query and the key it was signed with, so a test can prove where
the client went, how much it asked for and that it signed as the deployment's own identity. Every
value is synthetic (rule 9).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from fnmatch import fnmatchcase
from typing import Any
from urllib.parse import parse_qs, unquote, urlsplit
from xml.sax.saxutils import escape

from botocore.awsrequest import AWSPreparedRequest, AWSResponse

_NS = "http://s3.amazonaws.com/doc/2006-03-01/"
#: S3's refusals by name: status, code, message and what else S3's own error document holds.
REFUSALS: dict[str, tuple[int, str, str, str]] = {
    "missing": (404, "NoSuchBucket", "The specified bucket does not exist", ""),
    "denied": (403, "AccessDenied", "Access Denied", ""),
    "moved": (301, "PermanentRedirect",
              "The bucket you are attempting to access must be addressed using the specified "
              "endpoint. Please send all future requests to this endpoint.",
              "<Endpoint>{bucket}.s3.eu-west-1.amazonaws.com</Endpoint>"),
    "wrong_region": (400, "AuthorizationHeaderMalformed",
                     "The authorization header is malformed; the region 'eu-west-2' is wrong; "
                     "expecting 'eu-west-1'", "<Region>eu-west-1</Region>"),
}  # fmt: skip


class _Raw:
    def __init__(self, body: bytes) -> None:
        self.body = body

    def stream(self, **_: Any) -> Any:
        yield self.body


def _answer(url: str, status: int, body: str, headers: dict[str, str] | None = None) -> AWSResponse:
    data = body.encode()
    head = {"Content-Type": "application/xml", "x-amz-request-id": uuid.uuid4().hex[:16].upper(),
            **(headers or {})}  # fmt: skip
    return AWSResponse(url, status, head, _Raw(data))


@dataclass
class RecordedS3:
    """Buckets by name, each a list of (key, size); `refusing` names a bucket's refusal."""

    buckets: dict[str, list[tuple[str, int]]]
    refusing: dict[str, str] = field(default_factory=dict)
    #: A broken S3-compatible store: says a page is cut short, but gives no token to go on from.
    no_token: bool = False
    #: Every request: its host, its query and the access key it was signed with.
    requests: list[dict[str, Any]] = field(default_factory=list)
    #: The role's own statements, as the render makes them from the declaration
    #: (`harness.cloud_platform.terraform.connector_source_statements`), or None to grant everything.
    #: Given, S3 refuses as IAM would (403, `AccessDenied`): a listing whose `prefix` no `StringLike`
    #: value on `s3:prefix` matches, a listing with no prefix under a conditioned grant, and a key
    #: outside every `s3:GetObject` resource (L1.9 part 2, the orchestrator's review; rule 15).
    granted: list[dict[str, Any]] | None = None

    def attach(self, client: Any) -> Any:
        """`client` (botocore's S3 client) answered by this recording in place of the network."""
        client.meta.events.register("before-send.s3", self._send)
        return client

    @property
    def keys_listed(self) -> int:
        return sum(r["listed"] for r in self.requests)

    def _send(self, request: AWSPreparedRequest, **_: Any) -> AWSResponse:
        url = urlsplit(request.url)
        host = url.hostname or ""
        query = {k: v[0] for k, v in parse_qs(url.query, keep_blank_values=True).items()}
        authorization = request.headers.get("Authorization", b"")
        if isinstance(authorization, bytes):
            authorization = authorization.decode()
        key = authorization.split("Credential=", 1)[-1].split("/", 1)[0]
        record: dict[str, Any] = {"host": host, "query": query, "key": key, "listed": 0}
        self.requests.append(record)
        # Virtual-hosted: the bucket is the host's first label.
        bucket = host.split(".s3.", 1)[0]
        if bucket in self.refusing:
            status, code, message, extra = REFUSALS[self.refusing[bucket]]
            body = (
                f'<?xml version="1.0" encoding="UTF-8"?>\n<Error><Code>{code}</Code>'
                f"<Message>{escape(message)}</Message><BucketName>{bucket}</BucketName>"
                f"{extra.format(bucket=bucket)}<RequestId>SYNTHETIC</RequestId></Error>"
            )
            headers = {"x-amz-bucket-region": "eu-west-1"} if status in (301, 400) else {}
            return _answer(request.url, status, body, headers)
        if self.granted is not None and not self._allowed(bucket, url.path, query):
            status, code, message, _extra = REFUSALS["denied"]
            return _answer(request.url, status, f"<Error><Code>{code}</Code><Message>{message}"
                                                "</Message></Error>")  # fmt: skip
        if bucket not in self.buckets:
            status, code, message, _extra = REFUSALS["missing"]
            return _answer(request.url, status, f"<Error><Code>{code}</Code><Message>{message}"
                                                "</Message></Error>")  # fmt: skip
        assert query.get("list-type") == "2", "only ListObjectsV2 is recorded"
        return self._list(request.url, bucket, query, record)

    def _allowed(self, bucket: str, path: str, query: dict[str, str]) -> bool:
        """Whether IAM grants the request, from `granted` alone (deny by default, as IAM does)."""
        assert self.granted is not None
        listing = query.get("list-type") == "2"
        key = unquote(path.lstrip("/"))
        for statement in self.granted:
            if listing and "s3:ListBucket" in statement["actions"]:
                if f"arn:aws:s3:::{bucket}" not in statement["resources"]:
                    continue
                condition = statement.get("condition")
                if condition is None:
                    return True
                assert condition["test"] == "StringLike" and condition["variable"] == "s3:prefix"
                if "prefix" in query and any(
                    fnmatchcase(query["prefix"], value) for value in condition["values"]
                ):
                    return True
            elif not listing and "s3:GetObject" in statement["actions"]:
                if any(fnmatchcase(f"arn:aws:s3:::{bucket}/{key}", r)
                       for r in statement["resources"]):  # fmt: skip
                    return True
        return False

    def _list(self, url: str, bucket: str, query: dict[str, str], record: dict[str, Any]) -> Any:
        prefix = query.get("prefix", "")
        delimiter = query.get("delimiter", "")
        size = min(int(query.get("max-keys", "1000")), 1000)  # S3 gives at most 1,000 a page
        keys = sorted(k for k in self.buckets[bucket] if k[0].startswith(prefix))
        start = int(query.get("continuation-token", "0") or 0)
        contents, prefixes, at = [], [], start
        while at < len(keys) and len(contents) + len(prefixes) < size:
            key, length = keys[at]
            rest = key[len(prefix) :]
            if delimiter and delimiter in rest:
                common = prefix + rest.split(delimiter, 1)[0] + delimiter
                if common not in prefixes:
                    prefixes.append(common)
            else:
                contents.append((key, length))
            at += 1
        record["listed"] = len(contents)
        truncated = at < len(keys)
        parts = [f'<?xml version="1.0" encoding="UTF-8"?>\n<ListBucketResult xmlns="{_NS}">',
                 f"<Name>{bucket}</Name><Prefix>{escape(prefix)}</Prefix>",
                 f"<KeyCount>{len(contents) + len(prefixes)}</KeyCount><MaxKeys>{size}</MaxKeys>",
                 f"<IsTruncated>{'true' if truncated else 'false'}</IsTruncated>"]  # fmt: skip
        if delimiter:
            parts.append(f"<Delimiter>{escape(delimiter)}</Delimiter>")
        for key, length in contents:
            parts.append(f"<Contents><Key>{escape(key)}</Key>"
                         "<LastModified>2026-11-11T00:00:00.000Z</LastModified>"
                         f'<ETag>"synthetic"</ETag><Size>{length}</Size>'
                         "<StorageClass>STANDARD</StorageClass></Contents>")  # fmt: skip
        for common in prefixes:
            parts.append(f"<CommonPrefixes><Prefix>{escape(common)}</Prefix></CommonPrefixes>")
        if truncated and not self.no_token:
            parts.append(f"<NextContinuationToken>{at}</NextContinuationToken>")
        parts.append("</ListBucketResult>")
        return _answer(url, 200, "".join(parts))


class RefusingS3Server:
    """A local HTTP server answering every request with one of S3's documented refusals, for
    pyarrow's own S3 filesystem (its C++ SDK, which no `before-send` handler reaches). Used as a
    context manager; `endpoint` is what `S3FileSystem(endpoint_override=…, scheme="http")` takes.

    **Modelled, not measured against S3** (rule 15): the answers are AWS's documented ones for a
    bucket in another region than the client signs for: `PermanentRedirect` (301, with the bucket's
    region in `x-amz-bucket-region`) and `AuthorizationHeaderMalformed` (400, likewise); a HEAD's
    answer has no body, as S3's has none. What pyarrow does with them **is** measured here, on the
    pinned pyarrow (11 November 2026, 26.0.0): it follows neither, sending one request to one host,
    and raises `OSError` naming `AWS Error UNKNOWN (HTTP status 301|400)`. Every request's host and
    path is recorded, so a test proves nothing was sent elsewhere."""

    def __init__(self, refusal: str) -> None:
        import http.server
        import threading

        status, code, message, extra = REFUSALS[refusal]
        body = (
            f'<?xml version="1.0" encoding="UTF-8"?>\n<Error><Code>{code}</Code>'
            f"<Message>{escape(message)}</Message>"
            f"{extra.format(bucket='synthetic-exports')}<RequestId>SYNTHETIC</RequestId></Error>"
        ).encode()
        requests: list[tuple[str, str, str]] = []
        self.requests = requests

        class _Handler(http.server.BaseHTTPRequestHandler):
            def _answer(self) -> None:
                requests.append((self.command, self.headers.get("Host", ""), self.path))
                self.send_response(status)
                self.send_header("x-amz-bucket-region", "eu-west-1")
                self.send_header("Content-Type", "application/xml")
                self.send_header("Content-Length", "0" if self.command == "HEAD" else str(len(body)))
                self.end_headers()
                if self.command != "HEAD":
                    self.wfile.write(body)

            do_GET = do_HEAD = _answer

            def log_message(self, *_: Any) -> None:
                return None

        self._server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    @property
    def endpoint(self) -> str:
        return f"127.0.0.1:{self._server.server_address[1]}"

    def __enter__(self) -> RefusingS3Server:
        self._thread.start()
        return self

    def __exit__(self, *_: Any) -> None:
        self._server.shutdown()
        self._server.server_close()
