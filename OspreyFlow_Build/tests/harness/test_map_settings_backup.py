"""The maps file in a backup set, and what a restore says (`06_DECISIONS.md` ADR-147 decision 1;
`05_DEPLOYMENT.md` §6.1: "A backup carries no secrets"). The maps file is taken from the Conduit's
own volume; the map key file beside it never is, by any path: the backup reads the maps file by its
name alone, and the real `MapAdmin` writes a planted key only into the key file. A restore puts the
maps file back and names each provider whose key must be entered again."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from harness import backup, restore
from pydantic import SecretStr
from services.api.map_admin import InMemoryMapAdminAudit, MapAdmin, MapKeyFile, MapSettingsFile

from schemas.mapconfig import MapConfig, MapProvider
from tests.harness.test_gateway_backup import SALT_HERE, _dry_run, _env, _set

PLANTED = "k-PLANTED-backup-map-key-T5V1"
HOSTED = {
    "id": "hosted-tiles", "label": "Hosted tiles", "kind": "raster",
    "source": "https://tiles.example.test/{z}/{x}/{y}.png?key={credential}",
    "proxy": "required", "attribution": "Example",
    "licence": {"id": "example", "redistributable": False, "client_scope": "per-deployment"},
}  # fmt: skip
OSM = {
    "id": "osm-local", "label": "OpenStreetMap", "kind": "vector",
    "source": "file:///data/tiles/gb.pmtiles", "attribution": "© OpenStreetMap contributors",
    "licence": {"id": "ODbL-1.0", "redistributable": True, "client_scope": "open"},
}  # fmt: skip


async def _volume_with_a_key(folder: Path) -> None:
    admin = MapAdmin(
        installed=MapConfig.model_validate({"default": "osm-local", "providers": [OSM]}),
        settings_file=MapSettingsFile(folder), key_file=MapKeyFile(folder),
        audit=InMemoryMapAdminAudit(), tiles_root=folder,
    )  # fmt: skip
    await admin.add_provider("a", MapProvider.model_validate(HOSTED))
    await admin.set_key("a", "hosted-tiles", SecretStr(PLANTED))


async def test_a_backup_takes_the_maps_file_and_never_a_map_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    volume = tmp_path / "volume"
    await _volume_with_a_key(volume)
    compose = _env(tmp_path / "dep", SALT_HERE)
    asked: list[str] = []

    def run(command: list[str], **_kw: object) -> str:
        script = command[-1]
        asked.append(script)
        # The Conduit's volume, read as the command asks: `cat <path>`.
        path = script.split("cat ", 1)[1].split(" ", 1)[0]
        target = volume / Path(path).name
        return target.read_text() if target.is_file() else ""

    monkeypatch.setattr(backup, "_run", run)
    taken = backup.backup_maps_file(compose, tmp_path / "set" / "config" / "maps.yaml")

    assert taken is not None and "hosted-tiles" in taken.read_text()
    assert PLANTED in (volume / "map-keys.yaml").read_text()  # the plant is really on the volume
    assert all("map-keys" not in a for a in asked)
    everything = b"".join(p.read_bytes() for p in (tmp_path / "set").rglob("*") if p.is_file())
    assert PLANTED.encode() not in everything


def test_a_restore_names_each_map_provider_whose_key_to_enter_again(tmp_path: Path) -> None:
    directory = _set(tmp_path, keys=[])
    (directory / "config" / "maps.yaml").write_text(
        "keys_held: [hosted-tiles, os-ngd]\nareas: []\n"
    )
    plan = _dry_run(directory, _env(tmp_path / "here", SALT_HERE))
    assert plan.map_keys_to_enter == ("hosted-tiles", "os-ngd")
    said = plan.render()
    assert "hosted-tiles, os-ngd" in said and "Admin › Maps" in said


def test_a_restore_puts_the_maps_file_back_private(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sent: list[tuple[list[str], str]] = []

    def run(command: list[str], *, item: str, input: str | None = None, **_kw: object) -> str:
        sent.append((command, input or ""))
        return ""

    monkeypatch.setattr(restore, "_run", run)
    held = tmp_path / "maps.yaml"
    held.write_text(json.dumps({"areas": []}))
    restore.restore_maps_file(_env(tmp_path / "dep", SALT_HERE), held)
    command, given = sent[0]
    assert command[-1] == "umask 077 && cat > /run/osprey/map-settings/maps.yaml"
    assert given == held.read_text()
