"""The real render, for a deployment kept by name under `~/.ospreyflow/deployments/` (ADR-138).

`harness.apply`'s own step 1 (`stage_deployment`), not a stand-in, rendering into a temporary home:
- `deployment.env` there is mode 600 — `test_deployment_env_under_the_home_folder_is_600`;
- the images are built from the checkout, not from three folders above the home folder —
  `test_a_deployment_outside_a_checkout_builds_from_the_checkout_by_its_own_path`;
- a checkout-rooted deployment renders byte for byte as before (`../../..`) —
  `test_a_checkout_rooted_deployment_still_builds_from_three_folders_up`;
- its graph store is published at its own port — `test_the_graph_port_is_the_deployments_own`;
- its front proxy published on every network interface, though a named deployment is Lite (S10, the
  owner's ruling of 2 November 2026) — `test_a_named_deployment_answers_on_this_computer_only`.
"""

from __future__ import annotations

import stat
from pathlib import Path

import yaml
from harness.apply import stage_deployment
from harness.render import BUILD_CONTEXT_FROM_OUTPUT_DIR, REPO_ROOT, build_context_for, load_config

from schemas.deployment import OspreyConfig


def _named_config(home: Path, *, graph_port: int | None = 2503) -> tuple[OspreyConfig, Path]:
    folder = home / ".ospreyflow" / "deployments" / "alpha"
    folder.mkdir(parents=True)
    deployment: dict[str, object] = {"name": "alpha"}
    if graph_port is not None:
        deployment["graph_port"] = graph_port
    raw = {
        "profile": "local-lite",
        "deployment": deployment,
        "network": {"public_origin": "http://alpha.localhost:8090"},
        "components": {"source_path": str(REPO_ROOT),
                       "storage": {"ingest": str(home / "in"), "tiles": str(home / "tiles")}},
    }  # fmt: skip
    path = folder / "osprey.yaml"
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    return load_config(path), path


def _stage(config: OspreyConfig, path: Path) -> Path:
    stage = path.parent.parent / ".alpha.staging"
    stage_deployment(
        config, path, stage, realm="osprey", demo_analyst=True, images_from=None,
        previous_env="", environ={},
    )  # fmt: skip
    return stage


def test_deployment_env_under_the_home_folder_is_600(tmp_path: Path) -> None:
    stage = _stage(*_named_config(tmp_path))
    assert stat.S_IMODE((stage / "deployment.env").stat().st_mode) == 0o600


def test_a_deployment_outside_a_checkout_builds_from_the_checkout_by_its_own_path(
    tmp_path: Path,
) -> None:
    stage = _stage(*_named_config(tmp_path))
    services = yaml.safe_load((stage / "compose.yaml").read_text(encoding="utf-8"))["services"]
    assert services["api"]["build"]["context"] == str(REPO_ROOT.resolve())
    assert yaml.safe_load((stage / "compose.yaml").read_text(encoding="utf-8"))["name"] == "alpha"


def test_a_checkout_rooted_deployment_still_builds_from_three_folders_up() -> None:
    out_dir = REPO_ROOT / "deploy" / "generated" / "local-lite"
    assert build_context_for(out_dir, str(REPO_ROOT)) == BUILD_CONTEXT_FROM_OUTPUT_DIR
    assert build_context_for(out_dir, None) == BUILD_CONTEXT_FROM_OUTPUT_DIR


def test_the_graph_port_is_the_deployments_own(tmp_path: Path) -> None:
    stage = _stage(*_named_config(tmp_path))
    env = (stage / "deployment.env").read_text(encoding="utf-8").splitlines()
    assert "OSPREY_ARCADEDB_PORT=2503" in env
    assert "OSPREY_ARCADEDB_PORT=2480" not in env


def test_without_a_graph_port_the_render_is_as_before(tmp_path: Path) -> None:
    stage = _stage(*_named_config(tmp_path, graph_port=None))
    env = (stage / "deployment.env").read_text(encoding="utf-8").splitlines()
    assert "OSPREY_ARCADEDB_PORT=2480" in env


def test_a_named_deployment_answers_on_this_computer_only(tmp_path: Path) -> None:
    """S10: a deployment kept by name is a Lite one (ADR-138), so its own port is bound to
    `127.0.0.1` as the checkout's is, through `apply`'s real staging step."""
    stage = _stage(*_named_config(tmp_path))
    proxy = yaml.safe_load((stage / "compose.yaml").read_text(encoding="utf-8"))["services"]["proxy"]
    assert proxy["ports"] == ["127.0.0.1:8090:8080", "127.0.0.1:${OSPREY_ARCADEDB_PORT:-2480}:2480"]
