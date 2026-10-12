"""Finding the product folder and its interpreter (`06_DECISIONS.md` ADR-114 Amendment 3
decision 3: "from `OSPREYFLOW_HOME`, else the folder the bootstrap recorded, else the checkout it is
run inside").

What a mistake would do, and the case that catches it:
- the developer repository (product one folder down) not recognised —
  `test_the_developer_layout_is_found_from_the_repository_root_and_from_inside_the_product`;
- the user repository (product IS the root) not found from a subfolder —
  `test_the_user_layout_is_found_from_a_subfolder`;
- `OSPREYFLOW_HOME` ignored, or accepted when it holds no product —
  `test_ospreyflow_home_wins_and_is_refused_when_it_holds_no_product`;
- the recorded folder ignored — `test_the_recorded_folder_is_used_when_run_from_elsewhere`;
- an unrelated folder treated as a product — `test_nothing_found_is_refused_in_words`;
- the heavy work run outside the checkout's own environment —
  `test_python_for_prefers_the_checkouts_venv_and_falls_back_to_uv_run`;
- a deployment looked for under the wrong profile — `test_the_deployment_dir_follows_the_profile`.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from ospreyflow.home import CommandRefused, deployment_dir, find_product, python_for


def _make_product(root: Path, profile: str | None = None) -> Path:
    (root / "harness").mkdir(parents=True)
    (root / "harness" / "__init__.py").write_text("", encoding="utf-8")
    config = {"profile": profile} if profile else {}
    (root / "osprey.yaml").write_text(yaml.safe_dump(config), encoding="utf-8")
    return root


def _none() -> Path | None:
    return None


def test_the_developer_layout_is_found_from_the_repository_root_and_from_inside_the_product(
    tmp_path: Path,
) -> None:
    core = _make_product(tmp_path / "OspreyFlow_Core")
    (tmp_path / "OspreyFlow_Build").mkdir()
    assert find_product(tmp_path, {}, recorded=_none) == core
    assert find_product(core / "harness", {}, recorded=_none) == core


def test_the_user_layout_is_found_from_a_subfolder(tmp_path: Path) -> None:
    root = _make_product(tmp_path / "ospreyflow")
    (root / "deploy" / "generated").mkdir(parents=True)
    assert find_product(root / "deploy" / "generated", {}, recorded=_none) == root


def test_ospreyflow_home_wins_and_is_refused_when_it_holds_no_product(tmp_path: Path) -> None:
    mine = _make_product(tmp_path / "mine")
    other = _make_product(tmp_path / "other")
    assert find_product(other, {"OSPREYFLOW_HOME": str(mine)}, recorded=_none) == mine
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(CommandRefused, match="OSPREYFLOW_HOME"):
        find_product(other, {"OSPREYFLOW_HOME": str(empty)}, recorded=_none)


def test_the_recorded_folder_is_used_when_run_from_elsewhere(tmp_path: Path) -> None:
    recorded = _make_product(tmp_path / "recorded")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    assert find_product(elsewhere, {}, recorded=lambda: recorded) == recorded
    # A recorded folder that has gone does not hide the checkout the command is run inside.
    inside = _make_product(tmp_path / "inside")
    assert find_product(inside, {}, recorded=lambda: tmp_path / "gone") == inside


def test_nothing_found_is_refused_in_words(tmp_path: Path) -> None:
    (tmp_path / "harness").mkdir()  # a harness folder alone, with no osprey.yaml, is not a product
    (tmp_path / "harness" / "__init__.py").write_text("", encoding="utf-8")
    with pytest.raises(CommandRefused) as caught:
        find_product(tmp_path, {}, recorded=_none)
    assert "No OspreyFlow checkout found here" in str(caught.value)
    assert "OSPREYFLOW_HOME" in str(caught.value)


def test_python_for_prefers_the_checkouts_venv_and_falls_back_to_uv_run(tmp_path: Path) -> None:
    root = _make_product(tmp_path / "p")
    assert python_for(root) == ["uv", "run", "--project", str(root), "python"]
    posix = root / ".venv" / "bin" / "python"
    posix.parent.mkdir(parents=True)
    posix.write_text("", encoding="utf-8")
    assert python_for(root, windows=False) == [str(posix)]
    # Windows looks for its own layout, so a POSIX venv is not mistaken for one.
    assert python_for(root, windows=True) == ["uv", "run", "--project", str(root), "python"]
    windows = root / ".venv" / "Scripts" / "python.exe"
    windows.parent.mkdir(parents=True)
    windows.write_text("", encoding="utf-8")
    assert python_for(root, windows=True) == [str(windows)]


def test_the_deployment_dir_follows_the_profile(tmp_path: Path) -> None:
    default = _make_product(tmp_path / "a")
    assert deployment_dir(default) == default / "deploy" / "generated" / "local-lite"
    small = _make_product(tmp_path / "b", profile="small")
    assert deployment_dir(small) == small / "deploy" / "generated" / "small"
