"""ADR-152 invariant I20 (ADR-002 Amendment 1): both front ends resolve the same versions of `sigma`, `@sigma/*`,
`maplibre-gl` and `graphology`, except a difference written in `apps/pages/VERSION_WINDOW.yaml` with the day it
opened, and no release is cut while that file lists anything (slice WS4a).

`OspreyFlow_Core/scripts/same_drawing_versions_check.mjs [root] [--release]` reads the resolved tree in
`package-lock.json`. Every planted fault below is planted in a copy of **the real lockfile**, in the shape npm itself
writes (rule 15: the shape the check meets at its own call site, not a hand-written approximation): a front end's own
pin nested under `apps/pages/node_modules/` (as GG2a's Sigma 4.0.6 is on `away/GG2a`), a plugin's private copy under
`node_modules/<plugin>/node_modules/`, a copy under the linked shared package's own folder.

Which test fails if the invariant is broken (rule 12):
* a difference with nothing in the window: `test_a_difference_with_an_empty_window_fails` (I20's own red: `apps/pages`
  on `maplibre-gl` 6.5 while the workspace resolves 6.19) and `test_gg2a_s_sigma_4_pin_fails_with_an_empty_window`;
* a window entry with no day, a day that is not one, or the wrong versions: `test_an_entry_*`;
* a window that outlives its difference: `test_an_entry_with_no_difference_left_fails`;
* a release with anything listed: `test_a_release_is_refused_while_the_window_lists_anything`;
* a nested duplicate inside one front end, which no entry excuses: `test_a_nested_duplicate_*`;
* a check that compares nothing: `test_a_missing_*_does_not_pass`.
The real tree must pass both ways: `test_the_real_tree_passes`.
"""

from __future__ import annotations

import copy
import json
import shutil
import subprocess
from pathlib import Path

import pytest

CORE = Path(__file__).resolve().parents[3] / "OspreyFlow_Core"
SCRIPT = CORE / "scripts" / "same_drawing_versions_check.mjs"
REAL_LOCK = json.loads((CORE / "package-lock.json").read_text(encoding="utf-8"))
WINDOW = "apps/pages/VERSION_WINDOW.yaml"
EMPTY = "# no difference open\nwindows: []\n"


def node() -> str:
    found = shutil.which("node")
    assert found, "node is needed"
    return found


def run_check(root: Path, *flags: str) -> tuple[int, str]:
    done = subprocess.run([node(), str(SCRIPT), str(root), *flags], cwd=CORE, capture_output=True, text=True, timeout=60)
    return done.returncode, done.stdout + done.stderr


def real_version(name: str) -> str:
    return REAL_LOCK["packages"][f"node_modules/{name}"]["version"]


def entry(package: str, workspace: str, pages: str, opened: str | None = "2026-11-26") -> str:
    lines = [f"  - package: {package}", f"    apps/workspace: {workspace}", f"    apps/pages: {pages}"]
    if opened is not None:
        lines.append(f"    opened: {opened}")
    return "\n".join(lines) + "\n"


def scratch(tmp_path: Path, lock: dict | None = None, window: str | None = EMPTY) -> Path:
    (tmp_path / "apps/pages").mkdir(parents=True, exist_ok=True)
    (tmp_path / "package-lock.json").write_text(json.dumps(lock if lock is not None else REAL_LOCK), encoding="utf-8")
    if window is not None:
        (tmp_path / WINDOW).write_text(window, encoding="utf-8")
    return tmp_path


def pages_pins(lock: dict, name: str, version: str, extra: dict | None = None) -> dict:
    """`apps/pages` pinning `name` exactly at `version`, written as npm writes it when the root already holds another
    version: the pin in the workspace's own devDependencies, the copy nested in `apps/pages/node_modules/`."""
    planted = copy.deepcopy(lock)
    packages = planted["packages"]
    packages["apps/pages"].setdefault("devDependencies", {})[name] = version
    packages[f"apps/pages/node_modules/{name}"] = {
        "version": version,
        "resolved": f"https://registry.npmjs.org/{name}/-/{name.split('/')[-1]}-{version}.tgz",
        "dev": True,
        "license": "MIT",
        **(extra or {}),
    }
    return planted


def gg2a_lock() -> dict:
    """The lockfile as `away/GG2a` has it (read there at `759a45233`): Sigma 4.0.6 and graphology 0.26.0 pinned in
    `apps/pages`, Sigma nested under it, graphology the root's own copy."""
    planted = pages_pins(REAL_LOCK, "sigma", "4.0.6", {"dependencies": {"events": "^3.3.0", "graphology-utils": "^2.5.2"}})
    planted["packages"]["apps/pages"]["devDependencies"]["graphology"] = "0.26.0"
    return planted


def test_the_real_tree_passes() -> None:
    code, output = run_check(CORE)
    assert code == 0, output
    assert "PASS" in output
    code, output = run_check(CORE, "--release")
    assert code == 0, output


def test_the_real_window_file_is_empty() -> None:
    """On main the window is shut (decision 6: empty except while WS4 is open)."""
    text = (CORE / WINDOW).read_text(encoding="utf-8")
    assert [line for line in text.splitlines() if line and not line.startswith("#")] == ["windows: []"]


def test_the_check_sees_what_each_front_end_reaches_through_the_shared_package(tmp_path: Path) -> None:
    """graphology reaches the workspace both directly and through the linked `@ospreyflow/glass-shared`; a second copy
    under the shared package's own folder is a second version in the workspace, so the link is followed."""
    planted = copy.deepcopy(REAL_LOCK)
    planted["packages"]["packages/glass-shared/node_modules/graphology"] = {"version": "0.25.4", "license": "MIT"}
    code, output = run_check(scratch(tmp_path, planted))
    assert code == 1, output
    assert "apps/workspace reaches two versions of graphology" in output
    assert "0.25.4 (packages/glass-shared/node_modules/graphology)" in output


def test_a_difference_with_an_empty_window_fails(tmp_path: Path) -> None:
    """I20's own red (ADR-152's table): `apps/pages` pinning `maplibre-gl` 6.5 while the workspace resolves its own."""
    workspace = real_version("maplibre-gl")
    code, output = run_check(scratch(tmp_path, pages_pins(REAL_LOCK, "maplibre-gl", "6.5.0")))
    assert code == 1, output
    assert f"maplibre-gl: apps/workspace resolves {workspace} and apps/pages resolves 6.5.0" in output
    assert "does not list it" in output


def test_gg2a_s_sigma_4_pin_fails_with_an_empty_window(tmp_path: Path) -> None:
    code, output = run_check(scratch(tmp_path, gg2a_lock()))
    assert code == 1, output
    assert f"sigma: apps/workspace resolves {real_version('sigma')} and apps/pages resolves 4.0.6" in output
    # graphology is the root's copy for both, so it is not named.
    assert "graphology" not in output


def test_a_difference_listed_with_its_day_passes(tmp_path: Path) -> None:
    window = "windows:\n" + entry("sigma", real_version("sigma"), "4.0.6")
    code, output = run_check(scratch(tmp_path, gg2a_lock(), window))
    assert code == 0, output


def test_an_entry_with_no_day_is_refused(tmp_path: Path) -> None:
    window = "windows:\n" + entry("sigma", real_version("sigma"), "4.0.6", opened=None)
    code, output = run_check(scratch(tmp_path, gg2a_lock(), window))
    assert code == 1, output
    assert "the entry for sigma gives no day it opened" in output


@pytest.mark.parametrize("day", ["2026-11-31", "26 November 2026", "2026-1-5", "soon"])
def test_an_entry_whose_day_is_not_a_day_is_refused(tmp_path: Path, day: str) -> None:
    window = "windows:\n" + entry("sigma", real_version("sigma"), "4.0.6", opened=day)
    code, output = run_check(scratch(tmp_path, gg2a_lock(), window))
    assert code == 1, output
    assert "which is not a day" in output


def test_an_entry_naming_other_versions_fails(tmp_path: Path) -> None:
    """The window names the difference it excuses: Sigma 4.0.7 in `pages` is not the 4.0.6 written down."""
    window = "windows:\n" + entry("sigma", real_version("sigma"), "4.0.7")
    code, output = run_check(scratch(tmp_path, gg2a_lock(), window))
    assert code == 1, output
    assert "but apps/pages/VERSION_WINDOW.yaml lists" in output


def test_an_entry_with_no_difference_left_fails(tmp_path: Path) -> None:
    """WS4b closes the window in the merge that ports the workspace: an entry left behind is refused."""
    window = "windows:\n" + entry("sigma", real_version("sigma"), "4.0.6")
    code, output = run_check(scratch(tmp_path, REAL_LOCK, window))
    assert code == 1, output
    assert "do not differ in it: take the entry out" in output


def test_an_entry_for_a_library_i20_does_not_hold_is_refused(tmp_path: Path) -> None:
    window = "windows:\n" + entry("react", "19.3.1", "19.2.0")
    code, output = run_check(scratch(tmp_path, REAL_LOCK, window))
    assert code == 1, output
    assert "not a drawing library I20 holds equal" in output


@pytest.mark.parametrize(
    "window",
    [
        "",  # empty file
        "windows:\n",  # open, with nothing in it
        "windows: []\n  - package: sigma\n",  # says empty, then lists
        "windows:\n- package: sigma\n",  # indented otherwise than the file's one shape
        "versions: []\n",
    ],
)
def test_a_window_file_it_cannot_read_does_not_pass(tmp_path: Path, window: str) -> None:
    code, output = run_check(scratch(tmp_path, REAL_LOCK, window))
    assert code == 1, output
    assert WINDOW in output


def test_a_release_is_refused_while_the_window_lists_anything(tmp_path: Path) -> None:
    window = "windows:\n" + entry("sigma", real_version("sigma"), "4.0.6")
    root = scratch(tmp_path, gg2a_lock(), window)
    assert run_check(root)[0] == 0
    code, output = run_check(root, "--release")
    assert code == 1, output
    assert "no release while apps/pages/VERSION_WINDOW.yaml lists anything" in output
    assert "sigma (" in output and "opened 2026-11-26" in output


def test_a_nested_duplicate_under_a_plugin_fails(tmp_path: Path) -> None:
    """`@sigma/node-border` given a private copy of Sigma, as npm nests one when the plugin's range excludes the root's:
    the workspace would draw nodes with one renderer and the rest with another."""
    planted = copy.deepcopy(REAL_LOCK)
    planted["packages"]["node_modules/@sigma/node-border/node_modules/sigma"] = {"version": "3.1.0", "license": "MIT"}
    planted["packages"]["node_modules/@sigma/node-border"]["dependencies"] = {"sigma": "3.1.0"}
    code, output = run_check(scratch(tmp_path, planted))
    assert code == 1, output
    assert "apps/workspace reaches two versions of sigma" in output
    assert "3.1.0 (node_modules/@sigma/node-border/node_modules/sigma)" in output


def test_a_nested_duplicate_is_not_excused_by_the_window(tmp_path: Path) -> None:
    """`pages` on Sigma 4 with a Sigma plugin hoisted to the root, so its peer `sigma` resolves to the root's Sigma 3:
    a window entry for the difference between the front ends does not excuse two renderers inside one."""
    planted = gg2a_lock()
    planted["packages"]["apps/pages"]["devDependencies"]["@sigma/node-border"] = "^3.0.0"
    window = "windows:\n" + entry("sigma", real_version("sigma"), "4.0.6")
    code, output = run_check(scratch(tmp_path, planted, window))
    assert code == 1, output
    assert "apps/pages reaches two versions of sigma" in output


def test_a_missing_window_file_does_not_pass(tmp_path: Path) -> None:
    code, output = run_check(scratch(tmp_path, REAL_LOCK, window=None))
    assert code == 1, output
    assert "no apps/pages/VERSION_WINDOW.yaml" in output


def test_a_missing_front_end_does_not_pass(tmp_path: Path) -> None:
    planted = copy.deepcopy(REAL_LOCK)
    del planted["packages"]["apps/pages"]
    code, output = run_check(scratch(tmp_path, planted))
    assert code == 1, output
    assert "no front end apps/pages" in output


def test_a_missing_lockfile_does_not_pass(tmp_path: Path) -> None:
    (tmp_path / "apps/pages").mkdir(parents=True)
    (tmp_path / WINDOW).write_text(EMPTY, encoding="utf-8")
    code, output = run_check(tmp_path)
    assert code == 1, output
    assert "no package-lock.json" in output
