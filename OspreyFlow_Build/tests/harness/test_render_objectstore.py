"""ADR-114 Amendment 9 points 3 and 3a: the object store is SeaweedFS, on a named volume.

MinIO's public images were withdrawn, so a new install failed at it; and its data lived in an
anonymous volume, which a `down` and `up` replaces with an empty one. The settings found by probing
the real image are each held here, since its defaults run out of volumes by the third bucket.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from harness.render import load_config, render
from tools.layout import CORE

from tests.harness.test_render import FIXTURE_CONFIG, _fake_resolver


def _compose(tmp_path: Path) -> dict[str, Any]:
    path = tmp_path / "osprey.yaml"
    path.write_text(FIXTURE_CONFIG, encoding="utf-8")
    loaded = load_config(path)
    config = loaded.model_copy(
        update={"components": loaded.components.model_copy(update={"source_path": str(CORE)})}
    )
    return yaml.safe_load(render(config, resolver=_fake_resolver).artefacts["compose.yaml"])


def test_the_object_store_is_seaweedfs_and_minio_is_gone(tmp_path: Path) -> None:
    services = _compose(tmp_path)["services"]
    assert "minio" not in services
    store = services["objectstore"]
    assert store["image"] == "chrislusf/seaweedfs:4.48"
    command = store["command"]
    assert command[:2] == ["server", "-s3"] and "-dir=/data" in command
    for setting in ("-s3.port=8333", "-volume.max=1000", "-master.volumeSizeLimitMB=1024",
                    "-master.volumePreallocate=false"):  # fmt: skip
        assert setting in command, setting
    assert store["environment"]["WEED_MASTER_VOLUME_GROWTH_COPY_1"] == "1"


def test_its_credentials_are_the_deployments_and_never_written_here(tmp_path: Path) -> None:
    env = _compose(tmp_path)["services"]["objectstore"]["environment"]
    assert env["AWS_ACCESS_KEY_ID"].startswith("${OSPREY_MINIO_USER")
    assert env["AWS_SECRET_ACCESS_KEY"].startswith("${OSPREY_MINIO_PASSWORD:?")


def test_its_data_is_on_a_named_volume(tmp_path: Path) -> None:
    compose = _compose(tmp_path)
    assert "objectstore-data:/data" in compose["services"]["objectstore"]["volumes"]
    assert "objectstore-data" in compose["volumes"]


def test_it_is_health_checked_and_waited_for(tmp_path: Path) -> None:
    store = _compose(tmp_path)["services"]["objectstore"]
    assert store["healthcheck"]["test"][-1] == "http://127.0.0.1:8333/healthz"


def test_it_is_on_the_internal_network_alone(tmp_path: Path) -> None:
    assert _compose(tmp_path)["services"]["objectstore"]["networks"] == ["osprey"]


def test_the_services_that_use_it_are_told_where_it_is() -> None:
    from harness.apply import object_store_lines

    lines = object_store_lines("ospreyflow", "s3cret").splitlines()
    assert "MINIO_ENDPOINT=objectstore:8333" in lines
    assert "MINIO_ACCESS_KEY=ospreyflow" in lines and "MINIO_SECRET_KEY=s3cret" in lines
