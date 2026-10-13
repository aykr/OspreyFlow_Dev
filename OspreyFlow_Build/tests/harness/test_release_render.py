"""ADR-114 Amendment 8 points 1–2: the renderer tells the Conduit its version, and gives it the
deployment's `state/` folder read-only, where `ospreyflow update --check` writes the notice."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from harness.release import checkout_version
from harness.render import load_config, render
from tools.layout import CORE

from tests.harness.test_render import FIXTURE_CONFIG, _fake_resolver


def _rendered(tmp_path: Path) -> dict[str, str]:
    path = tmp_path / "osprey.yaml"
    path.write_text(FIXTURE_CONFIG, encoding="utf-8")
    loaded = load_config(path)
    config = loaded.model_copy(
        update={"components": loaded.components.model_copy(update={"source_path": str(CORE)})}
    )
    return render(config, resolver=_fake_resolver).artefacts


def test_the_conduit_is_told_the_deployments_version(tmp_path: Path) -> None:
    env = _rendered(tmp_path)["deployment.env"].splitlines()
    assert f"OSPREY_RELEASE_VERSION={checkout_version(CORE)}" in env
    assert "OSPREY_STATE_DIR=/var/lib/osprey/state" in env


def test_the_conduit_reads_the_state_folder_and_cannot_write_it(tmp_path: Path) -> None:
    compose = yaml.safe_load(_rendered(tmp_path)["compose.yaml"])
    assert "./state:/var/lib/osprey/state:ro" in compose["services"]["api"]["volumes"]
    for name, service in compose["services"].items():
        if name != "api":
            assert not any("./state:" in str(v) for v in service.get("volumes") or []), name


def test_a_release_names_its_own_registry_for_the_owned_images(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """Amendment 8: the user repository's release pushes to `ghcr.io/<its owner>`, so its lock must
    name that, not the default. A deployment that builds from its checkout is unaffected."""
    from harness.render import service_images

    path = tmp_path / "osprey.yaml"
    path.write_text(FIXTURE_CONFIG, encoding="utf-8")
    pulling = load_config(path)
    monkeypatch.setenv("OSPREY_IMAGE_REGISTRY", "ghcr.io/acme")
    owned = {i.service: i.image for i in service_images(pulling)}
    assert owned["api"].startswith("ghcr.io/acme/api:")
    assert owned["arcadedb"].startswith("arcadedata/arcadedb:")
    monkeypatch.delenv("OSPREY_IMAGE_REGISTRY")
    assert {i.service: i.image for i in service_images(pulling)}["api"].startswith(
        "ghcr.io/ospreyflow/api:"
    )
