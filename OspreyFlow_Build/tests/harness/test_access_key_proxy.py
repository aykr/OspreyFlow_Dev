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
OPEN_PATHS = {
    "/realms/osprey/protocol/openid-connect/token",
    "/realms/osprey/protocol/openid-connect/certs",
    "/realms/osprey/.well-known/openid-configuration",
}
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
    folder: Path | None = None

    body: bytes = b""

    def body_file(self) -> Path:
        return Path(os.environ.get("TMPDIR", "/tmp")) / f"osprey-proxy-body-{self.port}"

    def ask(self, name: str, path: str = "/", *, method: str = "GET",
            user: str | None = None, key: str | None = None,
            headers: dict[str, str] | None = None) -> tuple[int, dict[str, list[str]]]:  # fmt: skip
        """One request through the proxy by `curl`, as a browser sends it: the name in the TLS
        handshake and the `Host`, resolved to this machine. Returns the status and the headers."""
        argv = [
            "curl", "-sk", "-o", str(self.body_file()), "-D", "-", "--path-as-is", "-X", method,
            "--resolve", f"{name}:{self.port}:127.0.0.1", f"https://{name}:{self.port}{path}",
        ]  # fmt: skip
        if user is not None:
            argv += ["-u", f"{user}:{key}"]
        for field, value in (headers or {}).items():
            argv += ["-H", f"{field}: {value}"]
        out = subprocess.run(argv, capture_output=True, text=True, timeout=30, check=True).stdout
        self.body = self.body_file().read_bytes()
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
    log = (caddyfile.parent / "caddy.log").open("ab")
    process = subprocess.Popen([str(CADDY), "run", "--config", str(caddyfile), "--adapter", "caddyfile"],
                               env=env, stdout=subprocess.DEVNULL, stderr=log)  # fmt: skip
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise AssertionError((caddyfile.parent / "caddy.log").read_text(errors="replace"))
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.5).close()
            return process
        except OSError:
            time.sleep(0.2)
    process.kill()
    raise AssertionError("Caddy did not start listening")


_RUNNING: dict[Path, subprocess.Popen[bytes]] = {}


def _run_again(folder: Path, port: int) -> subprocess.Popen[bytes]:
    """The proxy restarted on the same files, as `ospreyflow apply` restarts it."""
    running = _RUNNING.pop(folder)
    running.kill()
    running.wait(timeout=10)
    process = _run(folder / "Caddyfile", port)
    _RUNNING[folder] = process
    return process


@pytest.fixture
def proxy(tmp_path: Path) -> Iterator[_Proxy]:
    stand_in = _stand_in()
    port, plain = _free_port(), _free_port()
    caddyfile = _caddyfile(tmp_path, port, plain, stand_in.server_address[1])
    access_key.set_key(tmp_path, user="demo", ask=lambda _prompt: KEY, hasher=_hash)
    access_key.carry_into(tmp_path, tmp_path)
    token = access_key.pass_token(tmp_path)
    assert token is not None
    _RUNNING[tmp_path] = _run(caddyfile, port)
    try:
        yield _Proxy(port, stand_in, token, tmp_path)
    finally:
        process = _RUNNING.pop(tmp_path, None)
        if process is not None:
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
def test_a_wrong_key_or_user_is_refused_and_given_no_pass(proxy: _Proxy, name: str) -> None:
    for user, key in (("demo", "not the shared key"), ("someone", KEY), (None, None)):
        status, fields = proxy.ask(name, "/", user=user, key=key)
        assert status == 401
        assert "set-cookie" not in fields
    assert proxy.stand_in.seen == []


@pytest.mark.parametrize("name", NAMES)
def test_a_refusal_says_nothing_more(proxy: _Proxy, name: str) -> None:
    """The 401 has no body and a realm that names only the product: the box asks, and nothing of
    the deployment, its services or why is told. (Caddy's own `Server: Caddy` stays: a refusal is
    written by its error path, which a deferred header deletion does not reach.)"""
    status, fields = proxy.ask(name, "/v1/anything", user="demo", key="not the shared key")
    assert status == 401
    assert proxy.body == b""
    assert fields["www-authenticate"] == ['Basic realm="OspreyFlow"']
    assert set(fields) <= {"www-authenticate", "x-robots-tag", "server", "alt-svc", "date",
                           "content-length"}, fields  # fmt: skip


def test_every_attempt_is_logged_and_the_log_holds_no_key_and_no_pass(proxy: _Proxy) -> None:
    """Each answer, a refusal included, is in the proxy's own log (`docker compose logs proxy`),
    with Caddy's redaction of `Authorization` and `Cookie`: never the key, nor the pass."""
    assert proxy.folder is not None
    proxy.ask(HOST, "/attempt", user="demo", key="a wrong guess at the key")
    proxy.ask(HOST, "/with-pass", headers=_pass(proxy))
    proxy.ask(HOST, "/with-key", user="demo", key=KEY)
    deadline = time.monotonic() + 5
    log = ""
    while time.monotonic() < deadline and "/with-key" not in log:
        log = (proxy.folder / "caddy.log").read_text(errors="replace")
        time.sleep(0.1)
    attempt = [line for line in log.splitlines() if '"/attempt"' in line]
    assert attempt and '"status":401' in attempt[0]
    for secret in (KEY, "a wrong guess at the key", proxy.token):
        assert secret not in log
    import base64

    assert base64.b64encode(f"demo:{KEY}".encode()).decode() not in log


@pytest.mark.parametrize("name", NAMES)
def test_the_key_lets_a_browser_in_gives_it_the_pass_and_never_reaches_behind(
    proxy: _Proxy, name: str
) -> None:
    status, fields = proxy.ask(name, "/", user="demo", key=KEY)
    assert status == 200
    assert fields["x-robots-tag"] == ["noindex, nofollow"]
    (given,) = [c for c in fields["set-cookie"] if c.startswith(f"{access_key.PASS_COOKIE}=")]
    # Host-only (no Domain): it is sent back to this one name alone, never to another subdomain of
    # the deployment's domain; each of the three names asks once. Eight hours at most.
    assert given == (f"{access_key.PASS_COOKIE}={proxy.token}; Path=/; Max-Age=28800; Secure; "
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
def test_a_forged_pass_is_refused(proxy: _Proxy, name: str) -> None:
    forged = [
        f"{access_key.PASS_COOKIE}={'x' * 43}",
        f"{access_key.PASS_COOKIE}=",
        f"{access_key.PASS_COOKIE}={proxy.token[:-1]}",
        f"other={proxy.token}",
    ]
    for cookie in forged:
        assert proxy.ask(name, "/", headers={"Cookie": cookie})[0] == 401, cookie
    assert proxy.stand_in.seen == []


def test_setting_the_key_again_refuses_the_old_pass_and_the_old_key(proxy: _Proxy, tmp_path: Path) -> None:
    """The helper and `ospreyflow apply`: a new hash and a new pass, and the proxy restarted with
    them; the browser holding the old pass, or the old key, is asked again."""
    old = proxy.token
    assert proxy.ask(HOST, "/", headers=_pass(proxy))[0] == 200
    access_key.set_key(tmp_path, user="demo", ask=lambda _prompt: KEY + " renewed", hasher=_hash)
    access_key.carry_into(tmp_path, tmp_path)
    access_key.settle(tmp_path)
    new = access_key.pass_token(tmp_path)
    assert new is not None and new != old
    caddy = _run_again(tmp_path, proxy.port)
    try:
        assert proxy.ask(HOST, "/", headers={"Cookie": f"{access_key.PASS_COOKIE}={old}"})[0] == 401
        assert proxy.ask(HOST, "/", user="demo", key=KEY)[0] == 401
        assert proxy.ask(HOST, "/", user="demo", key=KEY + " renewed")[0] == 200
        assert proxy.ask(HOST, "/", headers={"Cookie": f"{access_key.PASS_COOKIE}={new}"})[0] == 200
    finally:
        caddy.kill()
        caddy.wait(timeout=10)


PREFLIGHT = {"Origin": f"https://{HOST}", "Access-Control-Request-Method": "POST"}


@pytest.mark.parametrize("name", NAMES)
def test_a_cors_preflight_is_answered_without_the_key_and_given_no_pass(
    proxy: _Proxy, name: str
) -> None:
    status, fields = proxy.ask(name, "/v1/x", method="OPTIONS", headers=PREFLIGHT)
    assert status == 200
    assert "set-cookie" not in fields
    assert fields["x-robots-tag"] == ["noindex, nofollow"]


@pytest.mark.parametrize("name", NAMES)
def test_an_options_that_is_not_a_preflight_asks_for_the_key(proxy: _Proxy, name: str) -> None:
    assert proxy.ask(name, "/v1/x", method="OPTIONS")[0] == 401
    assert proxy.stand_in.seen == []


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
    Keycloak never: no Basic credential, of any client, passes the proxy."""
    headers = PREFLIGHT if method == "OPTIONS" else None
    status, fields = proxy.ask(name, path, method=method, user="demo", key="anything at all",
                               headers=headers)  # fmt: skip
    assert status == 200
    assert "set-cookie" not in fields
    (seen,) = proxy.stand_in.seen
    assert seen.authorization is None, "a Basic credential reached the service behind the proxy"


@pytest.mark.parametrize("name", NAMES)
@pytest.mark.parametrize("path", ["/", "/realms/osprey/protocol/openid-connect/auth", "/v1/x"])
def test_a_browser_that_has_answered_never_sends_the_key_behind(proxy: _Proxy, name: str, path: str) -> None:
    """After the first answer a browser sends the pass and the key together with every request;
    the key is taken off, whatever the scheme's case, on every name and path."""
    import base64

    credential = base64.b64encode(f"demo:{KEY}".encode()).decode()
    for scheme in ("Basic", "basic", "BASIC"):
        headers = {**_pass(proxy), "Authorization": f"{scheme} {credential}"}
        assert proxy.ask(name, path, headers=headers)[0] == 200
    assert [seen.authorization for seen in proxy.stand_in.seen] == [None, None, None]


@pytest.mark.parametrize("name", NAMES)
def test_a_lower_case_scheme_is_checked_and_taken_off_like_any_other(proxy: _Proxy, name: str) -> None:
    import base64

    for key, expected in (("not the shared key", 401), (KEY, 200)):
        credential = base64.b64encode(f"demo:{key}".encode()).decode()
        assert proxy.ask(name, "/", headers={"Authorization": f"basic {credential}"})[0] == expected
    assert [seen.authorization for seen in proxy.stand_in.seen] == [None]


@pytest.mark.parametrize(
    "path",
    [
        "/realms/osprey/protocol/openid-connect/auth%2F..%2Ftoken",
        "/realms/osprey/protocol/openid-connect/%2e%2e/openid-connect/auth",
        "/realms/osprey/protocol/openid-connect/token;/../auth",
        "/realms/osprey/protocol/openid-connect/auth%2Ftoken",
        "/REALMS/osprey/protocol/openid-connect/auth",
        "/realms/osprey/protocol/openid-connect/token/../auth",
    ],
)
def test_an_encoded_or_disguised_path_never_reaches_the_sign_in_page_without_the_key(
    proxy: _Proxy, path: str
) -> None:
    """Caddy matches the cleaned path; whatever it lets through as an open answer must reach the
    identity provider as that open answer itself, never another page."""
    status, _fields = proxy.ask(f"id.{HOST}", path)
    if status != 401:
        (seen,) = proxy.stand_in.seen
        assert seen.path in OPEN_PATHS, (path, seen.path)


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
