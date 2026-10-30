"""ADR-054 Amendment 6: a relative `components.storage.ingest` or `tiles` is read from the product
folder (the one holding `osprey.yaml`), the same way by Compose and by the harness's own checks.

Compose resolves a relative bind source from the folder its `compose.yaml` is in, which is always
`<product>/deploy/generated/<name>/`; the preflight checks are run from wherever the operator is.
Each case below fails if the two ever read the same setting differently, or if a relative path is
written into `compose.yaml` the way it was given (which Compose would read from the generated
folder, three levels below the product folder).
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
import yaml
from harness.preflight import basemap
from harness.preflight.context import PreflightContext
from harness.render import (
    GLYPHS_CONTAINER_PATH,
    INGEST_CONTAINER_PATH,
    INGEST_UPLOAD_SUBDIR,
    render,
    write,
)
from pydantic import ValidationError

from schemas.deployment import TILES_CONTAINER_PATH, OspreyConfig
from tests.harness.test_cluster_render import cluster_config

GIB = 1024**3

MAP = {
    "default": "osm-local",
    "providers": [
        {
            "id": "osm-local",
            "label": "OpenStreetMap",
            "kind": "vector",
            "licence": {"id": "ODbL", "redistributable": True, "client_scope": "open"},
            "source": "file:///data/tiles/osm-local.pmtiles",
            "variables": {},
            "proxy": "none",
            "style": "bundled:osprey-dark",
            "attribution": "© OpenStreetMap contributors",
        }
    ],
}


def _config(ingest: str, tiles: str) -> OspreyConfig:
    raw: dict[str, object] = {
        "components": {"storage": {"ingest": ingest, "tiles": tiles}},
        "map": MAP,
    }
    return OspreyConfig.model_validate(raw)


def _rendered(config: OspreyConfig, product: Path) -> Path:
    out = product / "deploy" / "generated" / config.profile.value
    write(render(config, resolver=lambda _i: "sha256:" + "0" * 64), out)
    return out


def _bind_sources(out: Path) -> dict[str, Path]:
    """Each host folder `compose.yaml` mounts, keyed by its container path, resolved the way Compose
    resolves it: a relative source from the folder the file is in."""
    compose = yaml.safe_load((out / "compose.yaml").read_text(encoding="utf-8"))
    found: dict[str, Path] = {}
    for service in compose["services"].values():
        for volume in service.get("volumes", []):
            source, target = volume.split(":")[:2]
            if source.startswith((".", "/")) and not source.startswith("./glass.json"):
                found[target] = Path(os.path.normpath(out / source))
    return found


def test_a_relative_ingest_and_tiles_are_mounted_from_the_product_folder(tmp_path: Path) -> None:
    product = tmp_path / "product"
    out = _rendered(_config("../Data/ingest", "../Data/basemap"), product)

    sources = _bind_sources(out)

    uploaded = f"{INGEST_CONTAINER_PATH}/{INGEST_UPLOAD_SUBDIR}"
    assert sources[INGEST_CONTAINER_PATH] == tmp_path / "Data" / "ingest"
    assert sources[uploaded] == tmp_path / "Data" / "ingest" / INGEST_UPLOAD_SUBDIR
    assert sources[TILES_CONTAINER_PATH] == tmp_path / "Data" / "basemap"
    assert sources[GLYPHS_CONTAINER_PATH] == tmp_path / "Data" / "basemap" / "fonts"


def test_an_absolute_path_is_rendered_unchanged(tmp_path: Path) -> None:
    out = _rendered(_config("/srv/ingest", "/srv/tiles"), tmp_path / "product")

    sources = _bind_sources(out)

    assert sources[INGEST_CONTAINER_PATH] == Path("/srv/ingest")
    assert sources[TILES_CONTAINER_PATH] == Path("/srv/tiles")


def test_no_rendered_file_names_the_folder_a_relative_path_resolves_to(tmp_path: Path) -> None:
    """The point of the amendment for the bundle gate: nothing rendered carries the host's own
    absolute path when `osprey.yaml` gave a relative one."""
    product = tmp_path / "product"
    out = _rendered(_config("../Data/ingest", "../Data/basemap"), product)

    for path in out.iterdir():
        if path.is_file():
            assert str(tmp_path) not in path.read_text(encoding="utf-8"), path.name


def test_the_basemap_check_reads_a_relative_tiles_folder_from_the_product_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Run from an unrelated folder, as `ospreyflow doctor` may be: the check must still find the
    tiles where Compose mounts them from."""
    product = tmp_path / "product"
    config = _config("../Data/ingest", "../Data/basemap")
    out = _rendered(config, product)
    tiles = tmp_path / "Data" / "basemap"
    tiles.mkdir(parents=True)
    (tiles / "osm-local.pmtiles").write_bytes(b"PMTiles")
    # Two levels down, so `..` from here cannot land on the product folder's sibling by chance.
    elsewhere = tmp_path / "some" / "other" / "folder"
    elsewhere.mkdir(parents=True)
    monkeypatch.chdir(elsewhere)
    context = PreflightContext(
        config=config,
        out_dir=out,
        memory_probe=lambda: 32 * GIB,
        disk_probe=lambda _path: (100 * GIB, 0, 100 * GIB),
        host_memory_probe=lambda: 32 * GIB,
        host_disk_probe=lambda _path: (100 * GIB, 0, 100 * GIB),
    )

    result = basemap.check(context)

    assert "does not exist yet" not in (result.what_is_wrong or ""), result


def test_the_cluster_profile_refuses_a_relative_host_folder() -> None:
    """On a cluster the folders are on other machines; there is no product folder to read from."""
    with pytest.raises(ValidationError, match="components.storage.ingest"):
        cluster_config(
            components={
                "analytics_engine": "clickhouse",
                "storage": {"ingest": "../Data/ingest", "tiles": "/srv/tiles"},
            }
        )


def test_the_cluster_profile_takes_an_absolute_host_folder() -> None:
    """The refusal above is for the relative path, not for any storage setting on a cluster."""
    cluster_config(
        components={
            "analytics_engine": "clickhouse",
            "storage": {"ingest": "/srv/ingest", "tiles": "/srv/tiles"},
        }
    )
