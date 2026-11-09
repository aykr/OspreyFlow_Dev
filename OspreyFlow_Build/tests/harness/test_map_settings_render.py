"""The Conduit's maps file and its map key file in the rendered deployment (`06_DECISIONS.md`
ADR-147 decision 1): their own named volume, its folder named to the Conduit; the tiles folder still
read-only, with one writable door (`built/`) for a basemap built in the Conduit, laid over it as
ADR-067's upload door is; and no generated file holding a map key."""

from __future__ import annotations

from pathlib import Path

import yaml
from harness.render import load_config, render

from tests.harness.test_render import FIXTURE_CONFIG, _fake_resolver


def _api(tmp_path: Path) -> tuple[dict[str, object], dict[str, object]]:
    path = tmp_path / "osprey.yaml"
    path.write_text(FIXTURE_CONFIG, encoding="utf-8")
    rendered = render(load_config(path), resolver=_fake_resolver)
    compose = yaml.safe_load(rendered.artefacts["compose.yaml"])
    return compose["services"]["api"], compose.get("volumes") or {}


def test_the_maps_file_has_a_volume_of_its_own_named_to_the_conduit(tmp_path: Path) -> None:
    api, volumes = _api(tmp_path)
    assert "map-settings:/run/osprey/map-settings" in api["volumes"]  # type: ignore[operator]
    assert api["environment"]["OSPREY_MAP_SETTINGS_DIR"] == "/run/osprey/map-settings"  # type: ignore[index]
    assert "map-settings" in volumes


def test_the_tiles_folder_stays_read_only_with_one_writable_door_for_a_build(
    tmp_path: Path,
) -> None:
    api, _ = _api(tmp_path)
    mounts = [str(m) for m in api["volumes"]]  # type: ignore[attr-defined]
    root = [m for m in mounts if m.split(":")[1:2] == ["/data/tiles"]]
    built = [m for m in mounts if m.split(":")[1:2] == ["/data/tiles/built"]]
    assert len(root) == 1 and root[0].endswith(":ro")
    assert len(built) == 1 and not built[0].endswith(":ro")
