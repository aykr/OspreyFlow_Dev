"""`harness.apply --images-from LOCK` (ADR-114 Amendment 8 point 10, B5e): an install from a
release runs exactly the images its verified lock names. The owned images' registry is taken from
the lock (a user repository's own `ghcr.io/<owner>`), and every image is pinned by digest before
anything starts. A lock that names no owned image is refused."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from harness.apply import ApplyFailed, _parse_args, pin_release_images, release_registry

D = "sha256:" + "a" * 64
LOCK = "# GENERATED\n" + yaml.safe_dump({"images": [
    {"service": "api", "repository": "ghcr.io/acme/api", "tag": "c0ffee", "digest": D},
    {"service": "workspace", "repository": "ghcr.io/acme/workspace", "tag": "c0ffee", "digest": D},
    {"service": "arcadedb", "repository": "arcadedata/arcadedb", "tag": "26.10.1", "digest": D},
]}, sort_keys=False)  # fmt: skip


def test_the_owned_images_registry_is_the_lock_s() -> None:
    assert release_registry(LOCK) == "ghcr.io/acme"


def test_a_lock_with_no_owned_image_is_refused() -> None:
    lock = "images:\n- {service: arcadedb, repository: arcadedata/arcadedb, digest: x}\n"
    with pytest.raises(ApplyFailed, match="names no image of the Conduit"):
        release_registry(lock)


def test_every_image_is_pinned_by_the_lock_s_digest_before_anything_starts(tmp_path: Path) -> None:
    (tmp_path / "compose.yaml").write_text("# banner\n" + yaml.safe_dump({"name": "x", "services": {
        "api": {"image": "ghcr.io/acme/api:c0ffee"},
        "report-sync": {"image": "ghcr.io/acme/api:c0ffee"},
        "arcadedb": {"image": "arcadedata/arcadedb:26.10.1"},
        "valkey": {"image": "valkey/valkey:8"},
    }}))  # fmt: skip
    lock = tmp_path / "release.lock"
    lock.write_text(LOCK)
    pin_release_images(tmp_path, lock)
    services = yaml.safe_load((tmp_path / "compose.yaml").read_text())["services"]
    assert services["api"]["image"] == f"ghcr.io/acme/api@{D}"
    assert services["report-sync"]["image"] == f"ghcr.io/acme/api@{D}"
    assert services["arcadedb"]["image"] == f"arcadedata/arcadedb@{D}"
    assert services["valkey"]["image"] == "valkey/valkey:8"  # not in the lock: untouched
    assert (tmp_path / "versions.lock").read_text() == LOCK


def test_the_flag_is_read() -> None:
    assert _parse_args(["--images-from", "/x/release.lock"]).images_from == Path("/x/release.lock")
    assert _parse_args([]).images_from is None


def test_the_render_step_pins_the_release_s_images_when_given_its_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """What `apply`'s step 1 writes: the release's digests, not the render's tags."""
    from harness.apply import render_deployment
    from harness.render import load_config

    from tests.harness.test_render import FIXTURE_CONFIG

    path = tmp_path / "osprey.yaml"
    path.write_text(FIXTURE_CONFIG, encoding="utf-8")
    lock = tmp_path / "release.lock"
    lock.write_text(LOCK)
    monkeypatch.setenv("OSPREY_IMAGE_REGISTRY", "ghcr.io/acme")
    render_deployment(load_config(path), tmp_path / "out", images_from=lock)
    services = yaml.safe_load((tmp_path / "out" / "compose.yaml").read_text())["services"]
    assert services["api"]["image"] == f"ghcr.io/acme/api@{D}"
    assert services["workspace"]["image"] == f"ghcr.io/acme/workspace@{D}"
    render_deployment(load_config(path), tmp_path / "plain", images_from=None)
    plain = yaml.safe_load((tmp_path / "plain" / "compose.yaml").read_text())["services"]
    assert "@" not in plain["api"]["image"]

