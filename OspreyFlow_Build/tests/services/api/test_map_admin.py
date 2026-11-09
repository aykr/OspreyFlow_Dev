"""*Admin › Maps*' service (`06_DECISIONS.md` ADR-147), through `MapAdmin` with real files in a
temporary folder, an in-memory tile store and an injected tile fetch (rule 9: no real tile is ever
fetched; every address is a `.test` name).

- the maps file replaces `osprey.yaml`'s `map:` whole from the first change, and is `600`;
- a key set in Admin is in the key file (`600`) and nowhere else: no view, history entry, maps file
  or log record carries it; a changed address drops it; a provider that takes none refuses one;
- the tile proxy is given the Admin key before `osprey.yaml`'s `env:` reference;
- prefetch areas: a box over the tile cap, or for a provider not proxied and cached, refused in
  words; a run fetches each missing tile once, with the key, and says a failure in fixed words that
  carry neither the key nor the address; the schedule says when it is due and the scheduler runs it;
- the local basemap's state, the glyphs and the builder; a build on a small synthetic region writes
  its file, loads its places and registers a tier-1 provider in the maps file.
"""

from __future__ import annotations

import asyncio
import logging
import stat
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
from pydantic import SecretStr, ValidationError
from services.api.map_admin import (
    PLANETILER_JAR,
    InMemoryMapAdminAudit,
    MapAdmin,
    MapAdminRefused,
    MapKeyFile,
    MapSettingsFile,
    PrefetchScheduler,
    area_tiles,
    build_basemap,
    tier_of,
)

from schemas.map_admin import MAX_AREA_TILES, PrefetchArea, PrefetchSchedule
from schemas.mapconfig import MapConfig, MapProvider

PLANTED = "k-PLANTED-map-key-Z8Q3-do-not-leak"
OSM = {
    "id": "osm-local", "label": "OpenStreetMap", "kind": "vector",
    "source": "file:///data/tiles/gb.pmtiles", "style": "bundled:osprey-dark",
    "attribution": "© OpenStreetMap contributors",
    "licence": {"id": "ODbL-1.0", "redistributable": True, "client_scope": "open"},
}  # fmt: skip
HOSTED = {
    "id": "hosted-tiles", "label": "Hosted tiles", "kind": "raster",
    "source": "https://tiles.example.test/{z}/{x}/{y}.png?key={credential}",
    "proxy": "required", "cache": {"ttl_days": 30}, "attribution": "Example",
    "licence": {"id": "example", "redistributable": False, "client_scope": "per-deployment"},
}  # fmt: skip
WMTS = {
    "id": "corporate-wmts", "label": "Corporate aerial", "kind": "raster", "service": "wmts",
    "endpoint": "https://gis.example.test/wmts", "layer": "aerial", "tile_matrix_set": "GM",
    "format": "image/png", "wmts_style": "default", "proxy": "required",
    "attribution": "Corporate",
    "licence": {"id": "internal", "redistributable": False, "client_scope": "per-deployment"},
}  # fmt: skip


class MemoryTiles:
    def __init__(self) -> None:
        self.tiles: dict[str, bytes] = {}

    def read(self, object_key: str, ttl_days: int) -> bytes | None:
        return self.tiles.get(object_key)

    def write(self, object_key: str, data: bytes) -> None:
        self.tiles[object_key] = data



@pytest.fixture(autouse=True)
def _no_real_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every `.test` name resolves to nothing, as it should, whatever this network's resolver does;
    a case that needs a name to resolve inside says so itself."""
    from services.api import map_admin

    monkeypatch.setattr(map_admin, "resolve_host", lambda host: [])

class World:
    def __init__(self, tmp_path: Path, *, providers: list[dict[str, object]] | None = None) -> None:
        self.folder = tmp_path / "map-settings"
        self.tiles_root = tmp_path / "tiles"
        self.tiles_root.mkdir()
        self.audit = InMemoryMapAdminAudit()
        self.store = MemoryTiles()
        self.urls: list[str] = []
        self.fail_with: BaseException | None = None
        self.clock = datetime(2026, 11, 8, 12, 0, tzinfo=UTC)
        installed = MapConfig.model_validate(
            {"default": "osm-local", "providers": providers or [OSM, HOSTED]}
        )

        async def http_get(url: str) -> bytes:
            self.urls.append(url)
            if self.fail_with is not None:
                raise self.fail_with
            return b"\x89PNG tile"

        self.admin = MapAdmin(
            installed=installed,
            settings_file=MapSettingsFile(self.folder),
            key_file=MapKeyFile(self.folder),
            audit=self.audit,
            tiles_root=self.tiles_root,
            tile_store=lambda: self.store,
            http_get=http_get,
            now=lambda: self.clock,
            java=lambda _name: "/usr/bin/java",
        )

    def everything_kept(self) -> str:
        """Every file in the settings folder but the key file, every view and history entry."""
        files = "".join(
            p.read_text()
            for p in self.folder.glob("*")
            if p.is_file() and p.name != "map-keys.yaml"
        )
        return (
            files
            + self.admin.view().model_dump_json()
            + "".join(e.model_dump_json() for e in self.audit.entries)
        )


def _area(**overrides: object) -> PrefetchArea:
    base: dict[str, object] = {
        "name": "Area of operations", "provider_id": "hosted-tiles",
        "west": -1.3, "south": 51.7, "east": -1.2, "north": 51.8, "zoom_min": 10, "zoom_max": 12,
    }  # fmt: skip
    base.update(overrides)
    return PrefetchArea.model_validate(base)


async def test_osprey_yaml_s_map_stands_until_the_first_change_then_the_maps_file_replaces_it(
    tmp_path: Path,
) -> None:
    w = World(tmp_path)
    assert w.admin.config().default == "osm-local" and not w.admin.view().changed_in_admin
    assert not (w.folder / "maps.yaml").exists()

    await w.admin.add_provider("admin-1", MapProvider.model_validate(WMTS))

    assert w.admin.view().changed_in_admin
    assert [p.id for p in w.admin.config().providers] == [
        "osm-local",
        "hosted-tiles",
        "corporate-wmts",
    ]
    mode = stat.S_IMODE((w.folder / "maps.yaml").stat().st_mode)
    assert mode == 0o600
    # A second admin reading the same folder sees the change (another replica, the command line).
    other = World.__new__(World)
    other_admin = MapAdmin(
        installed=MapConfig.model_validate({"default": "osm-local", "providers": [OSM]}),
        settings_file=MapSettingsFile(w.folder), key_file=MapKeyFile(w.folder),
        audit=InMemoryMapAdminAudit(), tiles_root=w.tiles_root,
    )  # fmt: skip
    del other
    assert len(other_admin.config().providers) == 3


async def test_a_key_set_in_admin_is_in_the_key_file_alone(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    w = World(tmp_path)

    view = await w.admin.set_key("admin-1", "hosted-tiles", SecretStr(PLANTED))
    row = next(p for p in view.providers if p.provider.id == "hosted-tiles")
    assert row.key_state == "set" and row.ready and row.key_set_by == "admin-1"
    assert w.admin.key_for("hosted-tiles") == PLANTED
    assert stat.S_IMODE((w.folder / "map-keys.yaml").stat().st_mode) == 0o600
    await w.admin.set_key("admin-1", "hosted-tiles", SecretStr(PLANTED + "-rotated"))

    assert PLANTED not in w.everything_kept()
    assert all(PLANTED not in r.getMessage() for r in caplog.records)
    assert [e.action for e in w.audit.entries] == ["key_set", "key_set"]
    assert w.audit.entries[1].changes == {"key": {"old": "set", "new": "set"}}

    await w.admin.remove_key("admin-1", "hosted-tiles")
    assert w.admin.key_for("hosted-tiles") is None
    assert w.admin.view().providers[1].state == "Needs a key: none is set."


async def test_a_changed_address_drops_the_key_held_for_the_old_one(tmp_path: Path) -> None:
    w = World(tmp_path)
    await w.admin.set_key("admin-1", "hosted-tiles", SecretStr(PLANTED))
    moved = MapProvider.model_validate(
        {**HOSTED, "source": "https://elsewhere.example.test/{z}/{x}/{y}?k={credential}"}
    )

    await w.admin.edit_provider("admin-1", "hosted-tiles", moved)

    assert w.admin.key_for("hosted-tiles") is None
    edit = w.audit.entries[-1]
    assert edit.action == "provider_edited" and "source" in edit.changes and "key" in edit.changes


async def test_a_provider_that_takes_no_key_refuses_one(tmp_path: Path) -> None:
    w = World(tmp_path)
    with pytest.raises(MapAdminRefused, match="takes no key"):
        await w.admin.set_key("admin-1", "osm-local", SecretStr(PLANTED))
    assert not (w.folder / "map-keys.yaml").exists()


async def test_the_default_and_a_provider_an_area_uses_are_not_removed(tmp_path: Path) -> None:
    w = World(tmp_path)
    with pytest.raises(MapAdminRefused, match="Choose another default"):
        await w.admin.remove_provider("admin-1", "osm-local")
    await w.admin.set_areas("admin-1", [_area()])
    with pytest.raises(MapAdminRefused, match="prefetch area uses"):
        await w.admin.remove_provider("admin-1", "hosted-tiles")
    with pytest.raises(MapAdminRefused, match="no map provider"):
        await w.admin.set_default("admin-1", "nowhere")


async def test_an_area_over_the_tile_cap_is_refused_with_its_count(tmp_path: Path) -> None:
    w = World(tmp_path)
    big = _area(west=-5.0, south=50.0, east=1.0, north=55.0, zoom_min=0, zoom_max=14)
    assert area_tiles(big) > MAX_AREA_TILES

    with pytest.raises(MapAdminRefused, match=f"{area_tiles(big):,} tiles") as refused:
        await w.admin.set_areas("admin-1", [big])
    assert refused.value.status == 422
    assert w.admin.view().areas == []


async def test_an_area_for_a_provider_the_conduit_does_not_cache_is_refused(tmp_path: Path) -> None:
    w = World(tmp_path)
    with pytest.raises(MapAdminRefused, match="not fetched and cached"):
        await w.admin.set_areas("admin-1", [_area(provider_id="osm-local")])


async def test_a_run_fetches_each_missing_tile_once_with_the_admin_key(tmp_path: Path) -> None:
    w = World(tmp_path)
    await w.admin.set_key("admin-1", "hosted-tiles", SecretStr(PLANTED))
    area = _area()
    await w.admin.set_areas("admin-1", [area])

    first = await w.admin.run_prefetch("admin-1")
    second = await w.admin.run_prefetch("admin-1")

    tiles = area_tiles(area)
    assert first[0].tiles_fetched == tiles and first[0].tiles_already_cached == 0
    assert second[0].tiles_fetched == 0 and second[0].tiles_already_cached == tiles
    assert len(w.urls) == tiles and all(u.endswith(f"key={PLANTED}") for u in w.urls)
    assert all(u.startswith("https://tiles.example.test/") for u in w.urls)
    assert PLANTED not in w.everything_kept()
    assert w.admin.view().areas[0].last_run is not None


@pytest.mark.parametrize(
    ("error", "words"),
    [
        (httpx.ConnectError("refused at https://tiles.example.test/?key=" + PLANTED),
         "could not be reached"),
        (httpx.HTTPStatusError(
            "403 for https://tiles.example.test/?key=" + PLANTED,
            request=httpx.Request("GET", "https://tiles.example.test/?key=" + PLANTED),
            response=httpx.Response(403)), "refused a tile (HTTP 403)"),
        (ValueError("unexpected " + PLANTED), "unexpected answer"),
    ],
)  # fmt: skip
async def test_a_failed_run_is_said_in_fixed_words_without_the_key_or_the_address(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, error: BaseException, words: str
) -> None:
    caplog.set_level(logging.DEBUG)
    w = World(tmp_path)
    await w.admin.set_key("admin-1", "hosted-tiles", SecretStr(PLANTED))
    await w.admin.set_areas("admin-1", [_area()])
    w.fail_with = error

    runs = await w.admin.run_prefetch("admin-1")

    assert runs[0].failed is not None and words in runs[0].failed
    assert PLANTED not in w.everything_kept() and "tiles.example.test" not in runs[0].failed
    assert all(PLANTED not in r.getMessage() for r in caplog.records)


async def test_a_run_for_a_provider_with_no_key_says_so(tmp_path: Path) -> None:
    w = World(tmp_path)
    await w.admin.set_areas("admin-1", [_area()])
    runs = await w.admin.run_prefetch("admin-1")
    assert runs[0].failed == "The provider needs a key and none is set." and w.urls == []


async def test_the_schedule_is_due_every_so_many_hours_and_the_scheduler_runs_it(
    tmp_path: Path,
) -> None:
    w = World(tmp_path)
    await w.admin.set_key("admin-1", "hosted-tiles", SecretStr(PLANTED))
    await w.admin.set_areas("admin-1", [_area(zoom_max=10)])
    assert w.admin.next_run_at() is None  # by hand only
    await w.admin.set_schedule("admin-1", PrefetchSchedule(every_hours=6))
    assert w.admin.due()  # never run: due at once

    scheduler = PrefetchScheduler(w.admin, check_seconds=0.01)
    scheduler.start()
    for _ in range(200):
        if w.admin.view().areas[0].last_run is not None:
            break
        await asyncio.sleep(0.01)
    await scheduler.close()

    assert w.admin.view().areas[0].last_run is not None
    assert not w.admin.due()
    assert w.admin.next_run_at() == w.clock + timedelta(hours=6)
    w.clock += timedelta(hours=6)
    assert w.admin.due()
    assert any(e.by == "schedule" and e.action == "prefetch_run" for e in w.audit.entries)


def test_each_provider_s_tier() -> None:
    assert tier_of(MapProvider.model_validate(OSM)) == 1
    zoomstack = {**OSM, "id": "os", "licence": {"id": "OGL-UK-3.0", "redistributable": True,
                                                 "client_scope": "open"}}  # fmt: skip
    assert tier_of(MapProvider.model_validate(zoomstack)) == 2
    assert tier_of(MapProvider.model_validate(HOSTED)) == 3
    assert tier_of(MapProvider.model_validate(WMTS)) == 4


async def test_the_local_basemap_s_state_the_glyphs_and_the_builder(tmp_path: Path) -> None:
    w = World(tmp_path)
    state = w.admin.view().basemap
    assert not state.glyphs_installed and not state.builder_ready
    assert "planetiler" in state.builder_state and "rutland" in state.regions

    (w.tiles_root / "fonts" / "Noto Sans Regular").mkdir(parents=True)
    (w.tiles_root / "fonts" / "Noto Sans Regular" / "0-255.pbf").write_bytes(b"glyphs")
    (w.tiles_root / PLANETILER_JAR).parent.mkdir()
    (w.tiles_root / PLANETILER_JAR).write_bytes(b"jar")

    state = w.admin.view().basemap
    assert state.glyphs_installed and state.builder_ready


async def test_a_build_on_a_small_synthetic_region_registers_a_tier_1_provider(
    tmp_path: Path,
) -> None:
    """The build's own path end to end, offline: the extract is a synthetic PBF-headed file (never
    downloaded), planetiler's run writes a PMTiles-headed file, and the places loader counts. Real
    planetiler needs Java and the jar, so its run is the one part stood in (`P3_RED_RECORD.md`)."""
    w = World(tmp_path)
    (w.tiles_root / PLANETILER_JAR).parent.mkdir()
    (w.tiles_root / PLANETILER_JAR).write_bytes(b"PK synthetic jar")  # placed, as the CLI does
    progress: list[str] = []
    asked: list[str] = []

    def downloader(region: str, dest: Path) -> Path:
        asked.append(region)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"\x00\x00\x00\x0d\x0a\x09OSMHeader synthetic")
        return dest

    def planetiler(extract: Path, output: Path, *, jar_path: Path) -> Path:
        assert jar_path == w.tiles_root / PLANETILER_JAR and extract.is_file()
        output.write_bytes(b"PMTiles\x03 synthetic")
        return output

    async def load_places(extract: Path) -> tuple[int, int, int]:
        return (3, 1, 0)

    name, created, referenced, rejected = await build_basemap(
        w.admin, by="admin-1", region="rutland", load_places=load_places, progress=progress.append,
        downloader=downloader, planetiler_runner=planetiler, tiles_root=w.tiles_root,
    )  # fmt: skip

    assert (name, created, referenced, rejected) == ("rutland.pmtiles", 3, 1, 0) and asked == [
        "rutland"
    ]
    provider = w.admin.provider("osm-local-rutland")
    assert provider.source == "file:///data/tiles/built/rutland.pmtiles" and tier_of(provider) == 1
    assert provider.licence.client_scope == "open" and provider.credential is None
    assert any("planetiler" in line for line in progress)
    assert w.audit.entries[-1].action == "basemap_built"

    with pytest.raises(MapAdminRefused, match="not a region"):
        await build_basemap(w.admin, by="admin-1", region="atlantis", load_places=load_places,
                            tiles_root=w.tiles_root)  # fmt: skip


async def test_a_build_with_no_java_or_no_jar_is_refused_before_anything_is_downloaded(
    tmp_path: Path,
) -> None:
    """ADR-147 decision 3, as the orchestrator's interim left it: no Java in the Conduit's image.
    The build says so in the builder's own words and fetches nothing."""
    w = World(tmp_path)
    asked: list[str] = []

    def downloader(region: str, dest: Path) -> Path:
        asked.append(region)
        return dest

    async def load_places(extract: Path) -> tuple[int, int, int]:
        return (0, 0, 0)

    w.admin._java = lambda _name: None  # noqa: SLF001 - this image's Java, absent
    with pytest.raises(MapAdminRefused, match="Java is not installed in the Conduit"):
        await build_basemap(w.admin, by="a", region="rutland", load_places=load_places,
                            downloader=downloader, tiles_root=w.tiles_root)  # fmt: skip
    w.admin._java = lambda _name: "/usr/bin/java"  # noqa: SLF001 - Java, but no jar placed
    with pytest.raises(MapAdminRefused, match="planetiler"):
        await build_basemap(w.admin, by="a", region="rutland", load_places=load_places,
                            downloader=downloader, tiles_root=w.tiles_root)  # fmt: skip
    assert asked == []


# --- from the lane's own review -----------------------------------------------------------------


async def test_a_key_is_given_only_to_the_address_it_was_entered_for(tmp_path: Path) -> None:
    """ADR-147 decision 2: a key is never sent to an address it was not entered for. The address is
    the whole of what the tile URL is made from (`source`, `endpoint`, `layer`, `variables`, the
    parameter), so changing a variable moves the key nowhere; nor does `osprey.yaml` changed under
    a surviving key file, or a maps file restored over one."""
    templated = {**HOSTED, "source": "https://{host_part}.example.test/{z}/{x}/{y}?key={credential}",
                 "variables": {"host_part": "tiles"}}  # fmt: skip
    w = World(tmp_path, providers=[OSM, templated])
    await w.admin.set_key("a", "hosted-tiles", SecretStr(PLANTED))
    assert w.admin.key_for("hosted-tiles") == PLANTED

    # The installer's osprey.yaml points the provider elsewhere; the key file survives.
    moved = {**templated, "variables": {"host_part": "elsewhere"}}
    other = MapAdmin(
        installed=MapConfig.model_validate({"default": "osm-local", "providers": [OSM, moved]}),
        settings_file=MapSettingsFile(w.folder), key_file=MapKeyFile(w.folder),
        audit=InMemoryMapAdminAudit(), tiles_root=w.tiles_root,
    )  # fmt: skip
    assert other.key_for("hosted-tiles") is None
    row = next(p for p in other.view().providers if p.provider.id == "hosted-tiles")
    assert row.key_state == "none" and "another address" in row.state


async def test_a_provider_the_conduit_does_not_fetch_refuses_a_key(tmp_path: Path) -> None:
    # A browser-fetched provider that takes a key is refused as it is read (ADR-147 Amendment 1),
    # so Admin never holds one to refuse a key for.
    browser = {**HOSTED, "id": "browser", "proxy": "none"}
    with pytest.raises(ValidationError, match="must be fetched by the Conduit"):
        MapConfig.model_validate({"default": "osm-local", "providers": [OSM, browser]})
    profile = {"id": "zoomstack", "label": "OS Open Zoomstack", "kind": "vector",
               "profile": "os-open-zoomstack", "credential": "env:OS_KEY", "attribution": "OS",
               "licence": {"id": "OGL-UK-3.0", "redistributable": True,
                           "client_scope": "open"}}  # fmt: skip
    w = World(tmp_path, providers=[OSM, profile])
    for provider_id in ("zoomstack",):
        with pytest.raises(MapAdminRefused):
            await w.admin.set_key("a", provider_id, SecretStr(PLANTED))
    row = next(p for p in w.admin.view().providers if p.provider.id == "zoomstack")
    assert not row.ready and "profile" in row.state


async def test_a_maps_file_that_cannot_be_read_leaves_the_map_on_osprey_yaml_s(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A restored or hand-edited maps file that does not validate must not take the map away from
    every analyst: the Conduit serves `osprey.yaml`'s and says why in its log."""
    w = World(tmp_path)
    w.folder.mkdir(parents=True, exist_ok=True)
    (w.folder / "maps.yaml").write_text("map: {default: nowhere, providers: []}\n")
    assert w.admin.config().default == "osm-local"
    assert any("maps file" in r.getMessage() for r in caplog.records)


async def test_adding_a_provider_records_each_of_its_fields(tmp_path: Path) -> None:
    w = World(tmp_path)
    await w.admin.add_provider("a", MapProvider.model_validate({**WMTS, "id": "w2"}))
    changes = w.audit.entries[-1].changes
    assert changes["endpoint"] == {"old": None, "new": "https://gis.example.test/wmts"}
    assert changes["attribution"]["new"] == "Corporate" and "tier" in changes


async def test_a_run_is_paced_so_a_provider_is_not_flooded(tmp_path: Path) -> None:
    """ADR-147 decision 5: at most so many tiles a second from one run (`tiles_per_second`), the
    pause between fetches, never before the first or for a tile already kept."""
    w = World(tmp_path)
    pauses: list[float] = []

    async def sleep(seconds: float) -> None:
        pauses.append(seconds)

    w.admin._sleep = sleep  # noqa: SLF001 - the run's own pause, stood in
    await w.admin.set_key("a", "hosted-tiles", SecretStr(PLANTED))
    area = _area()
    assert area_tiles(area) > 1
    await w.admin.set_areas("a", [area])
    await w.admin.run_prefetch("a")
    assert len(pauses) == area_tiles(area) - 1 and all(p == 1 / 10 for p in pauses)
    pauses.clear()
    await w.admin.run_prefetch("a")  # every tile kept: nothing fetched, nothing waited for
    assert pauses == []
