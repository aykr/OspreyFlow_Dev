"""v0.6.0 item 10, split for the demo's rebuild window (the orchestrator, on the owner's word, 15 November
2026). A fresh install empties ArcadeDB, so the settlements cannot load early, but the tiles folder
survives it. So the build runs in two stages of the same command:

- `--stage tiles`, before the window with the demo up: the extract downloaded, planetiler run, and the
  extract's settlements saved beside it (`<region>.places.json`). No graph, no analytics store, and
  nothing registered, so the running demo's map is unchanged.
- `--stage places`, in the window after the fresh install, with the Conduit stopped: the settlements
  loaded from that file, not from the 2 GB extract again (measured: a 14-minute pass); their points;
  the dataset and the provider registered. Refused in words, before anything is written, when the
  tiles stage's files are not there.

Without `--stage` the build is the whole of it, as before.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import scripts.build_local_basemap as script
from schemas.mapconfig import MapConfig
from services.api import map_admin, map_places
from services.api.map_admin import (
    PLANETILER_JAR,
    InMemoryMapAdminAudit,
    MapAdmin,
    MapAdminRefused,
    MapKeyFile,
    MapSettingsFile,
    build_basemap,
    command_parser,
)

from tests.scenarios.fixtures.osm_extract import build_synthetic_osm_pbf

OSM = {
    "id": "osm-local", "label": "OSM", "kind": "vector", "source": "file:///data/tiles/gb.pmtiles",
    "attribution": "© OSM contributors",
    "licence": {"id": "ODbL-1.0", "redistributable": True, "client_scope": "open"},
}  # fmt: skip
PLACES = [("Cranford", "place", "hamlet", 51.488, -0.459), ("The Anchor", "amenity", "cafe", 51.5, -0.1)]


def _admin(tmp_path: Path) -> MapAdmin:
    tiles = tmp_path / "tiles"
    (tiles / PLANETILER_JAR).parent.mkdir(parents=True)
    (tiles / PLANETILER_JAR).write_bytes(b"PK synthetic jar")
    return MapAdmin(
        installed=MapConfig.model_validate({"default": "osm-local", "providers": [OSM]}),
        settings_file=MapSettingsFile(tmp_path / "maps"), key_file=MapKeyFile(tmp_path / "maps"),
        audit=InMemoryMapAdminAudit(), tiles_root=tiles, java=lambda _name: "/usr/bin/java",
    )  # fmt: skip


class _Seen:
    def __init__(self) -> None:
        self.steps: list[str] = []

    def downloader(self, region: str, dest: Path) -> Path:
        self.steps.append("download")
        dest.parent.mkdir(parents=True, exist_ok=True)
        build_synthetic_osm_pbf(dest, places=PLACES)
        return dest

    def planetiler(self, extract: Path, output: Path, *, jar_path: Path) -> Path:
        self.steps.append("planetiler")
        output.write_bytes(b"PMTiles\x03 synthetic")
        return output

    async def load_places(self, source: Path) -> tuple[int, int, int]:
        self.steps.append(f"load {source.name}")
        return 1, 0, 0

    async def settle(self) -> None:
        self.steps.append("settle")


async def _build(admin: MapAdmin, seen: _Seen, stage: str | None) -> tuple[str, int, int, int]:
    return await build_basemap(
        admin, by="cli:owner", region="rutland", load_places=seen.load_places, settle=seen.settle,
        downloader=seen.downloader, planetiler_runner=seen.planetiler, tiles_root=admin.tiles_root,
        stage=stage, progress=lambda _line: None,
    )  # fmt: skip


async def test_the_tiles_stage_builds_the_tiles_and_saves_the_settlements_and_registers_nothing(
    tmp_path: Path,
) -> None:
    admin, seen = _admin(tmp_path), _Seen()
    await _build(admin, seen, "tiles")
    assert seen.steps == ["download", "planetiler"]
    built = admin.tiles_root / "built"
    assert (built / "rutland.pmtiles").is_file()
    saved = json.loads((built / "extracts" / "rutland.places.json").read_text(encoding="utf-8"))
    assert [row["name"] for row in saved] == ["Cranford"]  # the settlements alone, as the load reads
    with pytest.raises(MapAdminRefused):
        admin.provider("osm-local-rutland")  # the running demo's map is unchanged


async def test_the_places_stage_loads_the_saved_settlements_and_registers_the_provider(
    tmp_path: Path,
) -> None:
    admin = _admin(tmp_path)
    await _build(admin, _Seen(), "tiles")
    seen = _Seen()
    await _build(admin, seen, "places")
    assert seen.steps == ["load rutland.places.json", "settle"]  # no download, no planetiler
    assert admin.provider("osm-local-rutland").source == "file:///data/tiles/built/rutland.pmtiles"


@pytest.mark.parametrize("missing", ["rutland.pmtiles", "extracts/rutland.places.json"])
async def test_the_places_stage_is_refused_in_words_without_the_tiles_stage_s_files(
    tmp_path: Path, missing: str
) -> None:
    admin = _admin(tmp_path)
    await _build(admin, _Seen(), "tiles")
    (admin.tiles_root / "built" / missing).unlink()
    seen = _Seen()
    with pytest.raises(MapAdminRefused) as refused:
        await _build(admin, seen, "places")
    assert "--stage tiles" in refused.value.words and seen.steps == []


async def test_without_a_stage_the_build_is_the_whole_of_it(tmp_path: Path) -> None:
    admin, seen = _admin(tmp_path), _Seen()
    await _build(admin, seen, None)
    assert seen.steps == ["download", "planetiler", "load rutland.osm.pbf", "settle"]
    assert admin.provider("osm-local-rutland").source == "file:///data/tiles/built/rutland.pmtiles"


async def test_the_load_reads_a_saved_settlements_file_and_not_the_extract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    saved = tmp_path / "rutland.places.json"
    rows = [{"osm_id": "1", "name": "Cranford", "lat": "51.488", "lon": "-0.459"}]
    saved.write_text(json.dumps(rows), encoding="utf-8")

    def no_extract(_path: str) -> Any:
        raise AssertionError("the extract was read again")

    monkeypatch.setattr(script, "read_osm_places", no_extract)
    assert script.read_places(saved) == rows


def test_the_command_line_takes_a_stage() -> None:
    parse = command_parser().parse_args
    assert parse(["build", "great-britain", "--by", "x", "--unit", "u"]).stage is None
    assert parse(["build", "great-britain", "--by", "x", "--unit", "u", "--stage", "tiles"]).stage == "tiles"
    with pytest.raises(SystemExit):
        parse(["build", "great-britain", "--by", "x", "--unit", "u", "--stage", "maps"])
    assert map_admin.PLACES_FILE.format(region="rutland") == "rutland.places.json"


async def test_the_tiles_stage_from_the_command_line_needs_no_settings_and_no_database(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """P3, the rebuild's rehearsal (process/lanes/demo/REBUILD_2026-11-18.md): the tiles stage runs as
    a bare `docker run` of the Conduit's image beside a running deployment, with only the tiles folder
    mounted. The image holds no `osprey.yaml` and the container reaches no database, so the stage reads
    neither: not the maps settings or audit (`open_admin`), not the unit's check, not the graph or the
    analytics store. The unit is checked by the places stage, which loads into it."""
    tiles = tmp_path / "tiles"
    (tiles / PLANETILER_JAR).parent.mkdir(parents=True)
    (tiles / PLANETILER_JAR).write_bytes(b"PK synthetic jar")
    seen: list[Any] = []

    async def refused(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("the tiles stage reached for the settings or the database")

    async def build(admin: object, *, stage: str | None, tiles_root: Path, **_kw: Any) -> Any:
        seen.append((admin, stage, tiles_root))
        return ("rutland.pmtiles", 0, 0, 0)

    monkeypatch.setattr(map_admin, "open_admin", refused)
    monkeypatch.setattr(map_admin, "_analytics_if_free", refused)
    monkeypatch.setattr(map_places, "check_unit_from_env", refused)
    monkeypatch.setattr(map_admin, "build_basemap", build)
    monkeypatch.setattr(map_admin, "TILES_CONTAINER_PATH", str(tiles))
    code = await map_admin._main(["build", "rutland", "--by", "cli:x", "--unit", "u", "--stage", "tiles"])
    assert code == 0 and seen == [(None, "tiles", tiles)]


async def test_the_bare_tiles_stage_says_in_words_when_the_builder_is_missing(tmp_path: Path) -> None:
    """With no admin, the builder is checked from the tiles folder alone, before anything is fetched."""
    seen = _Seen()
    with pytest.raises(MapAdminRefused) as refused:
        await build_basemap(
            None, by="cli:x", region="rutland", load_places=seen.load_places,
            downloader=seen.downloader, planetiler_runner=seen.planetiler,
            tiles_root=tmp_path / "tiles", stage="tiles", progress=lambda _line: None,
        )  # fmt: skip
    # Java may or may not be on this machine's path; either way the words are the builder's own.
    assert refused.value.words == map_admin.builder_state(tmp_path / "tiles")[0] and seen.steps == []
    with pytest.raises(ValueError, match="tiles stage"):
        await build_basemap(None, by="cli:x", region="rutland", load_places=seen.load_places,
                            tiles_root=tmp_path / "tiles", stage="places")  # fmt: skip
