"""ADR-114 Amendment 41, against the real proxy: the Caddyfile `harness.site.render_caddyfile` renders
for a deployment that asks for the shared key, run by Caddy 2.11.4 itself (the version the product
pins, `harness.site.PROXY_IMAGE`), with the key file `harness.access_key` writes and a stand-in behind
each name that records what reaches it. The access-control test of every name (rule 4).

The stand-in is never the judge: every refusal below is Caddy's own. The hash is made by Caddy's own
`hash-password`, as the helper makes it on the server.

Needs a `caddy` 2.11 binary: `OSPREY_TEST_CADDY`, else `caddy` on the PATH; skipped, in words,
without one. `gate/B-proxy-*.raw.txt` has the runs, red and green.
"""

from __future__ import annotations

import http.server
import os
import shutil
import socket
import subprocess
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest
from harness import access_key
from harness.site import CERT_IN_PROXY, KEY_IN_PROXY, render_caddyfile

from schemas.deployment import OspreyConfig

HOST = "demo.gate.localhost"
NAMES = (HOST, f"id.{HOST}", f"bi.{HOST}")
KEY = "a long shared demonstration key"
CADDY = os.environ.get("OSPREY_TEST_CADDY") or shutil.which("caddy")

pytestmark = pytest.mark.skipif(
    CADDY is None, reason="no caddy binary: set OSPREY_TEST_CADDY to a Caddy 2.11 binary"
)


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@dataclass
class _Seen:
    method: str
    path: str
    authorization: str | None
    cookie: str | None


class _StandIn(http.server.ThreadingHTTPServer):
    seen: list[_Seen]


def _stand_in() -> _StandIn:
    class Handler(http.server.BaseHTTPRequestHandler):
        def _answer(self) -> None:
            server: _StandIn = self.server  # type: ignore[assignment]
            server.seen.append(_Seen(self.command, self.path, self.headers.get("Authorization"),
                                     self.headers.get("Cookie")))  # fmt: skip
            self.send_response(200)
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"ok")

        do_GET = do_POST = do_OPTIONS = _answer

        def log_message(self, *_args: object) -> None:
            pass

    server = _StandIn(("127.0.0.1", 0), Handler)
    server.seen = []
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


@dataclass
class _Proxy:
    port: int
    stand_in: _StandIn
    token: str

    def ask(self, name: str, path: str = "/", *, method: str = "GET",
            user: str | None = None, key: str | None = None,
            headers: dict[str, str] | None = None) -> tuple[int, dict[str, list[str]]]:  # fmt: skip
        """One request through the proxy by `curl`, as a browser sends it: the name in the TLS
        handshake and the `Host`, resolved to this machine. Returns the status and the headers."""
        argv = [
            "curl", "-sk", "-o", "/dev/null", "-D", "-", "--path-as-is", "-X", method,
            "--resolve", f"{name}:{self.port}:127.0.0.1", f"https://{name}:{self.port}{path}",
        ]  # fmt: skip
        if user is not None:
            argv += ["-u", f"{user}:{key}"]
        for field, value in (headers or {}).items():
            argv += ["-H", f"{field}: {value}"]
        out = subprocess.run(argv, capture_output=True, text=True, timeout=30, check=True).stdout
        lines = [line.strip() for line in out.splitlines() if line.strip()]
        status = int(lines[0].split()[1])
        fields: dict[str, list[str]] = {}
        for line in lines[1:]:
            field, _, value = line.partition(":")
            fields.setdefault(field.strip().lower(), []).append(value.strip())
        return status, fields


def _certificate(folder: Path) -> tuple[Path, Path]:
    cert, key = folder / "cert.pem", folder / "key.pem"
    subprocess.run(
        ["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
         "-keyout", str(key), "-out", str(cert), "-subj", f"/CN={HOST}",
         "-addext", "subjectAltName=" + ",".join(f"DNS:{n}" for n in NAMES)],
        capture_output=True, check=True,
    )  # fmt: skip
    return cert, key


def _hash(key: str) -> str:
    done = subprocess.run([str(CADDY), "hash-password", "--algorithm", "bcrypt"], input=key + "\n",
                          capture_output=True, text=True, check=True)  # fmt: skip
    return done.stdout.strip()


def _caddyfile(folder: Path, port: int, plain: int, stand_in: int, *, ask: bool = True) -> Path:
    """The rendered Caddyfile, with what the proxy's container gives it moved onto this machine:
    the certificate files, the key file, the two listening ports and the services behind it."""
    cert, key = _certificate(folder)
    config = OspreyConfig.model_validate({
        "profile": "small",
        "network": {"public_origin": f"https://{HOST}", "access_key": ask,
                    "tls": {"certificate": str(cert), "key": str(key)}},
        "reporting": {"superset": True},
    })  # fmt: skip
    text = render_caddyfile(config, doors=False)
    for old, new in (
        (CERT_IN_PROXY, str(cert)),
        (KEY_IN_PROXY, str(key)),
        (access_key.IN_PROXY, str(folder / access_key.ACCESS_KEY_FILE)),
        ("https_port 8443", f"https_port {port}"),
        ("http_port 8080", f"http_port {plain}"),
        (":8080 {", f":{plain} {{"),
        ("workspace:8080", f"127.0.0.1:{stand_in}"),
        ("keycloak:8080", f"127.0.0.1:{stand_in}"),
        ("superset:8088", f"127.0.0.1:{stand_in}"),
    ):
        text = text.replace(old, new)
    path = folder / "Caddyfile"
    path.write_text(text, encoding="utf-8")
    return path


def _run(caddyfile: Path, port: int) -> subprocess.Popen[bytes]:
    env = {**os.environ, "XDG_DATA_HOME": str(caddyfile.parent / "data"),
           "XDG_CONFIG_HOME": str(caddyfile.parent / "config")}  # fmt: skip
    process = subprocess.Popen([str(CADDY), "run", "--config", str(caddyfile), "--adapter", "caddyfile"],
                               env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)  # fmt: skip
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise AssertionError(process.stderr.read().decode() if process.stderr else "exited")
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.5).close()
            return process
        except OSError:
            time.sleep(0.2)
    process.kill()
    raise AssertionError("Caddy did not start listening")


@pytest.fixture
def proxy(tmp_path: Path) -> Iterator[_Proxy]:
    stand_in = _stand_in()
    port, plain = _free_port(), _free_port()
    caddyfile = _caddyfile(tmp_path, port, plain, stand_in.server_address[1])
    access_key.set_key(tmp_path, user="demo", ask=lambda _prompt: KEY, hasher=_hash)
    access_key.carry_into(tmp_path, tmp_path)
    token = access_key.pass_token(tmp_path)
    assert token is not None
    process = _run(caddyfile, port)
    try:
        yield _Proxy(port, stand_in, token)
    finally:
        process.kill()
        process.wait(timeout=10)
        stand_in.shutdown()


def _pass(proxy: _Proxy) -> dict[str, str]:
    return {"Cookie": f"{access_key.PASS_COOKIE}={proxy.token}"}


@pytest.mark.parametrize("name", NAMES)
def test_without_the_key_nothing_behind_the_proxy_answers(proxy: _Proxy, name: str) -> None:
    status, fields = proxy.ask(name, "/")
    assert status == 401
    assert fields["www-authenticate"][0].startswith("Basic")
    assert fields["x-robots-tag"] == ["noindex, nofollow"]
    assert proxy.stand_in.seen == []


@pytest.mark.parametrize("name", NAMES)
def test_a_wrong_key_or_user_is_refused(proxy: _Proxy, name: str) -> None:
    assert proxy.ask(name, "/", user="demo", key="not the shared key")[0] == 401
    assert proxy.ask(name, "/", user="someone", key=KEY)[0] == 401
    assert proxy.stand_in.seen == []


@pytest.mark.parametrize("name", NAMES)
def test_the_key_lets_a_browser_in_gives_it_the_pass_and_never_reaches_behind(
    proxy: _Proxy, name: str
) -> None:
    status, fields = proxy.ask(name, "/", user="demo", key=KEY)
    assert status == 200
    assert fields["x-robots-tag"] == ["noindex, nofollow"]
    (given,) = [c for c in fields["set-cookie"] if c.startswith(f"{access_key.PASS_COOKIE}=")]
    assert given == (f"{access_key.PASS_COOKIE}={proxy.token}; Domain={HOST}; Path=/; Secure; "
                     "HttpOnly; SameSite=Lax")  # fmt: skip
    (seen,) = proxy.stand_in.seen
    assert seen.authorization is None, "the key reached the service behind the proxy"


@pytest.mark.parametrize("name", NAMES)
def test_the_pass_lets_in_a_request_with_a_token_of_its_own(proxy: _Proxy, name: str) -> None:
    """The Glass's own API calls carry `Authorization: Bearer`, which a browser sends in place of
    the key; the pass lets them in, and their token reaches the service unchanged."""
    status, fields = proxy.ask(
        name, "/v1/x", headers={**_pass(proxy), "Authorization": "Bearer abc"}
    )
    assert status == 200 and fields["x-robots-tag"] == ["noindex, nofollow"]
    (seen,) = proxy.stand_in.seen
    assert seen.authorization == "Bearer abc"


@pytest.mark.parametrize("name", NAMES)
def test_a_pass_that_is_not_this_one_is_refused(proxy: _Proxy, name: str) -> None:
    other = {"Cookie": f"{access_key.PASS_COOKIE}={'x' * 43}"}
    assert proxy.ask(name, "/", headers=other)[0] == 401
    assert proxy.stand_in.seen == []


@pytest.mark.parametrize("name", NAMES)
def test_a_cors_preflight_is_answered_without_the_key_and_given_no_pass(
    proxy: _Proxy, name: str
) -> None:
    status, fields = proxy.ask(name, "/v1/x", method="OPTIONS")
    assert status == 200
    assert "set-cookie" not in fields
    assert fields["x-robots-tag"] == ["noindex, nofollow"]


@pytest.mark.parametrize(
    "path",
    [
        "/realms/osprey/protocol/openid-connect/token",
        "/realms/osprey/protocol/openid-connect/certs",
        "/realms/osprey/.well-known/openid-configuration",
    ],
)
def test_the_identity_providers_cross_origin_answers_go_without_the_key(
    proxy: _Proxy, path: str
) -> None:
    method = "POST" if path.endswith("/token") else "GET"
    status, fields = proxy.ask(f"id.{HOST}", path, method=method)
    assert status == 200 and fields["x-robots-tag"] == ["noindex, nofollow"]


OPEN = [
    (f"id.{HOST}", "POST", "/realms/osprey/protocol/openid-connect/token"),
    (f"id.{HOST}", "GET", "/realms/osprey/protocol/openid-connect/certs"),
    (f"id.{HOST}", "GET", "/realms/osprey/.well-known/openid-configuration"),
    *((name, "OPTIONS", "/v1/x") for name in NAMES),
]


@pytest.mark.parametrize(("name", "method", "path"), OPEN)
def test_the_open_answers_never_give_the_pass_for_an_unchecked_key(
    proxy: _Proxy, name: str, method: str, path: str
) -> None:
    """A request to an answer that goes without the key is not checked, whatever Basic credential it
    carries, so it is never given the pass for one; at the token endpoint the credential reaches
    Keycloak, since a client may sign in with Basic there."""
    status, fields = proxy.ask(name, path, method=method, user="demo", key="anything at all")
    assert status == 200
    assert "set-cookie" not in fields
    if path.endswith("/token"):
        (seen,) = proxy.stand_in.seen
        assert seen.authorization is not None


@pytest.mark.parametrize(
    "path",
    [
        "/realms/osprey/protocol/openid-connect/auth",
        "/realms/osprey/protocol/openid-connect/token/../auth",
        "/realms/master/protocol/openid-connect/token",
        "/admin/master/console/",
        "/realms/osprey/account/",
    ],
)
def test_the_sign_in_page_and_everything_else_on_the_identity_provider_asks(
    proxy: _Proxy, path: str
) -> None:
    assert proxy.ask(f"id.{HOST}", path)[0] == 401
    assert proxy.stand_in.seen == []


def test_without_its_key_file_the_proxy_does_not_start(tmp_path: Path) -> None:
    """Fails closed: a deployment that asks for the key and has none set answers nothing at all."""
    caddyfile = _caddyfile(tmp_path, _free_port(), _free_port(), 9)
    done = subprocess.run([str(CADDY), "validate", "--config", str(caddyfile), "--adapter", "caddyfile"],
                          capture_output=True, text=True)  # fmt: skip
    assert done.returncode != 0
    assert access_key.ACCESS_KEY_FILE in done.stdout + done.stderr


def test_a_deployment_that_does_not_ask_is_answered_as_before(tmp_path: Path) -> None:
    stand_in = _stand_in()
    port, plain = _free_port(), _free_port()
    process = _run(_caddyfile(tmp_path, port, plain, stand_in.server_address[1], ask=False), port)
    try:
        status, fields = _Proxy(port, stand_in, "").ask(HOST, "/")
        assert status == 200
        assert "x-robots-tag" not in fields and "set-cookie" not in fields
    finally:
        process.kill()
        process.wait(timeout=10)
        stand_in.shutdown()
