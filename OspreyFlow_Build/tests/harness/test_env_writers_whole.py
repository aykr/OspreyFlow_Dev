"""Every write of a deployment's `deployment.env` goes through `harness.atomic` (CARRIES; the
orchestrator's review of c5209b1, item 1; ADR-114 Amendment 39 decision 5, "an interruption leaves
whole files and the secrets as they were").

Three writers still truncated and rewrote the live file after the carries' first round:
`register_sign_in._write_env_value` (every `start --build`, restore and apply),
`restore._set_env_line` (`SUPERSET_SECRET_KEY` among others) and `update._put_back`'s
`shutil.copy2`. Each is now held here at its own call site, by the hard-link witness of
`test_atomic_writes.py`: a second name made for the old file keeps the old bytes only if the file
was *replaced*; a rewrite in place shows the new bytes through it too.

So that a fourth writer cannot appear unseen (rule 12), `test_no_module_writes_an_env_file_in_place`
scans every module under `harness/`, `scripts/` and `cli/ospreyflow/` for a raw write (`write_text`,
`write_bytes`, `open` for writing, `os.open` for writing, `shutil.copy`/`copy2`/`copyfile`/`move`)
whose destination names an env file (`deployment.env`, or a name holding `env`, such as `env_path`),
or copies a folder's files by their own names (`directory / item.name`, which reaches
`deployment.env` when the folder is a deployment's). Each such write is either the stage's or
rollback point's own fresh copy, listed in `ALLOWED` with its reason, or a defect. It is shown red
with each writer's real shape (`test_the_scan_flags_...`), and a stale `ALLOWED` entry fails.
"""

from __future__ import annotations

import ast
import os
from pathlib import Path

import pytest
from harness import register_sign_in, restore, update

CORE = Path(__file__).resolve().parents[3] / "OspreyFlow_Core"
SCANNED = ("harness", "scripts", "cli/ospreyflow")

OLD = "OSPREY_POSTGRES_PASSWORD=old-secret\nSUPERSET_SECRET_KEY=old-key\n"

#: (module, function, destination as written): a fresh copy into a new private folder, never the
#: live secrets file, and why.
ALLOWED = {
    # The rollback point is made new for each update (mkdir(parents=True), never exists before):
    # a copy into it creates a file; it replaces nothing.
    ("harness/update.py", "_keep_rollback_point", "point / item.name"),
    # Put-back's copy of every file but a `*.env` one, which never holds a secret and is written in
    # place so that a container mounting it on its own keeps seeing it; its `*.env` branch goes
    # through `replace_whole`, held by `test_update_s_put_back_replaces_deployment_env_...` below.
    ("harness/update.py", "_put_back", "directory / item.name"),
    # The refresh's stage is made new and 700 for each run (ADR-114 Am 39); a copy into it creates a
    # file, and what moves into place goes through `replace_whole`.
    ("scripts/refresh.py", "_files_up_to_date_staged", "stage / path.name"),
    # The refresh's own passes edit the stage's copy (`directory` is the stage there), which is
    # moved into place whole by `_files_up_to_date_staged`.
    ("scripts/refresh.py", "_models_up_to_date", "env_path"),
    ("scripts/refresh.py", "_release_up_to_date", "env_path"),
}

_COPIES = {"copy", "copy2", "copyfile", "move"}
_WRITE_FLAGS = {"O_WRONLY", "O_RDWR", "O_TRUNC", "O_APPEND"}


def _names_an_env_file(text: str) -> bool:
    lowered = text.lower().replace("environ", "")
    return "deployment.env" in lowered or "env" in lowered


def _by_its_own_name(node: ast.expr) -> bool:
    """`folder / item.name`: a folder's files copied over by their own names."""
    return (
        isinstance(node, ast.BinOp)
        and isinstance(node.op, ast.Div)
        and isinstance(node.right, ast.Attribute)
        and node.right.attr == "name"
    )


def _destination(call: ast.Call) -> ast.expr | None:
    func = call.func
    if isinstance(func, ast.Attribute) and func.attr in {"write_text", "write_bytes"}:
        return func.value
    if isinstance(func, ast.Attribute) and func.attr == "open" and isinstance(func.value, ast.Name):
        if func.value.id == "shutil":
            return None
        if func.value.id == "os" and call.args:
            flags = ast.dump(call.args[1]) if len(call.args) > 1 else ""
            return call.args[0] if any(flag in flags for flag in _WRITE_FLAGS) else None
    if isinstance(func, ast.Attribute) and func.attr in _COPIES:
        if isinstance(func.value, ast.Name) and func.value.id == "shutil" and len(call.args) > 1:
            return call.args[1]
    opener = isinstance(func, ast.Name) and func.id == "open"
    method = isinstance(func, ast.Attribute) and func.attr == "open"
    if opener or method:
        mode_args = call.args[1:2] if opener else call.args[0:1]
        mode = next((k.value for k in call.keywords if k.arg == "mode"), None)
        mode = mode or (mode_args[0] if mode_args else None)
        if isinstance(mode, ast.Constant) and isinstance(mode.value, str):
            if any(letter in mode.value for letter in "wax+"):
                return call.args[0] if opener else func.value
    return None


def in_place_writes(source: str, relative: str) -> set[tuple[str, str, str]]:
    """Each raw write in `source` that names an env file or copies a folder's files by name."""
    tree = ast.parse(source)
    found: set[tuple[str, str, str]] = set()

    def visit(node: ast.AST, function: str) -> None:
        for child in ast.iter_child_nodes(node):
            inner = (
                child.name
                if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef)
                else function
            )
            if isinstance(child, ast.Call):
                target = _destination(child)
                if target is not None:
                    text = ast.get_source_segment(source, target) or ""
                    if _names_an_env_file(text) or _by_its_own_name(target):
                        found.add((relative, function, text))
            visit(child, inner)

    visit(tree, "<module>")
    return found


def _tree_writes() -> set[tuple[str, str, str]]:
    found: set[tuple[str, str, str]] = set()
    for folder in SCANNED:
        for path in sorted((CORE / folder).rglob("*.py")):
            relative = str(path.relative_to(CORE))
            if relative == "harness/atomic.py":
                continue
            found |= in_place_writes(path.read_text(encoding="utf-8"), relative)
    return found


def test_no_module_writes_an_env_file_in_place() -> None:
    unexpected = _tree_writes() - ALLOWED
    assert not unexpected, (
        "these write deployment.env (or a folder's files by name) in place; send them through "
        f"harness.atomic.replace_whole, or list a fresh copy in ALLOWED with its reason: {unexpected}"
    )


def test_no_allowed_entry_is_stale() -> None:
    assert not ALLOWED - _tree_writes()


# The scan shown red with each writer's real shape, as it stood at c5209b1.


def test_the_scan_flags_register_sign_in_s_rewrite() -> None:
    planted = (
        "def _write_env_value(env_path, key, value):\n"
        "    lines = env_path.read_text(encoding='utf-8').splitlines()\n"
        "    env_path.write_text('\\n'.join(lines) + '\\n', encoding='utf-8')\n"
    )
    assert in_place_writes(planted, "harness/register_sign_in.py") == {
        ("harness/register_sign_in.py", "_write_env_value", "env_path")
    }


def test_the_scan_flags_update_s_put_back_copy() -> None:
    planted = (
        "import shutil\n"
        "def _put_back(directory, point):\n"
        "    for item in point.iterdir():\n"
        "        shutil.copy2(item, directory / item.name)\n"
    )
    assert in_place_writes(planted, "harness/update.py") == {
        ("harness/update.py", "_put_back", "directory / item.name")
    }


def test_the_scan_flags_an_open_for_writing_and_an_os_open() -> None:
    planted = (
        "import os\n"
        "def a(env_file):\n"
        "    with open(env_file, 'w') as f: f.write('x')\n"
        "def b(env_file):\n"
        "    os.open(env_file, os.O_WRONLY | os.O_TRUNC)\n"
        "def c(env_file):\n"
        "    with env_file.open('r+b') as f: f.write(b'x')\n"
        "def d(env_file):\n"
        "    env_file.read_text()\n"
    )
    found = {function for _, function, _ in in_place_writes(planted, "x.py")}
    assert found == {"a", "b", "c"}


# Each writer at its own call site.


def _kept_link(path: Path) -> Path:
    """A second name for the file as it is now, outside its folder (which put-back clears of what
    the rollback point does not hold)."""
    link = path.parent.parent / (path.name + ".old-inode")
    os.link(path, link)
    return link


def _deployment(tmp_path: Path) -> Path:
    folder = tmp_path / "osprey-local"
    folder.mkdir()
    env = folder / "deployment.env"
    env.write_text(OLD, encoding="utf-8")
    env.chmod(0o600)
    return env


def test_register_sign_in_replaces_deployment_env_rather_than_rewriting_it(
    tmp_path: Path,
) -> None:
    env = _deployment(tmp_path)
    before = _kept_link(env)
    register_sign_in._write_env_value(env, "OSPREY_DEMO_ADMIN_PASSWORD", "fresh")
    assert "OSPREY_DEMO_ADMIN_PASSWORD=fresh" in env.read_text(encoding="utf-8")
    assert before.read_text(encoding="utf-8") == OLD
    assert env.stat().st_mode & 0o777 == 0o600


def test_restore_replaces_deployment_env_rather_than_rewriting_it(tmp_path: Path) -> None:
    env = _deployment(tmp_path)
    before = _kept_link(env)
    restore._set_env_line(env, "SUPERSET_SECRET_KEY", "carried-key")
    text = env.read_text(encoding="utf-8")
    assert "SUPERSET_SECRET_KEY=carried-key" in text and "old-key" not in text
    assert before.read_text(encoding="utf-8") == OLD
    assert env.stat().st_mode & 0o777 == 0o600


def test_update_s_put_back_replaces_deployment_env_rather_than_rewriting_it(
    tmp_path: Path,
) -> None:
    env = _deployment(tmp_path)
    directory = env.parent
    point = update._keep_rollback_point(directory, "v0.5.0", "abc123")
    env.write_text("OSPREY_POSTGRES_PASSWORD=newer\n", encoding="utf-8")
    newer = _kept_link(env)
    update._put_back(directory, point)
    assert env.read_text(encoding="utf-8") == OLD
    assert newer.read_text(encoding="utf-8") == "OSPREY_POSTGRES_PASSWORD=newer\n"
    assert env.stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize("link_it", [False, True])
def test_put_back_keeps_a_symlinked_deployment_env_a_link(tmp_path: Path, link_it: bool) -> None:
    env = _deployment(tmp_path)
    directory = env.parent
    if link_it:
        real = tmp_path / "secrets" / "deployment.env"
        real.parent.mkdir()
        env.rename(real)
        env.symlink_to(real)
    point = update._keep_rollback_point(directory, "v0.5.0", "abc123")
    env.write_text("OSPREY_POSTGRES_PASSWORD=newer\n", encoding="utf-8")
    update._put_back(directory, point)
    assert env.is_symlink() is link_it
    assert env.read_text(encoding="utf-8") == OLD
