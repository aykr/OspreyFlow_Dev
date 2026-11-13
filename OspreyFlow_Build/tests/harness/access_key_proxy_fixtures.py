"""The real proxy for the shared key's tests (ADR-114 Amendment 41): the Caddyfile
`harness.site.render_caddyfile` renders for a deployment that asks for the shared key, run by a local
Caddy 2.11 (the version the product pins, `harness.site.PROXY_IMAGE`), with the key file
`harness.access_key` writes and a stand-in behind each name that records what reaches it.

Shared, as `tls_fixtures.py` is, by `test_access_key_proxy.py` (the access-control test of every name)
and admin's `test_refresh_silent_round_through_the_key.py` (ADR-050 Amendment 3, point 4), which until
13 November 2026 imported it from the other's test file (CARRIES; POST_051's step B).

Needs a `caddy` 2.11 binary: `OSPREY_TEST_CADDY`, else `caddy` on the PATH. A module using `proxy`
sets `pytestmark = NEEDS_CADDY` and imports `proxy` by name (the fixture).
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

#: Each module using the fixture sets `pytestmark = NEEDS_CADDY`: skipped, in words, without the binary.
NEEDS_CADDY = pytest.mark.skipif(
    CADDY is None, reason="no caddy binary: set OSPREY_TEST_CADDY to a Caddy 2.11 binary"
)


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@dataclass
class Seen:
    method: str
    path: str
    authorization: str | None
    cookie: str | None


class StandIn(http.server.ThreadingHTTPServer):
    seen: list[Seen]


def stand_in_server() -> StandIn:
    class Handler(http.server.BaseHTTPRequestHandler):
        def _answer(self) -> None:
            server: StandIn = self.server  # type: ignore[assignment]
            server.seen.append(Seen(self.command, self.path, self.headers.get("Authorization"),
                                     self.headers.get("Cookie")))  # fmt: skip
            self.send_response(200)
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"ok")

        do_GET = do_POST = do_OPTIONS = _answer

        def log_message(self, *_args: object) -> None:
            pass

    server = StandIn(("127.0.0.1", 0), Handler)
    server.seen = []
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


@dataclass
class Proxy:
    port: int
    stand_in: StandIn
    token: str
    folder: Path | None = None

    body: bytes = b""

    def body_file(self) -> Path:
        return Path(os.environ.get("TMPDIR", "/tmp")) / f"osprey-proxy-body-{self.port}"

    def ask(self, name: str, path: str = "/", *, method: str = "GET",
            user: str | None = None, key: str | None = None,
            headers: dict[str, str] | None = None,
            jar: Path | None = None) -> tuple[int, dict[str, list[str]]]:  # fmt: skip
        """One request through the proxy by `curl`, as a browser sends it: the name in the TLS
        handshake and the `Host`, resolved to this machine. Returns the status and the headers."""
        argv = [
            "curl", "-sk", "-o", str(self.body_file()), "-D", "-", "--path-as-is", "-X", method,
            "--resolve", f"{name}:{self.port}:127.0.0.1", f"https://{name}:{self.port}{path}",
        ]  # fmt: skip
        if user is not None:
            argv += ["-u", f"{user}:{key}"]
        if jar is not None:
            # curl's own cookie engine, which keeps and sends cookies by a browser's rules
            # (RFC 6265 domain matching): the pass reaches a name only as a browser would send it.
            argv += ["-b", str(jar), "-c", str(jar)]
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


def certificate(folder: Path) -> tuple[Path, Path]:
    cert, key = folder / "cert.pem", folder / "key.pem"
    subprocess.run(
        ["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
         "-keyout", str(key), "-out", str(cert), "-subj", f"/CN={HOST}",
         "-addext", "subjectAltName=" + ",".join(f"DNS:{n}" for n in NAMES)],
        capture_output=True, check=True,
    )  # fmt: skip
    return cert, key


def hash_key(key: str) -> str:
    done = subprocess.run([str(CADDY), "hash-password", "--algorithm", "bcrypt"], input=key + "\n",
                          capture_output=True, text=True, check=True)  # fmt: skip
    return done.stdout.strip()


def write_caddyfile(folder: Path, port: int, plain: int, stand_in: int, *, ask: bool = True) -> Path:
    """The rendered Caddyfile, with what the proxy's container gives it moved onto this machine:
    the certificate files, the key file, the two listening ports and the services behind it."""
    cert, key = certificate(folder)
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


def run_caddy(caddyfile: Path, port: int) -> subprocess.Popen[bytes]:
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


RUNNING: dict[Path, subprocess.Popen[bytes]] = {}


def run_again(folder: Path, port: int) -> subprocess.Popen[bytes]:
    """The proxy restarted on the same files, as `ospreyflow apply` restarts it."""
    running = RUNNING.pop(folder)
    running.kill()
    running.wait(timeout=10)
    process = run_caddy(folder / "Caddyfile", port)
    RUNNING[folder] = process
    return process


@pytest.fixture
def proxy(tmp_path: Path) -> Iterator[Proxy]:
    stand_in = stand_in_server()
    port, plain = free_port(), free_port()
    caddyfile = write_caddyfile(tmp_path, port, plain, stand_in.server_address[1])
    access_key.set_key(tmp_path, user="demo", ask=lambda _prompt: KEY, hasher=hash_key)
    access_key.carry_into(tmp_path, tmp_path)
    token = access_key.pass_token(tmp_path)
    assert token is not None
    RUNNING[tmp_path] = run_caddy(caddyfile, port)
    try:
        yield Proxy(port, stand_in, token, tmp_path)
    finally:
        process = RUNNING.pop(tmp_path, None)
        if process is not None:
            process.kill()
            process.wait(timeout=10)
        stand_in.shutdown()


def pass_cookie(proxy: Proxy) -> dict[str, str]:
    return {"Cookie": f"{access_key.PASS_COOKIE}={proxy.token}"}
