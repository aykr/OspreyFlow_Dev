"""`scripts/build_local_basemap.py`'s stages that need no live store —
`docs/00_ARCHITECTURE.md` §1.2's tier-1 "one-button" pipeline,
`docs/07_BUILD_PLAN.md` Phase 5. The full orchestration against a live
`GraphPort` is `tests/ingest/test_build_local_basemap_end_to_end.py`,
kept separate so this file stays inside `make test`'s no-live-store
boundary (`tests/ingest` is what that target ignores) while that one sits
outside it, needing ArcadeDB.

`download_extract`/`run_planetiler` are tested for argument construction
and error handling only, with the real network/subprocess call injected
out (the module's own docstring explains why: neither can be a CI
dependency).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from scripts.build_local_basemap import (
    PlanetilerNotAvailableError,
    UnknownRegionError,
    download_extract,
    register_local_provider,
    run_planetiler,
)
from services.api.mapconfig_loader import load_map_config

# --- download_extract --------------------------------------------------------


def test_download_extract_rejects_an_unknown_region_by_name(tmp_path: Path) -> None:
    with pytest.raises(UnknownRegionError, match="not-a-real-region"):
        download_extract(
            "not-a-real-region", tmp_path / "extract.osm.pbf", http_get=lambda url: b""
        )


def test_download_extract_fetches_the_regions_own_url_and_writes_the_bytes(tmp_path: Path) -> None:
    captured_urls: list[str] = []

    def fake_get(url: str) -> bytes:
        captured_urls.append(url)
        return b"fake-pbf-bytes"

    dest = tmp_path / "nested" / "great-britain.osm.pbf"
    download_extract("great-britain", dest, http_get=fake_get)

    assert captured_urls == ["https://download.geofabrik.de/europe/great-britain-latest.osm.pbf"]
    assert dest.read_bytes() == b"fake-pbf-bytes"


# --- run_planetiler -----------------------------------------------------------


def test_run_planetiler_refuses_to_silently_skip_a_missing_jar(tmp_path: Path) -> None:
    with pytest.raises(PlanetilerNotAvailableError, match="not found"):
        run_planetiler(
            tmp_path / "extract.osm.pbf",
            tmp_path / "out.pmtiles",
            jar_path=tmp_path / "does-not-exist.jar",
        )


def test_run_planetiler_invokes_java_with_the_expected_arguments(tmp_path: Path) -> None:
    jar_path = tmp_path / "planetiler.jar"
    jar_path.write_bytes(b"")  # only existence is checked
    osm_path = tmp_path / "extract.osm.pbf"
    output_path = tmp_path / "out.pmtiles"
    captured: list[list[str]] = []

    def fake_run(argv: list[str], *, check: bool) -> subprocess.CompletedProcess[bytes]:
        captured.append(argv)
        assert check is True
        return subprocess.CompletedProcess(argv, 0)

    run_planetiler(osm_path, output_path, jar_path=jar_path, subprocess_run=fake_run)

    assert captured == [
        [
            "java", "-jar", str(jar_path),
            f"--osm-path={osm_path}", f"--output={output_path}", "--force",
        ]
    ]


# --- register_local_provider ---------------------------------------------------


def test_register_local_provider_creates_a_fresh_config_when_none_exists(tmp_path: Path) -> None:
    config_path = tmp_path / "osprey.yaml"
    config = register_local_provider(
        config_path, provider_id="osm-local-gb", label="OpenStreetMap (GB)",
        pmtiles_path=tmp_path / "gb.pmtiles",
    )

    assert config.default == "osm-local-gb"
    reloaded = load_map_config(config_path)
    assert reloaded.providers[0].id == "osm-local-gb"
    assert reloaded.providers[0].licence.client_scope == "open"


def test_register_local_provider_replaces_an_entry_with_the_same_id(tmp_path: Path) -> None:
    config_path = tmp_path / "osprey.yaml"
    register_local_provider(
        config_path, provider_id="osm-local-gb", label="v1",
        pmtiles_path=tmp_path / "v1.pmtiles",
    )
    register_local_provider(
        config_path, provider_id="osm-local-gb", label="v2",
        pmtiles_path=tmp_path / "v2.pmtiles",
    )

    reloaded = load_map_config(config_path)
    assert len(reloaded.providers) == 1
    assert reloaded.providers[0].label == "v2"


def test_register_local_provider_appends_alongside_an_existing_provider(tmp_path: Path) -> None:
    config_path = tmp_path / "osprey.yaml"
    register_local_provider(
        config_path, provider_id="osm-local-gb", label="GB",
        pmtiles_path=tmp_path / "gb.pmtiles",
    )
    register_local_provider(
        config_path, provider_id="osm-local-ca", label="California",
        pmtiles_path=tmp_path / "ca.pmtiles", make_default=False,
    )

    reloaded = load_map_config(config_path)
    assert {p.id for p in reloaded.providers} == {"osm-local-gb", "osm-local-ca"}
    assert reloaded.default == "osm-local-gb"  # the second call did not steal the default
