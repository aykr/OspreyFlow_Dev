"""The organisation's own certificate, served by the real Caddy (ADR-114 Amendment 33 decision 3).

Every case runs the pinned image (`harness.site.PROXY_IMAGE`) with the Caddyfile the renderer
writes and the user the compose file names, the certificate and key mounted where the compose file
mounts them, and a real TLS client (Python's `ssl`) that trusts only a throwaway CA made for the
test (`tls_fixtures.py`). Caddy's 8443 is published on a free port of 127.0.0.1; nothing here binds
80 or 443 of this machine.

Rule 15 (a fixture models refusals): Caddy is the fixture for what a certificate check must refuse.
It refuses to start with a key that does not match its certificate, and the client refuses a name
the certificate does not cover — both measured here, with the same files `harness.tls_check` is
given in `test_tls_check.py::test_every_pair_caddy_refuses_the_check_refuses_too`.

What a mistake would do, and the case that catches it:
- a name served with Caddy's own certificate, or with none —
  `test_caddy_serves_the_given_certificate_for_each_name`;
- a bad key let through to a proxy that never starts —
  `test_caddy_refuses_to_start_with_a_key_that_does_not_match`;
- a name outside the certificate trusted —
  `test_a_client_refuses_a_name_the_certificate_does_not_cover`;
- Caddy calling out (ACME, OCSP) from a server with no route out —
  `test_caddy_with_its_own_certificate_starts_and_serves_with_no_route_out`.
"""

from __future__ import annotations

import os
import socket
import ssl
import uuid
from pathlib import Path
from typing import Any

import pytest
import yaml
from harness.render import render

from schemas.deployment import OspreyConfig

from .tls_fixtures import (
    HOST,
    NAMES,
    caddy,
    docker,
    wait_until_healthy,
    wait_until_stopped,
    write_set,
)


def _resolver(_image: object) -> str:
    return "sha256:" + "0" * 64


def _rendered(files: Any, **network: Any) -> tuple[str, dict[str, Any]]:
    """The Caddyfile and the proxy's compose service for a self-contained Small whose certificate
    is `files` (dashboards on, so all three names are served)."""
    config = OspreyConfig.model_validate({
        "profile": "small",
        "network": {"public_origin": f"https://{HOST}",
                    "tls": {"certificate": str(files.certificate), "key": str(files.key),
                            "ca": str(files.ca)}, **network},
        "reporting": {"sync": True, "superset": True},
    })  # fmt: skip
    artefacts = render(config, resolver=_resolver).artefacts
    proxy = yaml.safe_load(artefacts["compose.yaml"])["services"]["proxy"]
    return artefacts["Caddyfile"], proxy


def _user(proxy: dict[str, Any]) -> str:
    """The compose file's `user`, with the account that owns the key, as `apply` writes it."""
    return (
        str(proxy["user"])
        .replace("${OSPREY_PROXY_UID:?}", str(os.getuid()))
        .replace("${OSPREY_PROXY_GID:?}", str(os.getgid()))
    )


def _handshake(port: int, name: str, ca: Path) -> tuple[str, bytes]:
    """A TLS client that trusts only `ca`, asking for `name`: the certificate's subject and the
    status line Caddy answers with."""
    context = ssl.create_default_context(cafile=str(ca))
    with socket.create_connection(("127.0.0.1", port), timeout=10) as raw:
        with context.wrap_socket(raw, server_hostname=name) as tls:
            subject = dict(item[0] for item in tls.getpeercert()["subject"])  # type: ignore[index]
            tls.sendall(f"GET / HTTP/1.1\r\nHost: {name}\r\nConnection: close\r\n\r\n".encode())
            return str(subject["commonName"]), tls.recv(64).split(b"\r\n")[0]


def test_caddy_serves_the_given_certificate_for_each_name(tmp_path: Path) -> None:
    files = write_set(tmp_path / "tls")
    caddyfile, proxy = _rendered(files)
    with caddy(caddyfile, files, tmp_path, user=_user(proxy)) as running:
        assert wait_until_healthy(running), running.logs()[-1500:]
        assert running.https_port is not None
        for name in NAMES:
            subject, status = _handshake(running.https_port, name, files.ca)
            # The organisation's certificate (its subject is the host), and Caddy routing the name
            # to its service, which is not running in this test (so 502, not a TLS failure).
            assert subject == HOST
            assert status == b"HTTP/1.1 502 Bad Gateway", status
        logs = running.logs()
        assert "obtaining certificate" not in logs and "acme" not in logs.lower()


@pytest.mark.parametrize("problem", ["mismatched", "encrypted"])
def test_caddy_refuses_to_start_with_a_key_that_does_not_match(
    tmp_path: Path, problem: str
) -> None:
    """The refusal `harness.tls_check` must make before anything starts, measured: Caddy exits
    rather than serve a key that does not match its certificate, or one it cannot read."""
    files = write_set(
        tmp_path / "tls",
        mismatched_key=problem == "mismatched",
        password=b"not-given" if problem == "encrypted" else None,
    )
    caddyfile, proxy = _rendered(files)
    with caddy(caddyfile, files, tmp_path, user=_user(proxy)) as running:
        assert wait_until_stopped(running), "Caddy kept running with a bad key"
        logs = running.logs()
        assert "loading certificates" in logs or "private key" in logs, logs[-1500:]


def test_a_client_refuses_a_name_the_certificate_does_not_cover(tmp_path: Path) -> None:
    """A certificate for the host and `id.` alone, with dashboards on: Caddy still starts (it does
    not check names), and a real client refuses `bi.` — so the check has to (Amendment 33's
    `test_a_certificate_missing_id_or_bi_is_refused_naming_it`)."""
    files = write_set(tmp_path / "tls", names=(HOST, f"id.{HOST}"))
    caddyfile, proxy = _rendered(files)
    with caddy(caddyfile, files, tmp_path, user=_user(proxy)) as running:
        assert wait_until_healthy(running), running.logs()[-1500:]
        assert running.https_port is not None
        assert _handshake(running.https_port, f"id.{HOST}", files.ca)[0] == HOST
        with pytest.raises(ssl.SSLError):
            _handshake(running.https_port, f"bi.{HOST}", files.ca)


def test_caddy_with_its_own_certificate_starts_and_serves_with_no_route_out(tmp_path: Path) -> None:
    """On a Docker network with no route out, with a certificate that names an OCSP responder:
    Caddy becomes healthy and serves the name over TLS, and its log shows no certificate obtained,
    no ACME and no OCSP request (measured: without `ocsp_stapling off` Caddy logs "stapling OCSP"
    for this certificate, and without `auto_https off` it enables its HTTP-to-HTTPS redirects)."""
    files = write_set(tmp_path / "tls", ocsp="http://ocsp.example.invalid/")
    caddyfile, proxy = _rendered(files)
    network = f"osprey-test-noroute-{uuid.uuid4().hex[:8]}"
    docker("network", "create", "--internal", network)
    try:
        with caddy(caddyfile, files, tmp_path, user=_user(proxy), network=network,
                   loopback_names=NAMES) as running:  # fmt: skip
            assert wait_until_healthy(running), running.logs()[-1500:]
            # The name answers over TLS inside the container (busybox wget: TLS, no verification;
            # the verification is the case above).
            served = docker(
                "exec", running.name, "sh", "-c",
                f"wget -S -q -O /dev/null --no-check-certificate https://{HOST}:8443/ 2>&1; true",
                check=False,
            )  # fmt: skip
            said = served.stdout + served.stderr
            assert "502" in said or "Bad Gateway" in said, said
            logs = running.logs().lower()
            for call in ("obtaining certificate", "acme", "stapling ocsp", "ocsp request",
                         "enabling automatic http->https redirects"):  # fmt: skip
                assert call not in logs, f"{call!r} in Caddy's log:\n{logs[-2000:]}"
    finally:
        docker("network", "rm", network, check=False)


def test_port_80_only_redirects_against_caddy(tmp_path: Path) -> None:
    """`redirect_http: true`: a name's plain-HTTP request is answered with a 308 to its https://
    address, never proxied; an unknown name gets 404; the health answer stays."""
    files = write_set(tmp_path / "tls")
    caddyfile, proxy = _rendered(files, redirect_http=True)
    with caddy(caddyfile, files, tmp_path, user=_user(proxy)) as running:
        assert wait_until_healthy(running), running.logs()[-1500:]
        for host, first in ((f"id.{HOST}", "HTTP/1.0 308"), ("elsewhere.example", "HTTP/1.0 404")):
            head = f"GET /realms/osprey HTTP/1.0\\r\\nHost: {host}\\r\\n\\r\\n"
            answer = docker(
                "exec", running.name, "sh", "-c", f"printf '{head}' | nc 127.0.0.1 8080"
            ).stdout  # fmt: skip
            assert answer.startswith(first), answer[:300]
            if first.endswith("308"):
                assert f"Location: https://{host}/realms/osprey" in answer, answer[:300]
