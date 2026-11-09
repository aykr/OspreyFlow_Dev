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
        if "/7/" in self.path:  # a provider answering far more than any tile
            self.wfile.write(PNG + b"x" * (5 * 1024 * 1024))
            return
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


# --- The independent review's must-fix 3: a key outside the query ---------------------------------


@pytest.mark.parametrize(
    "source",
    ["https://tiles.example.test/{credential}/{z}/{x}/{y}.png",
     "https://tiles.example.test:{credential}/{z}/{x}/{y}.png",
     "https://{credential}.example.test/{z}/{x}/{y}.png",
     "https://tiles.example.test/{z}/{x}/{y}.png#{credential}"],
)  # fmt: skip
def test_a_key_is_taken_in_the_query_alone(source: str) -> None:
    """`{credential}` anywhere but the query would put the key where a log keeps it (a path, a
    port) or where a resolver sends it (a host), so no provider, `osprey.yaml`'s included, may."""
    with pytest.raises(ValueError, match="query"):
        MapConfig.model_validate({"default": "p", "providers": [{
            "id": "p", "label": "P", "kind": "raster", "source": source, "proxy": "required",
            "attribution": "E", "licence": {"id": "e", "redistributable": False,
                                            "client_scope": "per-deployment"}}]})  # fmt: skip


async def test_a_secret_in_a_url_s_path_reaches_no_log_record(
    provider_port: int, caplog: pytest.LogCaptureFixture
) -> None:
    """The real fetch and the real loggers (`httpx`, and `httpcore`'s own `connection` and `http11`,
    each its own logger): whatever a URL carries past its host is not logged."""
    from services.api.tile_proxy import _http_get

    caplog.set_level(logging.DEBUG)
    await _http_get(f"http://127.0.0.1:{provider_port}/{PLANTED}/1/2/3.png")
    logged = _everything_logged(caplog)
    assert "127.0.0.1" in logged and PLANTED not in logged
    assert {r.name for r in caplog.records} >= {"httpx", "httpcore.connection", "httpcore.http11"}


async def test_a_secret_in_a_url_s_port_is_a_fetch_failure_that_names_no_url(
    caplog: pytest.LogCaptureFixture,
) -> None:
    from services.api.tile_proxy import TileFetchFailed, _http_get

    caplog.set_level(logging.DEBUG)
    with pytest.raises(TileFetchFailed) as failed:
        await _http_get(f"http://127.0.0.1:{PLANTED}/1/2/3.png")
    assert PLANTED not in str(failed.value) and failed.value.__suppress_context__
    assert PLANTED not in _everything_logged(caplog)


@pytest.mark.parametrize(
    "name", ["httpx", "httpcore", "httpcore.connection", "httpcore.http11", "httpcore.http2"]
)
def test_each_http_client_logger_drops_what_a_url_carries_past_its_host(
    caplog: pytest.LogCaptureFixture, name: str
) -> None:
    """Measured: no record of httpcore's own loggers carries a URL past its host today (the real
    fetch above), so each is held to it by a record made as httpx makes its own: a format string and
    the URL as an argument. A logger's filter applies to its own records alone, never a child's."""
    import services.api.tile_proxy  # noqa: F401 - installs the filters

    caplog.set_level(logging.DEBUG)
    url = f"https://tiles.example.test/a/{PLANTED}?k={PLANTED}"
    logging.getLogger(name).debug('HTTP Request: %s %s "%s"', "GET", url, "200")
    logged = _everything_logged(caplog)
    assert "tiles.example.test" in logged and PLANTED not in logged


async def test_a_tile_larger_than_any_tile_is_refused_and_not_kept(provider_port: int) -> None:
    """ADR-147 decision 5: a response past the cap (4 MB; a tile is tens of kilobytes) is a failed
    fetch, read no further, so a provider cannot fill the cache or the Conduit's memory."""
    from services.api.tile_proxy import MAX_TILE_BYTES, TileFetchFailed, _http_get

    assert MAX_TILE_BYTES == 4 * 1024 * 1024
    with pytest.raises(TileFetchFailed, match="larger"):
        await _http_get(f"http://127.0.0.1:{provider_port}/7/1/2.png")
