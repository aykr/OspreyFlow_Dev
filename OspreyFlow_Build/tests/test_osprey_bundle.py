"""`tools/osprey_bundle.py` — `spec/00_ARCHITECTURE.md` §1.2's "the
bundle step refuses to package tiles or gazetteers whose profile says
`redistributable: false`, and names them". Proves the refusal against a fixture config that
deliberately violates it — the same "prove the gate with a fixture that
intentionally violates it" pattern `tests/licence_check/
test_gpl_rejection.py` already established for package licences (a
different concern, reused only as a pattern, no shared code).
"""

from __future__ import annotations

import tarfile
from pathlib import Path

import pytest
from harness.render import load_config
from services.api.mapconfig_loader import load_map_config

from schemas.deployment import OspreyConfig
from tools.layout import REPO as REPO_ROOT
from tools.osprey_bundle import (
    BundleResult,
    NonRedistributableProviderError,
    bundle_map_providers,
)

FIXTURE_ALL_OPEN = """
map:
  default: osm-local
  providers:
    - id: osm-local
      label: "OpenStreetMap"
      kind: vector
      source: file:///data/tiles/gb-osm.pmtiles
      style: bundled:osprey-dark
      attribution: "© OpenStreetMap contributors"
      licence: {id: ODbL, redistributable: true, client_scope: open}
    - id: os-open-zoomstack-local
      label: "OS Open Zoomstack"
      kind: vector
      source: file:///data/tiles/os-open-zoomstack.pmtiles
      style: bundled:osprey-dark
      attribution: "Contains OS data (c) Crown copyright and database right"
      licence: {id: OGL-UK-3.0, redistributable: true, client_scope: open}
"""

FIXTURE_ONE_NON_REDISTRIBUTABLE = """
map:
  default: osm-local
  providers:
    - id: osm-local
      label: "OpenStreetMap"
      kind: vector
      source: file:///data/tiles/gb-osm.pmtiles
      style: bundled:osprey-dark
      attribution: "© OpenStreetMap contributors"
      licence: {id: ODbL, redistributable: true, client_scope: open}
    - id: os-ngd
      label: "OS NGD"
      kind: vector
      source: "os-datahub://ngd/tiles"
      credential: env:OS_DATAHUB_API_KEY
      proxy: required
      attribution: "Contains OS data (c) Crown copyright"
      licence: {id: PSGA, redistributable: false, client_scope: per-deployment}
"""


def test_bundles_every_provider_when_all_are_redistributable(tmp_path: Path) -> None:
    path = tmp_path / "osprey.yaml"
    path.write_text(FIXTURE_ALL_OPEN)
    config = load_map_config(path)

    result = bundle_map_providers(config)

    assert isinstance(result, BundleResult)
    assert set(result.bundled_provider_ids) == {"osm-local", "os-open-zoomstack-local"}


def test_refuses_the_whole_bundle_and_names_the_non_redistributable_provider(
    tmp_path: Path,
) -> None:
    path = tmp_path / "osprey.yaml"
    path.write_text(FIXTURE_ONE_NON_REDISTRIBUTABLE)
    config = load_map_config(path)

    with pytest.raises(NonRedistributableProviderError) as exc_info:
        bundle_map_providers(config)

    assert exc_info.value.refused_provider_ids == ("os-ngd",)
    assert "os-ngd" in str(exc_info.value)


# --- build_bundle / make_tarball (06_DECISIONS.md ADR-049 Stage 2 §5b) ---------------------------


def _fake_resolver(_image: str) -> str:
    return "sha256:" + "0" * 64


def _fake_docker_save(_image: str, out_path: Path) -> None:
    out_path.write_bytes(b"not a real image archive, just a marker for the test")


def _fake_docker_build_docs_layer(_base_image: str, _docs_site_dir: Path, _tag: str) -> None:
    pass


def _fake_docker_tag(_local_tag: str, _pull_mode_tag: str) -> None:
    pass


@pytest.fixture
def bundle_config() -> OspreyConfig:
    return load_config(REPO_ROOT / "osprey.yaml")


def test_build_bundle_stages_every_expected_file(
    tmp_path: Path, bundle_config: OspreyConfig
) -> None:
    from tools.osprey_bundle import build_bundle

    manifest = build_bundle(
        bundle_config,
        tmp_path / "staging",
        example_config_text="map:\n  default: osm-local\n",
        resolver=_fake_resolver,
    )

    expected = {
        "compose.yaml",
        "deployment.env",
        "versions.lock",
        "RUNBOOK.md",
        "LICENSE",
        "NOTICE",
        "osprey.schema.json",
        "osprey.yaml.example",
        "docs-site/index.html",
        "docs-site/operator-guide.html",
        "docs-site/analyst-guide.html",
        "docs-site/preflight-reference.html",
    }
    assert expected <= set(manifest.files)
    assert manifest.image_archives == ()


def test_build_bundle_with_images_archives_every_service(
    tmp_path: Path, bundle_config: OspreyConfig
) -> None:
    from tools.osprey_bundle import build_bundle

    manifest = build_bundle(
        bundle_config,
        tmp_path / "staging",
        example_config_text="map:\n  default: osm-local\n",
        include_images=True,
        resolver=_fake_resolver,
        docker_save=_fake_docker_save,
        docker_build_docs_layer=_fake_docker_build_docs_layer,
        docker_tag=_fake_docker_tag,
    )

    assert "images/api.tar" in manifest.image_archives
    assert "images/workspace.tar" in manifest.image_archives
    assert (tmp_path / "staging" / "images" / "api.tar").is_file()


def test_build_bundle_with_images_also_archives_the_harness_bootstrap_image(
    tmp_path: Path, bundle_config: OspreyConfig
) -> None:
    """Item 3 of Stage 2 §5b's own brief: "Include it in the bundle's image set." Not a compose
    service (`harness.render.service_images` never names it), and not archived unless named here
    explicitly — this is the test that fails if that naming is ever dropped."""
    from tools.osprey_bundle import HARNESS_IMAGE, build_bundle

    saved: list[str] = []

    def _recording_docker_save(image: str, out_path: Path) -> None:
        saved.append(image)
        out_path.write_bytes(b"not a real image archive, just a marker for the test")

    manifest = build_bundle(
        bundle_config,
        tmp_path / "staging",
        example_config_text="map:\n  default: osm-local\n",
        include_images=True,
        resolver=_fake_resolver,
        docker_save=_recording_docker_save,
        docker_build_docs_layer=_fake_docker_build_docs_layer,
        docker_tag=_fake_docker_tag,
    )

    assert "images/harness.tar" in manifest.image_archives
    assert HARNESS_IMAGE in saved
    assert (tmp_path / "staging" / "images" / "harness.tar").is_file()


def test_build_bundle_with_images_layers_the_docs_site_onto_the_workspace_image_only(
    tmp_path: Path, bundle_config: OspreyConfig
) -> None:
    """Item 3's "into both the tarball and the workspace image at /docs" — proves the augmentation
    is wired to the real command and scoped to exactly the one service it names, not every image."""
    from tools.osprey_bundle import build_bundle

    calls: list[tuple[str, str]] = []

    def _recording_docker_build_docs_layer(base_image: str, _docs_site_dir: Path, tag: str) -> None:
        calls.append((base_image, tag))

    build_bundle(
        bundle_config,
        tmp_path / "staging",
        example_config_text="map:\n  default: osm-local\n",
        include_images=True,
        resolver=_fake_resolver,
        docker_save=_fake_docker_save,
        docker_build_docs_layer=_recording_docker_build_docs_layer,
        docker_tag=_fake_docker_tag,
    )

    # Round 07: `entry.image` for an owned service is now the pull-mode reference
    # (`bundle_config` declares no `components.source_path`) — the tag `docker_tag` (faked here)
    # would have retagged the local build to, not the local build tag itself.
    from harness.render import OWNED_IMAGE_REGISTRY

    assert len(calls) == 1
    base_image, tag = calls[0]
    assert base_image == tag
    assert base_image.startswith(f"{OWNED_IMAGE_REGISTRY}/workspace:")


def test_build_bundle_excludes_stray_os_marker_files_from_the_manifest(
    tmp_path: Path, bundle_config: OspreyConfig
) -> None:
    """The real shape of a defect the real `--images` exit test found, not a fabricated one: this
    machine's own OS/sync tooling writes a 0-byte `Icon\\r` (macOS's custom-folder-icon marker) into
    any directory it touches, and an unfiltered `staging_dir.rglob("*")` staged it straight into a
    real bundle tarball. Plants the exact file this build actually produced, in the exact place
    (the staging root and inside `docs-site/`, both hit in the real build) that let it through."""
    from tools.osprey_bundle import build_bundle

    staging_dir = tmp_path / "staging"
    staging_dir.mkdir()
    (staging_dir / "Icon\r").write_bytes(b"")

    manifest = build_bundle(
        bundle_config,
        staging_dir,
        example_config_text="map:\n  default: osm-local\n",
        resolver=_fake_resolver,
    )

    assert "Icon\r" not in manifest.files
    assert not any(name.endswith("Icon\r") for name in manifest.files)


def test_make_tarball_excludes_stray_os_marker_files(
    tmp_path: Path, bundle_config: OspreyConfig
) -> None:
    from tools.osprey_bundle import build_bundle, make_tarball

    staging_dir = tmp_path / "staging"
    build_bundle(
        bundle_config,
        staging_dir,
        example_config_text="map:\n  default: osm-local\n",
        resolver=_fake_resolver,
    )
    (staging_dir / "docs-site" / "Icon\r").write_bytes(b"")

    tarball_path = make_tarball(staging_dir, tmp_path / "bundle.tar.gz")

    with tarfile.open(tarball_path) as tar:
        names = tar.getnames()
    assert not any(name.endswith("Icon\r") for name in names)


def test_build_bundle_refuses_a_bundle_containing_a_private_tree_file(
    tmp_path: Path, bundle_config: OspreyConfig
) -> None:
    """The planted violation, the real shape: something stages a private-tree file into the
    bundle's own directory before `build_bundle` finishes — proving the packaging gate is actually
    wired into the real command, not only unit-tested in isolation against a fabricated path list
    (`tests/packaging/test_internal_demo_exclusion.py`)."""
    from tools.osprey_bundle import build_bundle

    staging_dir = tmp_path / "staging"
    staging_dir.mkdir()
    (staging_dir / "CLAUDE.md").write_text("leaked", encoding="utf-8")

    with pytest.raises(RuntimeError, match="refusing to package"):
        build_bundle(
            bundle_config,
            staging_dir,
            example_config_text="map:\n  default: osm-local\n",
            resolver=_fake_resolver,
        )


def test_make_tarball_produces_a_real_readable_archive(
    tmp_path: Path, bundle_config: OspreyConfig
) -> None:
    from tools.osprey_bundle import build_bundle, make_tarball

    staging_dir = tmp_path / "staging"
    manifest = build_bundle(
        bundle_config,
        staging_dir,
        example_config_text="map:\n  default: osm-local\n",
        resolver=_fake_resolver,
    )

    tarball_path = make_tarball(staging_dir, tmp_path / "bundle.tar.gz")

    with tarfile.open(tarball_path) as tar:
        names = set(tar.getnames())
    assert set(manifest.files) <= names


def test_make_tarball_is_uncompressed_when_it_carries_image_archives(
    tmp_path: Path, bundle_config: OspreyConfig
) -> None:
    """Compressing already-compressed image-layer data twice wastes real time on a multi-gigabyte
    bundle — this module's own docstring names the reasoning; this test proves the branch."""
    from tools.osprey_bundle import build_bundle, make_tarball

    staging_dir = tmp_path / "staging"
    build_bundle(
        bundle_config,
        staging_dir,
        example_config_text="map:\n  default: osm-local\n",
        include_images=True,
        resolver=_fake_resolver,
        docker_save=_fake_docker_save,
        docker_build_docs_layer=_fake_docker_build_docs_layer,
        docker_tag=_fake_docker_tag,
    )

    tarball_path = make_tarball(staging_dir, tmp_path / "bundle.tar")

    with open(tarball_path, "rb") as f:
        magic = f.read(2)
    assert magic != b"\x1f\x8b", "the tarball is gzip-compressed despite carrying image archives"


def test_a_missing_local_image_is_refused_by_name_not_by_a_bare_docker_tag_traceback() -> None:
    """**Round 13b's own red-then-green for `_docker_tag`'s enforced precondition.** Before it,
    `--images` against a checkout where an owned image had never been built died with
    `subprocess.CalledProcessError: Command '['docker', 'tag', 'osprey/ingest:local', ...]'
    returned non-zero exit status 1` — a traceback naming a `docker` invocation and nothing an
    operator could act on. Found for real running `tests/harness/test_bundle_exit_test.py` from a
    fresh clone: `harness.apply --build` builds the services a running `local-lite` starts, which
    excludes `ingest` and the harness image, so the precondition three comments in that module
    state was unmet with nothing enforcing it.

    The planted violation is the real shape, per `CLAUDE.md` rule 15: a tag that genuinely does
    not exist in the local daemon, passed to the real `_docker_tag`, so it is the real `docker
    tag` that refuses — not a stub standing in for it.
    """
    import pytest

    from tools.osprey_bundle import MissingLocalImageError, _docker_tag

    absent = "osprey/no-such-service:definitely-not-built-13b"
    with pytest.raises(MissingLocalImageError) as refused:
        _docker_tag(absent, "ghcr.io/ospreyflow/no-such-service:test")
    message = str(refused.value)
    assert absent in message, message
    assert "docker build" in message, "the refusal must name the command that fixes it"
