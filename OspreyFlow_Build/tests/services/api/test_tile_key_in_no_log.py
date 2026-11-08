"""A map key in no log record, on the real fetch path (`06_DECISIONS.md` ADR-147 decision 2;
rule 15's second worked example: the stand-in refuses as a real provider does). A provider takes its
key in the tile URL's query, so anything that logs a URL logs the key: httpx's own INFO line for
every request, and an `HTTPStatusError`'s message ("… for url '…?key=…'") when the provider refuses.
A loopback server answers 200 with a tile, and 403 or 500 as a provider refusing a wrong or revoked
key does; the real `_http_get`, the real tile route and the real logger run, and no record, nor any
traceback a handler would print, carries the key. Synthetic (rule 9): a loopback address, a planted
key, no tile from anyone."""

from __future__ import annotations

import logging
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from services.api.app import app, get_principal
from services.api.map_admin import InMemoryMapAdminAudit, MapAdmin, MapKeyFile, MapSettingsFile

from schemas.domain import Principal
from schemas.mapconfig import MapConfig

PLANTED = "k-PLANTED-log-key-M3N8-do-not-leak"
PNG = b"\x89PNG\r\n\x1a\n synthetic tile"
ADMIN = Principal(id="admin-1", clearance="OFFICIAL", org_unit="u", roles=["osprey-admin"])


class _Provider(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 - the stdlib's name
        status = 403 if "/9/" in self.path else 500 if "/8/" in self.path else 200
        self.send_response(status)
        self.send_header("Content-Type", "image/png")
        self.end_headers()
        self.wfile.write(PNG if status == 200 else b"refused")

    def log_message(self, *_args: object) -> None:  # the server's own log is not the Conduit's
        pass


@pytest.fixture
def provider_port() -> Iterator[int]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Provider)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server.server_address[1]
    server.shutdown()


@pytest.fixture
def client(tmp_path: Path, provider_port: int) -> Iterator[TestClient]:
    installed = MapConfig.model_validate({
        "default": "osm-local",
        "providers": [
            {"id": "osm-local", "label": "OSM", "kind": "vector",
             "source": "file:///data/tiles/gb.pmtiles", "attribution": "© OSM contributors",
             "licence": {"id": "ODbL-1.0", "redistributable": True, "client_scope": "open"}},
            {"id": "hosted", "label": "Hosted", "kind": "raster",
             "source": f"http://127.0.0.1:{provider_port}/{{z}}/{{x}}/{{y}}.png?key={{credential}}",
             "proxy": "required", "attribution": "Example",
             "licence": {"id": "example", "redistributable": False,
                         "client_scope": "per-deployment"}},
        ],
    })  # fmt: skip
    admin = MapAdmin(
        installed=installed, settings_file=MapSettingsFile(tmp_path), key_file=MapKeyFile(tmp_path),
        audit=InMemoryMapAdminAudit(), tiles_root=tmp_path,
    )  # fmt: skip
    import asyncio

    asyncio.run(admin.set_key("admin-1", "hosted", SecretStr(PLANTED)))
    app.state.map_admin = admin
    app.state.tile_cache_storage = None
    app.dependency_overrides[get_principal] = lambda: ADMIN
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()
    del app.state.map_admin


def _everything_logged(caplog: pytest.LogCaptureFixture) -> str:
    formatter = logging.Formatter()
    return "\n".join(formatter.format(r) for r in caplog.records)


def test_a_tile_fetched_logs_its_request_without_the_key(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    answer = client.get("/v1/map/tiles/hosted/1/2/3")
    assert answer.status_code == 200 and answer.content == PNG
    logged = _everything_logged(caplog)
    assert "127.0.0.1" in logged  # the request is still logged, its address without the query
    assert PLANTED not in logged


@pytest.mark.parametrize(("z", "status"), [(9, 403), (8, 500)])
def test_a_provider_that_refuses_is_said_in_fixed_words_and_no_record_carries_the_key(
    client: TestClient, caplog: pytest.LogCaptureFixture, z: int, status: int
) -> None:
    caplog.set_level(logging.DEBUG)
    answer = client.get(f"/v1/map/tiles/hosted/{z}/2/3")
    assert answer.status_code == 502
    assert answer.json()["detail"] == (
        f"The map provider 'hosted' refused the tile (HTTP {status}). If it was refused for its "
        "key, set the key again in Admin › Maps."
    )
    assert PLANTED not in answer.text and "127.0.0.1" not in answer.text
    assert PLANTED not in _everything_logged(caplog)


def test_an_unset_environment_key_is_said_in_words(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ADR-147 decision 2: a provider that needs a key and holds neither answers 503 in words; an
    installer's `env:` reference to a variable that is not set is that case too."""
    monkeypatch.delenv("UNSET_MAP_KEY_FOR_TEST", raising=False)
    installed = MapConfig.model_validate({
        "default": "env-keyed",
        "providers": [{"id": "env-keyed", "label": "Env", "kind": "raster",
                       "source": "http://127.0.0.1:9/{z}/{x}/{y}?key={credential}",
                       "credential": "env:UNSET_MAP_KEY_FOR_TEST", "proxy": "required",
                       "attribution": "E", "licence": {"id": "e", "redistributable": False,
                                                       "client_scope": "per-deployment"}}],
    })  # fmt: skip
    app.state.map_admin = MapAdmin(
        installed=installed, settings_file=MapSettingsFile(tmp_path), key_file=MapKeyFile(tmp_path),
        audit=InMemoryMapAdminAudit(), tiles_root=tmp_path,
    )  # fmt: skip
    app.state.tile_cache_storage = None
    app.dependency_overrides[get_principal] = lambda: ADMIN
    try:
        answer = TestClient(app, raise_server_exceptions=False).get("/v1/map/tiles/env-keyed/1/2/3")
    finally:
        app.dependency_overrides.clear()
        del app.state.map_admin
    assert answer.status_code == 503 and "UNSET_MAP_KEY_FOR_TEST" not in answer.text
    assert "needs a key" in answer.json()["detail"]
