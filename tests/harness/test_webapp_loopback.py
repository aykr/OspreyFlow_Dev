"""`DECISIONS.md` ruling R2: "in setup mode the harness binds to loopback only... and refuses any
non-loopback source." The bootstrap command's own `-p 127.0.0.1:7000:7000` (`harness/webapp.py`'s
own `_parse_args`, `--host` defaulting to `127.0.0.1`) is the first layer; this file proves the
second, application-level one — a real ASGI request whose own client address is not loopback,
refused before it reaches any route at all, not a unit test of `is_loopback` alone.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from harness.webapp import create_app
from harness.webapp_auth import is_loopback


def _app(tmp_path: Path):  # noqa: ANN201 - FastAPI's own app type, imported only for the fixture
    return create_app(config_path=tmp_path / "osprey.yaml")


@pytest.mark.parametrize("client_host", ["203.0.113.5", "10.0.0.7", "198.51.100.1"])
def test_a_request_from_a_non_loopback_address_is_refused(tmp_path: Path, client_host: str) -> None:
    client = TestClient(_app(tmp_path), client=(client_host, 51000))
    response = client.get("/api/config")
    assert response.status_code == 403
    assert "loopback" in response.text


@pytest.mark.parametrize("client_host", ["127.0.0.1", "::1"])
def test_a_request_from_a_loopback_address_is_admitted(tmp_path: Path, client_host: str) -> None:
    client = TestClient(_app(tmp_path), client=(client_host, 51000))
    response = client.get("/api/config")
    assert response.status_code == 200


def test_a_request_with_no_client_info_at_all_is_refused_not_trusted_by_default(
    tmp_path: Path,
) -> None:
    """The ASGI shape a raw TCP proxy or a misconfigured server can produce — `request.client` is
    `None`, not an address. `is_loopback`'s own docstring names this case; proven here against the
    real middleware rather than only against the helper function directly."""
    assert is_loopback(None) is False


@pytest.mark.parametrize(
    ("host", "expected"),
    [
        ("127.0.0.1", True),
        ("127.0.0.2", True),  # the whole 127.0.0.0/8 block is loopback, not only .1
        ("::1", True),
        ("0.0.0.0", False),  # noqa: S104 - asserting this is NOT treated as loopback, not binding it
        ("8.8.8.8", False),
        ("not-an-ip-at-all", False),
    ],
)
def test_is_loopback_classifies_by_real_ip_semantics_not_a_string_allowlist(
    host: str, expected: bool
) -> None:
    assert is_loopback(host) is expected
