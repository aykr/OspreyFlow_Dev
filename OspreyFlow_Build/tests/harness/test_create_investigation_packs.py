"""ADR-126 decision 2 (unit D1): the harness creates the seeded case with the packs its seeded
datasets carry. Its Author is the harness's own sign-in identity, as which no demo person signs in,
and its case holds HMP's custody links, so the case must say `[fibo, niem]` when HMP is seeded.

What a mistake here would do, and the case that catches it:

- a POST with no `domains` would leave the harness's case reading as POLE, so the Figures tab
  would hide the KYC card for a case holding HMP's accounts
  (`test_the_post_sends_the_union_of_the_seeded_datasets_packs`);
- a call site in `main` that did not hand `create_investigation` the seeded datasets would send
  nothing, whatever the function itself does (`test_the_call_site_hands_over_the_seeded_datasets`);
- a body sent without a JSON content type would be refused by the real Conduit, which the
  loopback server below refuses as it does
  (`test_the_body_is_json_and_the_server_refuses_it_otherwise`).

**A fixture that models refusals** (`CLAUDE.md` rule 15). The loopback server below is a real HTTP
server that the code under test reaches through `urllib`, as it does the deployment's. Like
Keycloak it refuses a token exchange with no `subject_token`; like the Conduit it refuses an
unknown pack, a body that is not JSON and a request without the exchanged bearer token.
"""

from __future__ import annotations

import ast
import json
import urllib.parse
from collections.abc import Iterator
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from typing import Any

import pytest
from harness import apply
from harness.apply import ApplyFailed, create_investigation
from harness.realm import CONDUIT_CLIENT_ID, VERIFY_SUBJECT

REALM = "osprey"
SECRET = "synthetic-secret"
OWN_TOKEN = "own-token-1"
EXCHANGED_TOKEN = "exchanged-token-1"
PACKS = {"fibo", "niem", "stix"}


@dataclass
class _Conduit:
    """What the loopback server saw."""

    url: str
    investigation_posts: list[dict[str, Any]] = field(default_factory=list)
    refused: list[str] = field(default_factory=list)
    token_requests: int = 0


def _handler(seen: _Conduit) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
            return

        def _reply(self, status: int, payload: dict[str, Any]) -> None:
            body = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _refuse(self, status: int, why: str) -> None:
            seen.refused.append(why)
            self._reply(status, {"error": why})

        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b""
            if self.path == f"/realms/{REALM}/protocol/openid-connect/token":
                seen.token_requests += 1
                self._token(urllib.parse.parse_qs(raw.decode()))
            elif self.path == "/v1/investigations":
                self._investigations(raw)
            else:
                self._refuse(404, "no such route")

        def _token(self, form: dict[str, list[str]]) -> None:
            def one(key: str) -> str | None:
                return form.get(key, [None])[0]

            if one("client_id") != CONDUIT_CLIENT_ID or one("client_secret") != SECRET:
                self._refuse(401, "invalid_client")
            elif one("grant_type") == "client_credentials":
                self._reply(200, {"access_token": OWN_TOKEN})
            elif one("grant_type") == "urn:ietf:params:oauth:grant-type:token-exchange":
                # RFC 8693 §2.1: `subject_token` is REQUIRED. Keycloak answers access_denied.
                if one("subject_token") != OWN_TOKEN or not one("subject_token_type"):
                    self._refuse(403, "access_denied")
                elif one("requested_subject") != VERIFY_SUBJECT:
                    self._refuse(403, "access_denied")
                else:
                    self._reply(200, {"access_token": EXCHANGED_TOKEN})
            else:
                self._refuse(400, "unsupported_grant_type")

        def _investigations(self, raw: bytes) -> None:
            if self.headers.get("Authorization") != f"Bearer {EXCHANGED_TOKEN}":
                self._refuse(401, "not signed in")
                return
            body: dict[str, Any] = {}
            if raw:
                if "application/json" not in (self.headers.get("Content-Type") or ""):
                    self._refuse(422, "a body that is not declared JSON")
                    return
                try:
                    parsed = json.loads(raw)
                except ValueError:
                    self._refuse(422, "a body that is not JSON")
                    return
                if not isinstance(parsed, dict):
                    self._refuse(422, "a body that is not an object")
                    return
                body = parsed
            domains = body.get("domains")
            if domains is not None and (
                not isinstance(domains, list)
                or not all(isinstance(d, str) and d in PACKS for d in domains)
            ):
                self._refuse(422, "an unknown pack")
                return
            seen.investigation_posts.append(body)
            self._reply(201, {"id": f"case-{len(seen.investigation_posts)}"})

    return Handler


@pytest.fixture
def conduit() -> Iterator[_Conduit]:
    seen = _Conduit(url="")
    server = ThreadingHTTPServer(("127.0.0.1", 0), _handler(seen))
    seen.url = f"http://127.0.0.1:{server.server_address[1]}"
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield seen
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _create(seen: _Conduit, **kwargs: Any) -> str:
    return create_investigation(seen.url, REALM, SECRET, seen.url, **kwargs)


def test_the_post_sends_the_union_of_the_seeded_datasets_packs(conduit: _Conduit) -> None:
    case_id = _create(conduit, datasets=["hmp", "fixture-corp", "scenarios"])

    assert case_id == "case-1"
    assert conduit.investigation_posts == [{"domains": ["fibo", "niem"]}]


def test_a_seed_of_no_packs_still_says_so(conduit: _Conduit) -> None:
    """`fixture-corp` and `scenarios` carry no packs: the case is chosen as POLE, not unchosen."""
    _create(conduit, datasets=["fixture-corp", "scenarios"])

    assert conduit.investigation_posts == [{"domains": []}]


def test_a_call_that_names_no_datasets_posts_no_body(conduit: _Conduit) -> None:
    """`test_sustained_load.py` calls it as before: nothing to choose, so nothing is sent."""
    _create(conduit)

    assert conduit.investigation_posts == [{}]
    assert conduit.refused == []


def test_the_body_is_json_and_the_server_refuses_it_otherwise(conduit: _Conduit) -> None:
    _create(conduit, datasets=["hmp"])
    assert conduit.refused == [], "the declared-JSON body was accepted"

    raw = urllib_post(conduit.url + "/v1/investigations", b'{"domains": ["fibo"]}', None)
    assert raw == 422 and conduit.refused == ["a body that is not declared JSON"]


def test_the_fixture_refuses_what_the_deployment_refuses(conduit: _Conduit) -> None:
    unknown = urllib_post(
        conduit.url + "/v1/investigations",
        b'{"domains": ["gone"]}',
        "application/json",
        bearer=EXCHANGED_TOKEN,
    )
    unsigned = urllib_post(
        conduit.url + "/v1/investigations", b"{}", "application/json", bearer="other"
    )

    assert (unknown, unsigned) == (422, 401)


def test_a_refused_post_is_reported_as_a_failed_seed(conduit: _Conduit) -> None:
    with pytest.raises(ApplyFailed, match="could not create an investigation"):
        create_investigation(conduit.url, REALM, "wrong-secret", conduit.url, datasets=["hmp"])


def test_an_unknown_seed_is_refused_by_name_before_any_request(conduit: _Conduit) -> None:
    """`domains_for` raises `KeyError`; left inside the request's `try` it would escape as a bare
    traceback (or be mistaken for a missing token field). It is refused first, naming the seed."""
    with pytest.raises(ApplyFailed, match="no-such-seed") as refused:
        _create(conduit, datasets=["hmp", "no-such-seed"])

    assert refused.value.stage == "seed"
    assert conduit.token_requests == 0 and conduit.investigation_posts == []


def test_the_call_site_hands_over_the_seeded_datasets() -> None:
    """The step in `main` that creates the seeded case, read as source: every call to
    `create_investigation` in `harness/apply.py` passes `datasets=`. A call without it posts no
    body, so the case would read as POLE whatever the function does."""
    source = Path(apply.__file__).read_text(encoding="utf-8")
    calls = [
        node
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "create_investigation"
    ]

    assert calls, "the seeding step no longer calls create_investigation"
    for call in calls:
        assert "datasets" in {k.arg for k in call.keywords}, ast.unparse(call)


def urllib_post(
    url: str, body: bytes, content_type: str | None, *, bearer: str | None = None
) -> int:
    import urllib.error
    import urllib.request

    headers = {"Authorization": f"Bearer {bearer or EXCHANGED_TOKEN}"}
    if content_type is not None:
        headers["Content-Type"] = content_type
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return int(response.status)
    except urllib.error.HTTPError as error:
        return error.code
