"""`python -m services.api.prefetch` (the `geometry_ref` areas `osprey.yaml` names) follows *Admin ›
Maps* as the Conduit does (`06_DECISIONS.md` ADR-147 decision 1): the maps file's providers once it
holds them, and a provider's key set in Admin, for its own address only. Offline: the map and keys
it would fetch with, not a fetch."""

from __future__ import annotations

import asyncio
from pathlib import Path

import yaml
from pydantic import SecretStr
from services.api.map_admin import InMemoryMapAdminAudit, MapAdmin, MapKeyFile, MapSettingsFile
from services.api.prefetch import effective_map

from schemas.mapconfig import MapProvider

OSM = {
    "id": "osm-local", "label": "OSM", "kind": "vector", "source": "file:///data/tiles/gb.pmtiles",
    "attribution": "© OSM contributors",
    "licence": {"id": "ODbL-1.0", "redistributable": True, "client_scope": "open"},
}  # fmt: skip
HOSTED = {
    "id": "hosted", "label": "Hosted", "kind": "raster",
    "source": "https://tiles.example.test/{z}/{x}/{y}.png?key={credential}", "proxy": "required",
    "cache": {"ttl_days": 30, "prefetch_areas": ["area-1"]}, "attribution": "E",
    "licence": {"id": "e", "redistributable": False, "client_scope": "per-deployment"},
}  # fmt: skip


def test_the_maps_file_and_its_keys_are_what_prefetch_fetches_with(tmp_path: Path) -> None:
    config = tmp_path / "osprey.yaml"
    config.write_text(yaml.safe_dump({"map": {"default": "osm-local", "providers": [OSM]}}))
    folder = tmp_path / "map-settings"
    environ = {"OSPREY_MAP_SETTINGS_DIR": str(folder)}

    before, key_before = effective_map(config, environ)
    assert [p.id for p in before.providers] == ["osm-local"] and key_before("hosted") is None

    admin = MapAdmin(
        installed=before, settings_file=MapSettingsFile(folder), key_file=MapKeyFile(folder),
        audit=InMemoryMapAdminAudit(), tiles_root=tmp_path,
    )  # fmt: skip
    asyncio.run(admin.add_provider("a", MapProvider.model_validate(HOSTED)))
    asyncio.run(admin.set_key("a", "hosted", SecretStr("k-synthetic")))

    after, key_after = effective_map(config, environ)
    assert [p.id for p in after.providers] == ["osm-local", "hosted"]
    assert key_after("hosted") == "k-synthetic"
