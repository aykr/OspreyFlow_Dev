"""ADR-132 Amendment 1: a machine may run more than one Lite deployment. Each is a Compose project
named by `deployment.name`, with its own volumes and its own rendered folder.

The trap these cases design out: before `deployment.name`, the Compose project was
`osprey-<profile>` and the rendered folder `deploy/generated/<profile>/`, so a second `local-lite`
deployment would have been the same project, silently sharing the first's volumes (one graph store
for both), and its render would have overwritten the first's files. A deployment that does not
set the name must keep the project and folder it has today, or the owner's running deployment
would lose its volumes.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from harness.render import main as render_main
from harness.render import render
from ospreyflow.home import deployment_dir
from pydantic import ValidationError

from schemas.deployment import OspreyConfig, compose_project, generated_folder


def _compose(config: OspreyConfig) -> dict[str, object]:
    artefacts = render(config, resolver=lambda _i: "sha256:" + "0" * 64).artefacts
    return yaml.safe_load(artefacts["compose.yaml"])


def _write(folder: Path, raw: dict[str, object]) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "osprey.yaml"
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    return path


def test_a_deployment_without_a_name_keeps_its_project_folder_and_volumes() -> None:
    """The owner's current deployment: `osprey-local-lite`, rendered to `local-lite/`, and volumes
    with no name of their own, so Compose keeps prefixing them with that same project name."""
    config = OspreyConfig()
    compose = _compose(config)

    assert compose["name"] == "osprey-local-lite"
    assert compose_project(config) == "osprey-local-lite"
    assert generated_folder(config) == "local-lite"
    volumes = compose["volumes"]
    assert isinstance(volumes, dict)
    assert all(not (spec or {}).get("name") for spec in volumes.values())


def test_a_named_deployment_is_a_project_and_a_folder_of_its_own() -> None:
    config = OspreyConfig.model_validate({"deployment": {"name": "osprey-govuk"}})

    assert _compose(config)["name"] == "osprey-govuk"
    assert generated_folder(config) == "osprey-govuk"


def test_render_writes_a_named_deployment_to_its_own_folder_and_leaves_the_other(
    tmp_path: Path,
) -> None:
    out_root = tmp_path / "generated"
    plain = _write(tmp_path / "a", {})
    named = _write(tmp_path / "b", {"deployment": {"name": "osprey-govuk"}})

    for config in (plain, named):
        argv = ["--config", str(config), "--out-root", str(out_root), "--allow-unpinned"]
        assert render_main(argv) == 0

    assert (out_root / "local-lite" / "compose.yaml").is_file()
    assert (out_root / "osprey-govuk" / "compose.yaml").is_file()
    first = yaml.safe_load((out_root / "local-lite" / "compose.yaml").read_text(encoding="utf-8"))
    assert first["name"] == "osprey-local-lite"


def test_the_command_and_the_harness_agree_where_a_deployment_is_rendered(tmp_path: Path) -> None:
    """`ospreyflow start`, `stop` and `status` find the deployment through `deployment_dir`; the
    harness renders it through `generated_folder`. If they disagreed, the command would drive the
    other deployment, or none."""
    for raw in ({}, {"deployment": {"name": "osprey-govuk"}}):
        product = tmp_path / str(len(raw))
        _write(product, raw)
        config = OspreyConfig.model_validate(raw)
        rendered = product / "deploy" / "generated" / generated_folder(config)
        assert deployment_dir(product) == rendered


@pytest.mark.parametrize("name", ["Osprey-GovUK", "osprey_govuk", "-osprey", "osprey govuk", ""])
def test_a_name_compose_would_not_take_is_refused(name: str) -> None:
    with pytest.raises(ValidationError, match="deployment.name"):
        OspreyConfig.model_validate({"deployment": {"name": name}})
