"""`scripts/build_local_basemap.py`'s stages that need no live store —
`spec/00_ARCHITECTURE.md` §1.2's tier-1 "one-button" pipeline.
The full orchestration against a live
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
import yaml
from scripts.build_local_basemap import (
    GEOFABRIK_REGIONS,
    UNREACHABLE_DATABASE,
    NotAnOsmExtractError,
    PlanetilerNotAvailableError,
    UnknownRegionError,
    build_tiles_only,
    download_extract,
    register_local_provider,
    resolve_extract,
    run_planetiler,
    set_tiles_root,
)
from services.api.mapconfig_loader import load_map_config

#: **The real first bytes of a real Geofabrik extract**, copied from the head of
#: `europe/united-kingdom/england/rutland-latest.osm.pbf` on 26 September 2026: a 4-byte
#: big-endian `BlobHeader` length (`0x0000000e`) then the protobuf carrying `OSMHeader`. Used
#: instead of the `b"fake-pbf-bytes"` this file's own fixture returned until 26 September,
#: which was a shape the real server never emits — `CLAUDE.md` rule 15's "a fixture standing in
#: for an external dependency models that dependency's refusals, not only its grants".
REAL_PBF_PREFIX = bytes.fromhex("0000000e0a094f534d48656164657218c20110b4011abc01789c")

#: **And what that same server really returns for an extract path it no longer serves** — the
#: head of the HTML home page Geofabrik 302s a retired sub-region path to, captured the same day
#: from `europe/great-britain/england/rutland-latest.osm.pbf`. It arrives with a *200* after
#: `httpx`'s own `follow_redirects=True`, which is precisely why `raise_for_status()` could not
#: catch it and `_assert_is_osm_pbf` has to.
REAL_GEOFABRIK_REDIRECT_HTML = (
    b'<!DOCTYPE html>\n<html>\n  <head>\n<meta charset="UTF-8">\n'
    b'<link rel="icon" href="https://www.geofabrik.de/favicon.ico" />\n'
    b'<meta name="description" content="Download OpenStreetMap data for OpenStreetMap Data '
    b'Extracts for self-hosting or data analysis.">\n'
)


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
        return REAL_PBF_PREFIX

    dest = tmp_path / "nested" / "great-britain.osm.pbf"
    download_extract("great-britain", dest, http_get=fake_get)

    assert captured_urls == ["https://download.geofabrik.de/europe/great-britain-latest.osm.pbf"]
    assert dest.read_bytes() == REAL_PBF_PREFIX


def test_download_extract_rejects_geofabriks_own_redirect_to_html_and_writes_nothing(
    tmp_path: Path,
) -> None:
    """The defect found building the basemap for real on 26 September 2026, planted in the shape
    the real dependency actually produced: a retired extract path answering 200-with-HTML after a
    followed redirect. Before `_assert_is_osm_pbf`, this wrote the HTML to disk under a
    `.osm.pbf` name and returned it as a success, and planetiler failed minutes later with a parse
    error naming neither the region nor the URL.

    Asserting the file is *absent*, not merely that the call raised, is the load-bearing half: a
    rejected download that still leaves a plausible-looking artefact behind is a trap for the next
    stage, which takes the path on trust."""
    dest = tmp_path / "rutland.osm.pbf"

    with pytest.raises(NotAnOsmExtractError) as excinfo:
        download_extract("rutland", dest, http_get=lambda url: REAL_GEOFABRIK_REDIRECT_HTML)

    # The region and the URL both named, so the message is actionable without a second round trip.
    assert "rutland" in str(excinfo.value)
    assert "download.geofabrik.de" in str(excinfo.value)
    assert not dest.exists(), "a rejected download must leave no file behind"


def test_every_configured_region_url_is_one_geofabrik_still_serves_by_shape(
    tmp_path: Path,
) -> None:
    """Not a network call — the offline half of the same finding. Geofabrik renamed
    `great-britain` to `united-kingdom`; the top-level legacy alias still resolves, but no
    *sub*-extract under `great-britain/` does. Any region whose URL reaches below the top level
    must therefore use the current name, or it is a URL that answers 200-with-HTML and only fails
    once a real build is attempted."""
    for region, url in GEOFABRIK_REGIONS.items():
        assert url.startswith("https://download.geofabrik.de/"), (region, url)
        assert url.endswith("-latest.osm.pbf"), (region, url)
        path = url.removeprefix("https://download.geofabrik.de/")
        if path.count("/") > 1:
            assert "great-britain/" not in path, (
                f"{region}: a sub-extract under the retired 'great-britain/' prefix — Geofabrik "
                f"answers that with a redirect to its home page, not a 404. Use "
                f"'europe/united-kingdom/...'. Got: {url}"
            )


# --- run_planetiler -----------------------------------------------------------


def test_run_planetiler_refuses_to_silently_skip_a_missing_jar(tmp_path: Path) -> None:
    with pytest.raises(PlanetilerNotAvailableError, match="not found"):
        run_planetiler(
            tmp_path / "extract.osm.pbf",
            tmp_path / "out.pmtiles",
            jar_path=tmp_path / "does-not-exist.jar",
        )


def test_run_planetiler_invokes_java_with_the_expected_arguments(tmp_path: Path) -> None:
    """**The expected argument list was wrong from Phase 5 until 26 September 2026, and this test
    asserted the wrong one.** It only ever compared `run_planetiler`'s output against a list
    written from the same assumption the function was written from — `scripts/
    build_local_basemap.py`'s own docstring said so outright ("real planetiler CLI flags are
    unverified here") — so it could never have found the fault, exactly `CLAUDE.md` rule 12's
    shape. The first real run failed immediately:

        java.lang.IllegalArgumentException: data/sources/lake_centerline.shp.zip does not exist.
        Run with --download to fetch it

    Both additions below are now checked against a real `planetiler --help`, not assumed:
    `--download` (the OpenMapTiles profile's three auxiliary sources) and an explicit
    `--download_dir` (whose default, `data/sources`, is relative to the working directory — from
    a checkout, this repository's own `data/`).

    This assertion is still argument-construction only, and still cannot prove the flags are
    right; what proves that is a real build, and the one this round ran is recorded in
    `process/demo/2026-09-26/RUNBOOK.md`."""
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
        ["java", "-version"],
        [
            "java", "-jar", str(jar_path),
            f"--osm-path={osm_path}", f"--output={output_path}",
            "--download", f"--download_dir={tmp_path / 'sources'}", "--force",
        ]
    ]
    # The download directory is pinned *under the output directory*, never left to planetiler's
    # own relative default — the half of this fix that a flag-name check alone would not catch.
    assert f"--download_dir={tmp_path / 'sources'}" in captured[1]


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


def test_register_local_provider_credits_openmaptiles_as_well_as_openstreetmap(
    tmp_path: Path,
) -> None:
    """`00_ARCHITECTURE.md` §1.2 principle 3 — "attribution and licence travel with the layer
    [...] because the obligation does" — for the credit planetiler itself says these tiles carry.

    Found 26 September 2026 by reading the real planetiler run's own closing output rather than
    assuming ODbL was the whole story: the tiles this pipeline produces are a CC-BY work of the
    OpenMapTiles profile as well as ODbL OpenStreetMap data, and planetiler prints "Maps made
    with these vector tiles must display a visible credit: © OpenMapTiles © OpenStreetMap
    contributors". Every provider registered before this fix declared only the OSM half.

    Named here rather than left to `scripts/verify_map.py`'s own `check_attribution`, which
    cannot catch this class of fault at all: that check asserts attribution is *present* and
    survives `public_view()` unchanged, so a confidently wrong credit passes it. This is the test
    that fails if the credit regresses."""
    config_path = tmp_path / "osprey.yaml"
    register_local_provider(
        config_path, provider_id="osm-local-rutland", label="OpenStreetMap (rutland)",
        pmtiles_path=tmp_path / "rutland.pmtiles",
    )

    attribution = load_map_config(config_path).providers[0].attribution
    assert attribution is not None
    assert "OpenMapTiles" in attribution, (
        "the OpenMapTiles credit planetiler's own output requires is missing — a basemap built "
        f"by scripts/build_local_basemap.py would ship an incomplete credit line. Got: "
        f"{attribution!r}"
    )
    assert "OpenStreetMap contributors" in attribution, attribution


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


def test_register_local_provider_preserves_other_top_level_keys(tmp_path: Path) -> None:
    """Regression test, 26 September 2026 — found wiring `harness/geospatial.py`'s own real
    caller: a `config_path` that exists with content but no `map:` key yet (the exact shape
    `harness/webapp.py`'s `_write_config` produces before any provider is registered, since
    `OspreyConfig.map` defaults to `None` and is dropped by `exclude_none=True`) used to raise
    `KeyError('map')`, and once that was naively fixed to tolerate a missing key, the function's
    own write path (`{"map": ...}` only) silently discarded every *other* top-level section on
    the very first non-map-only file it was ever called against. Neither case was exercised by
    any test above — each one only ever calls this function on a fresh file or one this same
    function had already written."""
    config_path = tmp_path / "osprey.yaml"
    config_path.write_text(
        "profile: local-lite\ngovernance:\n  identity_provider: keycloak\n", encoding="utf-8"
    )

    register_local_provider(
        config_path, provider_id="osm-local-gb", label="GB", pmtiles_path=tmp_path / "gb.pmtiles"
    )

    raw = yaml.safe_load(config_path.read_text())
    assert raw["profile"] == "local-lite"
    assert raw["governance"]["identity_provider"] == "keycloak"
    reloaded = load_map_config(config_path)
    assert reloaded.providers[0].id == "osm-local-gb"


# --- an extract the owner already has, and a jar that is not one ---------------


def test_an_extract_the_owner_already_has_is_used_and_nothing_is_downloaded(
    tmp_path: Path,
) -> None:
    """Catches a build that fetches a second 2 GB copy of a file that is already on disk: the
    owner downloaded `great-britain-260928.osm.pbf` and the script downloaded it again."""
    have = tmp_path / "great-britain-260928.osm.pbf"
    have.write_bytes(b"pbf")

    def downloader(region: str, dest: Path) -> Path:
        raise AssertionError("must not download when an extract is given")

    used = resolve_extract(
        "great-britain", tmp_path / "out", existing=have, downloader=downloader
    )

    assert used == have


def test_a_missing_extract_is_refused_by_name_rather_than_downloaded_instead(
    tmp_path: Path,
) -> None:
    """A mistyped path must not quietly turn into a multi-gigabyte download."""
    with pytest.raises(NotAnOsmExtractError, match="not found"):
        resolve_extract(
            "great-britain",
            tmp_path / "out",
            existing=tmp_path / "typo.osm.pbf",
            downloader=lambda region, dest: dest,
        )


def test_with_no_extract_given_the_region_is_downloaded_beside_the_output(
    tmp_path: Path,
) -> None:
    fetched: list[Path] = []

    def downloader(region: str, dest: Path) -> Path:
        fetched.append(dest)
        return dest

    used = resolve_extract("rutland", tmp_path / "out", existing=None, downloader=downloader)

    assert used == tmp_path / "out" / "rutland.osm.pbf"
    assert fetched == [used]


def test_run_planetiler_says_when_it_was_given_a_map_extract_instead_of_the_jar(
    tmp_path: Path,
) -> None:
    """The real mistake: `--planetiler-jar great-britain-260928.osm.pbf`. The message must name
    what was passed and what is wanted, not fail inside Java."""
    extract = tmp_path / "great-britain-260928.osm.pbf"
    extract.write_bytes(b"pbf")

    with pytest.raises(PlanetilerNotAvailableError, match=r"not a \.jar"):
        run_planetiler(extract, tmp_path / "out.pmtiles", jar_path=extract)


def test_a_missing_java_is_explained_not_dumped_as_a_traceback(tmp_path: Path) -> None:
    """Seen on macOS: `/usr/bin/java` exists as a stub that exits non-zero with "Unable to locate
    a Java Runtime", so the build died in a `CalledProcessError` traceback from the planetiler
    command. The message must say Java 21 or later is needed, before planetiler is attempted."""
    jar_path = tmp_path / "planetiler.jar"
    jar_path.write_bytes(b"")
    calls: list[list[str]] = []

    def no_java(argv: list[str], *, check: bool) -> subprocess.CompletedProcess[bytes]:
        calls.append(argv)
        raise subprocess.CalledProcessError(1, argv)

    with pytest.raises(PlanetilerNotAvailableError, match=r"Java 21"):
        run_planetiler(
            tmp_path / "e.osm.pbf",
            tmp_path / "o.pmtiles",
            jar_path=jar_path,
            subprocess_run=no_java,
        )
    assert calls == [["java", "-version"]]


def test_the_command_line_prints_the_planetiler_problem_and_exits_non_zero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from scripts.build_local_basemap import main

    extract = tmp_path / "extract.osm.pbf"
    extract.write_bytes(b"pbf")  # given, so nothing is downloaded
    code = main(
        [
            "--region", "great-britain", "--extract", str(extract), "--output-dir", str(tmp_path),
            "--planetiler-jar", str(tmp_path / "missing.jar"), "--tiles-only",
        ]
    )

    assert code == 1
    assert "planetiler jar not found" in capsys.readouterr().err


# --- tiles only: the map without the database ------------------------------------


def test_a_provider_can_be_registered_under_the_path_the_conduit_sees(tmp_path: Path) -> None:
    """The file is built on the host and served from inside a container. The provider's source is
    the container's view of it; registering the host path made the layer unreachable."""
    config_path = tmp_path / "osprey.yaml"
    register_local_provider(
        config_path,
        provider_id="osm-local-gb",
        label="OpenStreetMap (GB)",
        pmtiles_path=tmp_path / "host" / "gb.pmtiles",
        served_path="/data/tiles/gb.pmtiles",
    )

    assert load_map_config(config_path).providers[0].source == "file:///data/tiles/gb.pmtiles"


def test_the_tiles_folder_is_recorded_without_disturbing_the_rest_of_the_config(
    tmp_path: Path,
) -> None:
    """The deployment mounts `components.storage.tiles`; the build has to point it at the folder it
    wrote to, and must not lose the other keys the console wrote (the same fault
    `register_local_provider` once had)."""
    config_path = tmp_path / "osprey.yaml"
    config_path.write_text(
        yaml.safe_dump({"profile": "local-lite", "components": {"storage": {"data": "/d"}}})
    )

    set_tiles_root(config_path, tmp_path / "basemap")

    raw = yaml.safe_load(config_path.read_text())
    assert raw["components"]["storage"]["tiles"] == str((tmp_path / "basemap").resolve())
    assert raw["components"]["storage"]["data"] == "/d"
    assert raw["profile"] == "local-lite"


def test_a_tiles_only_build_never_needs_the_database(tmp_path: Path) -> None:
    """Catches the build that dies on `ConnectError` before any tile exists. `build_tiles_only`
    takes no graph at all, so it cannot reach for one."""
    extract = tmp_path / "great-britain.osm.pbf"
    extract.write_bytes(b"pbf")
    out = tmp_path / "basemap"
    config_path = tmp_path / "osprey.yaml"

    def fake_planetiler(osm: Path, target: Path, *, jar_path: Path) -> Path:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"pmtiles")
        return target

    result = build_tiles_only(
        region="great-britain",
        output_dir=out,
        planetiler_jar_path=tmp_path / "planetiler.jar",
        osprey_config_path=config_path,
        existing_extract=extract,
        planetiler_runner=fake_planetiler,
        progress=lambda _line: None,
    )

    assert result == out / "great-britain.pmtiles"
    raw = yaml.safe_load(config_path.read_text())
    assert raw["map"]["default"] == "osm-local-great-britain"
    assert raw["map"]["providers"][0]["source"] == "file:///data/tiles/great-britain.pmtiles"
    assert raw["components"]["storage"]["tiles"] == str(out.resolve())


def test_an_unreachable_database_is_explained_not_dumped_as_a_traceback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The first real run ended in forty lines of `httpx.ConnectError`. It should say that the
    database is not reachable, why the launched deployment's is not, and the way round it."""
    import argparse
    import asyncio

    import httpx
    from scripts import build_local_basemap as module

    async def refuse(self: object) -> None:
        raise httpx.ConnectError("All connection attempts failed")

    monkeypatch.setattr(module.ArcadeDBClient, "create_database_if_absent", refuse)
    args = argparse.Namespace(
        region="rutland", output_dir=str(tmp_path), planetiler_jar="x.jar", extract=None,
        osprey_config=str(tmp_path / "osprey.yaml"), tiles_only=False,
        principal_id="p", clearance="OFFICIAL", org_unit="u",
    )

    code = asyncio.run(module._run(args))

    assert code == 1
    assert "--tiles-only" in capsys.readouterr().err
    assert "Cannot reach ArcadeDB" in UNREACHABLE_DATABASE
