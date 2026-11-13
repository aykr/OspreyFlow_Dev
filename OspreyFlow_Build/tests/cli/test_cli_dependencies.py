"""ADR-114 decision 3: the `ospreyflow` command is its own package (`cli/`), "depending on nothing but the
standard library and PyYAML", installed alone by `uv tool install` (install.sh; the cloud-platform install's
*What it needs*); work needing more runs in the checkout's own environment. So no module of the command
imports anything else when it loads, and `release` and `run`, which need httpx, run again in the checkout.

R1 on kind, 13 November 2026: install block 7's `ospreyflow images push` stopped at
`ModuleNotFoundError: No module named 'httpx'`. `main.py` imports `conduit_client`, which imported httpx at
module level (58bcfc3), so every verb of such an install failed, the owner's own on osprey-small with them.
The orchestrator's ruling: keep decision 3 (no new dependency)."""

from __future__ import annotations

import ast
import importlib.metadata
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

CORE = Path(__file__).resolve().parents[3] / "OspreyFlow_Core"
CLI = CORE / "cli"
ALLOWED = {"yaml"}  # PyYAML, the one the decision names


def _loaded_imports(source: str) -> set[str]:
    """The top-level modules a module imports when it loads: its own statements, and those under an `if`
    or `try` there, but not under `if TYPE_CHECKING:` nor inside a function or class."""
    names: set[str] = set()

    def visit(body: list[ast.stmt]) -> None:
        for node in body:
            if isinstance(node, ast.Import):
                names.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names.add(node.module.split(".")[0])
            elif isinstance(node, ast.If):
                if not (isinstance(node.test, ast.Name) and node.test.id == "TYPE_CHECKING"):
                    visit(node.body)
                visit(node.orelse)
            elif isinstance(node, ast.Try):
                for part in (node.body, node.orelse, node.finalbody, *(h.body for h in node.handlers)):
                    visit(part)

    visit(ast.parse(source).body)
    return {n for n in names if n not in sys.stdlib_module_names and n not in {"ospreyflow", "__future__"}}


def test_no_module_of_the_command_loads_more_than_pyyaml() -> None:
    loaded = {
        path.name: extra
        for path in sorted((CLI / "ospreyflow").rglob("*.py"))
        if (extra := _loaded_imports(path.read_text()) - ALLOWED)
    }
    assert loaded == {}


def test_the_check_sees_a_load_time_import_in_the_shape_conduit_client_had() -> None:
    """Rule 15: the shape 58bcfc3 gave `conduit_client.py`, and the shapes that are allowed."""
    assert _loaded_imports("from __future__ import annotations\nimport json\n\nimport httpx\n") == {"httpx"}
    assert _loaded_imports("try:\n    import httpx\nexcept ImportError:\n    pass\n") == {"httpx"}
    assert _loaded_imports("from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    import httpx\n") == set()
    assert _loaded_imports("def client():\n    import httpx\n") == set()
    assert _loaded_imports("from . import conduit_client\nfrom ospreyflow import demo\n") == set()


# -- the command as `uv tool install ./cli` gives it: an environment of its own, holding PyYAML alone --------


@pytest.fixture(scope="module")
def small(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A fresh environment (none of the checkout's packages) with the package's declared dependency alone:
    PyYAML's files copied from the environment running these tests. Its Python, run with `-I`, sees only it
    and `cli/`.

    Not `uv pip install --offline pyyaml`: CI run 43471935601 (627745f), all five tests below erroring at
    setup with "pyyaml was not found in the cache". A cache that `uv sync` filled from the lock holds the
    wheel but not the index's page for it, which an unpinned offline resolve needs, so that install worked
    only where the cache had resolved PyYAML before (a developer's, not CI's fresh one)."""
    uv = shutil.which("uv")
    if uv is None:
        pytest.skip("uv is not on PATH")
    if not (CORE / ".venv").is_dir():
        pytest.skip("the checkout has no environment (uv sync) to run release and run in")
    venv = tmp_path_factory.mktemp("small") / "venv"
    subprocess.run([uv, "venv", "-q", "--no-project", "--python", sys.executable, str(venv)], check=True)
    python = venv / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    site = Path(subprocess.run([str(python), "-I", "-c", "import sysconfig; print(sysconfig.get_paths()['purelib'])"],
                               capture_output=True, text=True, check=True).stdout.strip())
    pyyaml = importlib.metadata.distribution("PyYAML")
    for file in pyyaml.files or ():
        if file.parts[0] == ".." or "__pycache__" in file.parts:
            continue  # its console scripts (none) and byte-code, which the small environment makes itself
        (site / file).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(Path(str(pyyaml.locate_file(file))), site / file)
    assert subprocess.run([str(python), "-I", "-c", "import yaml"], capture_output=True).returncode == 0
    assert subprocess.run([str(python), "-I", "-c", "import httpx"], capture_output=True).returncode != 0
    return python


def _ospreyflow(python: Path, tmp: Path, *argv: str, **env: str) -> subprocess.CompletedProcess[str]:
    run = (f"import sys; sys.path.insert(0, {str(CLI)!r})\n"
           "from ospreyflow.main import main\nsys.exit(main())")
    home = tmp / "home"
    home.mkdir(exist_ok=True)
    keep = {k: v for k, v in os.environ.items() if k in ("PATH", "SYSTEMROOT", "TMPDIR", "TEMP", "TMP")}
    return subprocess.run(
        [str(python), "-I", "-c", run, *argv], capture_output=True, text=True, cwd=tmp, timeout=120,
        env={**keep, "HOME": str(home), "OSPREYFLOW_HOME": str(CORE), **env},
    )


def _no_import_error(done: subprocess.CompletedProcess[str]) -> None:
    assert "ModuleNotFoundError" not in done.stderr + done.stdout, done.stderr[-800:]
    assert "Traceback" not in done.stderr, done.stderr[-800:]


def test_help_from_the_small_install(small: Path, tmp_path: Path) -> None:
    done = _ospreyflow(small, tmp_path, "--help")
    _no_import_error(done)
    assert done.returncode == 0 and "release" in done.stdout


def test_images_push_from_the_small_install_reaches_its_own_work(small: Path, tmp_path: Path) -> None:
    done = _ospreyflow(small, tmp_path, "images", "push", "--registry", "127.0.0.1:9", "--from",
                       str(tmp_path / "no-such-render"))
    _no_import_error(done)
    assert done.returncode != 0
    assert "no-such-render" in done.stderr + done.stdout


def test_release_from_the_small_install_runs_in_the_checkout(small: Path, tmp_path: Path) -> None:
    """It reaches httpx through the checkout's environment and the Conduit's address, refused in words
    (nothing listens on port 9)."""
    done = _ospreyflow(small, tmp_path, "release", "export", "pid", "--name", "r", "--release-version", "1",
                       "--out", "bundle", OSPREY_API_URL="http://127.0.0.1:9", OSPREY_TOKEN="t")
    _no_import_error(done)
    assert done.returncode == 1
    assert "The Conduit at http://127.0.0.1:9 could not be reached (ConnectError)" in done.stderr


def test_run_from_the_small_install_runs_in_the_checkout(small: Path, tmp_path: Path) -> None:
    """With no service identity, its own refusal, which comes after its client is made (httpx), in
    full: the line names OSPREY_CLIENT_SECRET, which the command's step runner would have hidden."""
    done = _ospreyflow(small, tmp_path, "run", "pid", "p", "--external-run-id", "dag:1",
                       OSPREY_API_URL="http://127.0.0.1:9")
    _no_import_error(done)
    assert done.returncode == 1 and "OSPREY_TOKEN_URL" in done.stderr


def test_a_checkout_without_httpx_is_refused_in_words(small: Path, tmp_path: Path) -> None:
    """Run again in an environment that still lacks httpx, the command says so and never loops."""
    done = _ospreyflow(small, tmp_path, "run", "pid", "p", "--external-run-id", "dag:1",
                       OSPREY_API_URL="http://127.0.0.1:9", OSPREYFLOW_IN_CHECKOUT="1")
    _no_import_error(done)
    assert done.returncode == 1 and "uv sync --frozen" in done.stderr
