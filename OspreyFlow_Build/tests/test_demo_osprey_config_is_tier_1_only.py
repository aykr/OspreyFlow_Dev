"""Standing rule 9: "the demo and CI run on tier 1
providers only" — enforced by rejecting any non-`open` provider in the
committed `osprey.yaml`, the same way `tests/licence_check` proves the
dependency-licence gate against a fixture lockfile rather than only
documenting it. This file is the guard for the one committed config;
`tools/osprey_bundle.py`'s own refusal-by-name mechanism (Phase 5
Checkpoint 3a) is proved separately against a fixture config in
`tests/test_osprey_bundle.py`, since bundling is a general capability this
demo config never needs to exercise (every entry here is already open).
"""

from __future__ import annotations

from pathlib import Path

from services.api.mapconfig_loader import load_map_config
from tools.layout import REPO as _REPO

OSPREY_YAML = _REPO / "osprey.yaml"


def test_every_provider_in_the_committed_config_is_open_and_redistributable() -> None:
    config = load_map_config(OSPREY_YAML)
    assert config.providers  # not vacuously true
    for provider in config.providers:
        assert provider.licence.client_scope == "open", provider.id
        assert provider.licence.redistributable is True, provider.id


def test_the_default_provider_is_tier_1_local_and_needs_no_credential() -> None:
    config = load_map_config(OSPREY_YAML)
    default = next(p for p in config.providers if p.id == config.default)
    assert default.credential is None
    assert default.proxy == "none"
    assert default.source is not None and default.source.startswith("file://")


def test_no_maps_file_is_committed_so_the_demo_and_ci_start_from_this_config() -> None:
    """ADR-147: a deployment's maps file (`maps.yaml`, the Conduit's own volume) replaces
    `osprey.yaml`'s `map:` once *Admin › Maps* changes it. One committed anywhere (a demo pack, a
    fixture, a seed) could carry a non-open provider into the demo or CI past the two checks above,
    so none is; the service's own tests write theirs to a temporary folder."""
    import subprocess

    tracked = subprocess.run(
        ["git", "ls-files"], cwd=_REPO, capture_output=True, text=True, check=True
    ).stdout.splitlines()
    assert [p for p in tracked if p.rsplit("/", 1)[-1] in {"maps.yaml", "map-keys.yaml"}] == []


def test_a_conduit_with_no_maps_file_serves_exactly_this_config(tmp_path: Path) -> None:
    from services.api.map_admin import InMemoryMapAdminAudit, MapAdmin, MapKeyFile, MapSettingsFile

    installed = load_map_config(OSPREY_YAML)
    admin = MapAdmin(
        installed=installed, settings_file=MapSettingsFile(tmp_path), key_file=MapKeyFile(tmp_path),
        audit=InMemoryMapAdminAudit(), tiles_root=tmp_path,
    )  # fmt: skip
    assert admin.config() == installed
    assert all(p.tier in (1, 2) and p.key_state == "none" for p in admin.view().providers)
