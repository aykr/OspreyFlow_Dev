"""A named deployment's folder stays readable by its owner alone (ADR-138 decision 2).

Found at step 11b (2 November 2026): `ospreyflow install --name govuk` made
`~/.ospreyflow/deployments/govuk/` mode 700, then the harness copied its staged render over it with
`shutil.copytree`, which also copies the stage folder's own mode, and the folder holding
`deployment.env` ended 755. Each test names what it would catch.
"""

from __future__ import annotations

import inspect
import os
import stat
from pathlib import Path

import pytest
from harness import apply
from harness.apply import move_into_place

pytestmark = pytest.mark.skipif(os.name == "nt", reason="POSIX modes")


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def test_the_deployments_folder_keeps_its_own_mode_when_the_render_is_moved_in(
    tmp_path: Path,
) -> None:
    """Catches the copy taking the stage folder's 755 over the deployment's 700."""
    out_dir = tmp_path / "govuk"
    out_dir.mkdir()
    out_dir.chmod(0o700)
    stage = tmp_path / ".govuk.staging"
    stage.mkdir()
    stage.chmod(0o755)
    env = stage / "deployment.env"
    env.write_text("OSPREY_EXAMPLE=1\n")
    env.chmod(0o600)

    move_into_place(stage, out_dir)

    assert _mode(out_dir) == 0o700
    assert _mode(out_dir / "deployment.env") == 0o600


def test_a_folder_the_render_creates_takes_the_stages_mode(tmp_path: Path) -> None:
    """A checkout-rooted deployment's first render has no folder yet: it is made, as before."""
    stage = tmp_path / ".local-lite.staging"
    stage.mkdir()
    (stage / "compose.yaml").write_text("name: x\n")
    out_dir = tmp_path / "local-lite"

    move_into_place(stage, out_dir)

    assert (out_dir / "compose.yaml").is_file()


def test_every_move_of_a_staged_render_keeps_the_folders_mode() -> None:
    """Catches a call site that copies the stage over the deployment directly (install and apply
    both stage their render); only `move_into_place` may call `copytree` onto `out_dir`."""
    source = inspect.getsource(apply)
    helper = inspect.getsource(move_into_place)
    assert source.replace(helper, "").count("copytree(stage, out_dir") == 0
    assert source.count("move_into_place(stage, out_dir)") == 2
