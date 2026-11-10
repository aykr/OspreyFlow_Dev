"""The real render, for a deployment kept by name under `~/.ospreyflow/deployments/` (ADR-138).

`harness.apply`'s own step 1 (`stage_deployment`), not a stand-in, rendering into a temporary home:
- `deployment.env` there is mode 600 — `test_deployment_env_under_the_home_folder_is_600`;
- the images are built from the checkout, not from three folders above the home folder —
  `test_a_deployment_outside_a_checkout_builds_from_the_checkout_by_its_own_path`;
- a checkout-rooted deployment renders byte for byte as before (`../../..`) —
  `test_a_checkout_rooted_deployment_still_builds_from_three_folders_up`;
- every image it builds — Superset's among them — is built from a folder of the checkout, found
  from the compose file's own folder as Compose finds it —
  `test_every_build_context_of_a_named_deployment_is_a_folder_of_the_checkout` (step 11b: the
  Superset context stayed `../../superset`, which from the home folder is `~/.ospreyflow/superset`,
  and the first real named install failed at its build);
- its graph store is published at its own port — `test_the_graph_port_is_the_deployments_own`;
- the install's preflight checks that port, from the deployment's own `deployment.env`, not 2480,
  so a named install is not refused where another deployment holds 2480 (P5b's live run on the
  test server, 10 November 2026) — `test_the_preflight_checks_the_deployments_own_graph_port`;
- its front proxy published on every network interface, though a named deployment is Lite (S10, the
  owner's ruling of 2 November 2026) — `test_a_named_deployment_answers_on_this_computer_only`.
"""

from __future__ import annotations

import stat
from pathlib import Path

import pytest
import yaml
from harness.apply import stage_deployment
from harness.render import BUILD_CONTEXT_FROM_OUTPUT_DIR, REPO_ROOT, build_context_for, load_config
from harness.reporting import superset_build_context

from schemas.deployment import OspreyConfig


def _named_config(
    home: Path, *, graph_port: int | None = 2503, reporting: bool = False
) -> tuple[OspreyConfig, Path]:
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
    if reporting:
        raw["reporting"] = {"sync": True, "superset": True}
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


def _build_contexts(compose_file: Path) -> dict[str, Path]:
    """Each built service's `build.context`, resolved as Compose resolves it: from the compose
    file's own folder."""
    services = yaml.safe_load(compose_file.read_text(encoding="utf-8"))["services"]
    return {
        name: (compose_file.parent / service["build"]["context"]).resolve()
        for name, service in services.items()
        if isinstance(service, dict) and "build" in service
    }


def test_every_build_context_of_a_named_deployment_is_a_folder_of_the_checkout(
    tmp_path: Path,
) -> None:
    stage = _stage(*_named_config(tmp_path, reporting=True))
    contexts = _build_contexts(stage / "compose.yaml")
    assert "superset" in contexts  # the case that failed: reporting on, as an install has it
    checkout = REPO_ROOT.resolve()
    for service, context in contexts.items():
        assert context.is_dir(), f"{service} builds from {context}, which does not exist"
        assert context == checkout or checkout in context.parents, (service, context)
    assert contexts["superset"] == checkout / "deploy" / "superset"


def test_a_checkout_rooted_deployment_still_builds_from_three_folders_up() -> None:
    out_dir = REPO_ROOT / "deploy" / "generated" / "local-lite"
    assert build_context_for(out_dir, str(REPO_ROOT)) == BUILD_CONTEXT_FROM_OUTPUT_DIR
    assert build_context_for(out_dir, None) == BUILD_CONTEXT_FROM_OUTPUT_DIR
    assert superset_build_context(BUILD_CONTEXT_FROM_OUTPUT_DIR) == "../../superset"
    assert superset_build_context(None) == "../../superset"


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


def test_the_preflight_checks_the_deployments_own_graph_port(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The compose file publishes `${OSPREY_ARCADEDB_PORT:-2480}` and the deployment's own
    `deployment.env` names its port, which Compose reads with `--env-file`; the preflight resolved
    it against this process's environment alone, so it checked 2480 and refused the install
    wherever another deployment held 2480. Called through `harness.apply.preflight` on the context
    the install builds (`PreflightContext(config=config, out_dir=stage)`), with the ports check as
    its one check; the shell's own value still wins, as Compose's does. The port guard keeps a real
    socket off 2480, so the held ports are given to the check's bind test."""
    from harness import apply
    from harness.preflight import PreflightContext, ports

    config, path = _named_config(tmp_path, graph_port=2503)
    stage = _stage(config, path)
    monkeypatch.delenv("OSPREY_ARCADEDB_PORT", raising=False)
    monkeypatch.setattr(apply, "ALL_CHECKS", [ports])
    held: set[int] = {2480}
    checked: list[int] = []

    def bindable(port: int) -> bool:
        checked.append(port)
        return port not in held

    monkeypatch.setattr(ports, "_is_bindable", bindable)
    context = PreflightContext(config=config, out_dir=stage)
    apply.preflight(context)
    assert 2503 in checked and 2480 not in checked, checked
    # Its own port held is refused, by that port.
    held = {2503}
    with pytest.raises(apply.ApplyFailed, match="2503"):
        apply.preflight(context)
    # The shell's value wins over the env file, as it does for Compose.
    held = set()
    monkeypatch.setenv("OSPREY_ARCADEDB_PORT", "2511")
    checked.clear()
    apply.preflight(context)
    assert 2511 in checked and 2503 not in checked, checked


def test_the_ports_check_reads_an_env_file_as_compose_does(tmp_path: Path) -> None:
    """`deployment.env` as render writes it is bare `NAME=value`; the reader takes the other shapes
    Compose takes the same way, so a hand-edited file is not read otherwise than `up` reads it."""
    from harness.preflight.ports import read_env_file

    env = tmp_path / "deployment.env"
    env.write_text(
        "# a comment\n\n"
        "PLAIN=2503\n"
        "export EXPORTED=2504\n"
        "COMMENTED=2505 # the graph store\n"
        "SINGLE='2506'\n"
        'DOUBLE="2507"\n'
        "HASH_INSIDE='25#08'\n"
        "EQUALS=a=b\n"
        "BLANK=\n",
        encoding="utf-8",
    )
    assert read_env_file(env) == {
        "PLAIN": "2503", "EXPORTED": "2504", "COMMENTED": "2505", "SINGLE": "2506",
        "DOUBLE": "2507", "HASH_INSIDE": "25#08", "EQUALS": "a=b", "BLANK": "",
    }  # fmt: skip
