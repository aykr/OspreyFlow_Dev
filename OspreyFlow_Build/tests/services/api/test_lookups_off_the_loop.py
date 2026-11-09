"""Host lookups never run on the event loop (the independent review of L1.6, carried into L1.8).

`socket.getaddrinfo` blocks for as long as the resolver takes, which for a name that does not answer
is seconds. Called from an async route, it stalls every request the Conduit is serving. So each
async path that looks up a host — a connector's read, *Test connection*, naming a connection,
*Admin › Maps*' add and edit, a tile fetch for an Admin-added provider, and the prefetch — sends the
lookup to a worker thread (`asyncio.to_thread`).

Each case stands a recorder in for the module's one lookup (`resolve_host`, the only caller of
`getaddrinfo` in `connector_reads` and in `map_admin`), so the case sees the real path call it. The
recorder notes whether it ran on a thread with a running event loop. Each case asserts both that
the lookup happened (so the case cannot pass by never reaching it) and that it did not happen on the
loop. Shown red with each `to_thread` taken out
(`process/lanes/studio-b/l1.8/red-carry-lookups.txt`).
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from services.api import app as app_module
from services.api import connector_reads, map_admin
from services.api.app import app, get_principal
from services.api.connector_reads import Readers, check_connection, read_rows
from services.api.map_admin import InMemoryMapAdminAudit, MapAdmin, MapKeyFile, MapSettingsFile

from schemas.domain import Principal
from schemas.map_admin import PrefetchArea
from schemas.mapconfig import MapConfig, MapProvider
from schemas.sources import (
    ApiConnectionSettings,
    ApiRead,
    Connection,
    SqlConnectionSettings,
    SqlRead,
)

PUBLIC = "93.184.215.14"
ADMIN = Principal(id="admin-1", clearance="OFFICIAL", org_unit="u", roles=["osprey-admin"])


class Lookups:
    """A stand-in for `resolve_host`: answers `answer`, and notes where it was called."""

    def __init__(self, answer: list[str]) -> None:
        self.answer = answer
        self.on_loop: list[str] = []
        self.off_loop: list[str] = []

    def __call__(self, host: str) -> list[str]:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            self.off_loop.append(host)
        else:
            self.on_loop.append(host)
        return list(self.answer)

    def held_off_the_loop(self) -> None:
        assert self.on_loop == [], f"looked up on the event loop: {self.on_loop}"
        assert self.off_loop, "the path never looked the host up, so this case proves nothing"


@pytest.fixture
def connector_lookups(monkeypatch: pytest.MonkeyPatch) -> Lookups:
    found = Lookups([PUBLIC])
    monkeypatch.setattr(connector_reads, "resolve_host", found)
    return found


def _connection(settings: object) -> Connection:
    return Connection(
        id="c1", kind=settings.kind, name="synthetic", created_by="a",  # type: ignore[attr-defined]
        created_at=datetime(2026, 11, 9, tzinfo=UTC), settings=settings, datasets=["ds-a"],
    )  # fmt: skip


SQL = SqlConnectionSettings(host="db.example.test", database="nomis", user="reader", secret="NOMIS")
API = ApiConnectionSettings(base_url="https://telco.example.test")


async def _refuse_after_lookup(*_: Any, **__: Any) -> bool:
    return False  # no TCP reach: the SQL read stops, after its addresses were looked up


async def test_a_sql_read_looks_its_host_up_off_the_loop(connector_lookups: Lookups, tmp_path: Path) -> None:
    source = SimpleNamespace(read=SqlRead(table="public.visits"), refresh=None)
    with pytest.raises(Exception):  # noqa: B017 — nothing answers; only where the lookup ran matters
        await read_rows(
            source, _connection(SQL), dataset_id="ds-a", cursor=None, root=tmp_path,
            readers=Readers(sql_reach=_refuse_after_lookup, allowed_hosts=["db.example.test"]),
        )  # fmt: skip
    connector_lookups.held_off_the_loop()


async def test_an_api_read_looks_each_page_s_host_up_off_the_loop(
    connector_lookups: Lookups, tmp_path: Path
) -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=[{"n": 1}]))
    source = SimpleNamespace(read=ApiRead(path="/v1/numbers"), refresh=None)
    rows = await read_rows(
        source, _connection(API), dataset_id="ds-a", cursor=None, root=tmp_path,
        readers=Readers(http_transport=transport, allowed_hosts=["telco.example.test"]),
    )  # fmt: skip
    assert rows is not None
    connector_lookups.held_off_the_loop()


@pytest.mark.parametrize("settings", [SQL, API], ids=["sql", "api"])
async def test_test_connection_looks_the_host_up_off_the_loop(
    connector_lookups: Lookups, settings: object
) -> None:
    readers = Readers(
        sql_reach=_refuse_after_lookup, allowed_hosts=["db.example.test", "telco.example.test"]
    )
    await check_connection(_connection(settings), readers)
    connector_lookups.held_off_the_loop()


def test_naming_a_connection_looks_its_host_up_off_the_loop(
    connector_lookups: Lookups, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The route itself, `POST /v1/admin/connections`, as an administrator names one."""
    from services.api.sources import InMemorySourceStore

    class _Audit:
        async def record(self, **kwargs: Any) -> None:
            return None

    monkeypatch.setattr(app.state, "sources", InMemorySourceStore(), raising=False)
    monkeypatch.setattr(app.state, "audit", _Audit(), raising=False)
    app.dependency_overrides[get_principal] = lambda: ADMIN
    try:
        body = {"kind": "api", "name": "Telco (synthetic)", "datasets": ["ds-a"],
                "settings": {"kind": "api", "base_url": "https://telco.example.test"}}  # fmt: skip
        answer = TestClient(app).post("/v1/admin/connections", json=body)
    finally:
        app.dependency_overrides.clear()
    assert answer.status_code == 201, answer.text
    connector_lookups.held_off_the_loop()


# --- Admin › Maps ------------------------------------------------------------------------------

OSM = {
    "id": "osm-local", "label": "OpenStreetMap", "kind": "vector",
    "source": "file:///data/tiles/gb.pmtiles", "style": "bundled:osprey-dark",
    "attribution": "© OpenStreetMap contributors",
    "licence": {"id": "ODbL-1.0", "redistributable": True, "client_scope": "open"},
}  # fmt: skip
ADDED = {
    "id": "added-tiles", "label": "Added tiles", "kind": "raster",
    "source": "https://tiles.example.test/{z}/{x}/{y}.png", "proxy": "required",
    "attribution": "Example", "cache": {"ttl_days": 7},
    "licence": {"id": "example", "redistributable": False, "client_scope": "per-deployment"},
}  # fmt: skip


@pytest.fixture
def maps(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[SimpleNamespace]:
    found = Lookups([PUBLIC])
    monkeypatch.setattr(map_admin, "resolve_host", found)
    fetched: list[str] = []

    async def http_get(url: str) -> bytes:
        fetched.append(url)
        return b"\x89PNG synthetic tile"

    class _Tiles:
        def read(self, object_key: str, ttl_days: int) -> bytes | None:
            return None

        def write(self, object_key: str, data: bytes) -> None:
            return None

    admin = MapAdmin(
        installed=MapConfig.model_validate({"default": "osm-local", "providers": [OSM]}),
        settings_file=MapSettingsFile(tmp_path / "map-settings"),
        key_file=MapKeyFile(tmp_path / "map-settings"), audit=InMemoryMapAdminAudit(),
        tiles_root=tmp_path / "tiles", tile_store=lambda: _Tiles(), http_get=http_get,
    )  # fmt: skip
    (tmp_path / "tiles").mkdir()
    app.state.map_admin = admin
    app.dependency_overrides[get_principal] = lambda: ADMIN
    yield SimpleNamespace(admin=admin, lookups=found, fetched=fetched, client=TestClient(app))
    app.dependency_overrides.clear()
    del app.state.map_admin


#: The same provider with no cache, so a tile is fetched, not read from the tile cache.
UNCACHED = {**{k: v for k, v in ADDED.items() if k != "cache"}, "id": "uncached-tiles"}


def _add(maps: SimpleNamespace, provider: dict[str, Any] = ADDED) -> None:
    made = maps.client.post("/v1/admin/maps/providers", content=json.dumps({"provider": provider}))
    assert made.status_code == 200, made.text


def test_adding_a_map_provider_looks_its_host_up_off_the_loop(maps: SimpleNamespace) -> None:
    _add(maps)
    maps.lookups.held_off_the_loop()


def test_editing_a_map_provider_looks_its_host_up_off_the_loop(maps: SimpleNamespace) -> None:
    _add(maps)
    maps.lookups.off_loop.clear()
    edited = {**ADDED, "label": "Added tiles, renamed"}
    answer = maps.client.put(
        "/v1/admin/maps/providers/added-tiles", content=json.dumps({"provider": edited})
    )
    assert answer.status_code == 200, answer.text
    maps.lookups.held_off_the_loop()


def test_a_tile_for_an_added_provider_looks_its_host_up_off_the_loop(
    maps: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    _add(maps, UNCACHED)
    maps.lookups.off_loop.clear()

    async def fetch(url: str) -> bytes:
        return b"\x89PNG\r\n\x1a\n synthetic tile"

    monkeypatch.setattr(app_module, "fetch_tile", fetch)
    monkeypatch.setattr(app.state, "tile_cache_storage", None, raising=False)
    assert maps.client.get("/v1/map/tiles/uncached-tiles/1/0/0").status_code == 200
    maps.lookups.held_off_the_loop()


async def test_the_prefetch_looks_each_provider_s_host_up_off_the_loop(maps: SimpleNamespace) -> None:
    await maps.admin.add_provider("admin-1", MapProvider.model_validate(ADDED))
    area = PrefetchArea.model_validate({
        "name": "Area", "provider_id": "added-tiles",
        "west": -1.3, "south": 51.7, "east": -1.29, "north": 51.71, "zoom_min": 1, "zoom_max": 1,
    })  # fmt: skip
    await maps.admin.set_areas("admin-1", [area])
    maps.lookups.off_loop.clear()
    await maps.admin.run_prefetch("admin-1")
    maps.lookups.held_off_the_loop()
