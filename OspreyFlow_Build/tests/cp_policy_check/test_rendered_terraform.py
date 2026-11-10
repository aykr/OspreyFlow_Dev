"""The namespace's Terraform the `cloud-platform` profile renders (ADR-148 decisions 1, 4 and 8)
is what OpenTofu formats as written and accepts as valid, for both environments, so the pull
request a person raises from it is not refused for its syntax. OpenTofu runs as the image
`make opentofu-check` pins; `init` fetches the three providers, so this needs Docker and the
network. Shown red by a planted fault in the shape the renderer emits (rule 15)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from harness.render import load_config, render
from tools.cp_policy_check import FIXTURES, _resolver

TOFU = "ghcr.io/opentofu/opentofu:1.10.6"


def _write(folder: Path, fixture: str) -> Path:
    artefacts = render(load_config(FIXTURES / f"{fixture}.yaml"), resolver=_resolver).artefacts
    for name, text in artefacts.items():
        if name.startswith("terraform/"):
            (folder / name.removeprefix("terraform/")).write_text(text, encoding="utf-8")
    return folder


def _tofu(folder: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", "run", "--rm", "-v", f"{folder}:/w", TOFU, "-chdir=/w", *args],
        capture_output=True, text=True, timeout=600, check=False,
    )  # fmt: skip


@pytest.mark.parametrize("fixture", ["development", "production"])
def test_the_terraform_is_formatted_and_valid(tmp_path: Path, fixture: str) -> None:
    folder = _write(tmp_path, fixture)
    fmt = _tofu(folder, "fmt", "-check", "-diff")
    assert fmt.returncode == 0, fmt.stdout + fmt.stderr
    init = _tofu(folder, "init", "-backend=false", "-input=false", "-no-color")
    assert init.returncode == 0, init.stdout + init.stderr
    valid = _tofu(folder, "validate", "-no-color")
    assert valid.returncode == 0, valid.stdout + valid.stderr


def test_a_reference_to_nothing_is_refused(tmp_path: Path) -> None:
    folder = _write(tmp_path, "development")
    rds = folder / "rds.tf"
    # What the renderer would emit had a secret's value named a resource it does not write.
    rds.write_text(
        rds.read_text(encoding="utf-8").replace(
            "aws_db_instance.postgres.address", "aws_db_instance.missing.address"
        ),
        encoding="utf-8",
    )
    assert _tofu(folder, "init", "-backend=false", "-input=false", "-no-color").returncode == 0
    assert _tofu(folder, "validate", "-no-color").returncode != 0
