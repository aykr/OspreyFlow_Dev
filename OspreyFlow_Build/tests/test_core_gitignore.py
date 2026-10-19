"""The product folder's own `.gitignore` keeps a user's secrets and data out of their commits.

The user repository is `OspreyFlow_Core` alone (ADR-114 Amendment 21), so the development root's
`.gitignore` — which is where these rules lived — never reaches a user. Until 19 October 2026 the
product's own file named only `.install/` and `.cloud/`, so `git add -A` in a clone or fork after
`ospreyflow install` would have committed `deploy/generated/<profile>/deployment.env` (the
generated passwords), every backup set and the local data (the review of 18 October 2026).

Each path below is one the `ospreyflow` command or the harness writes inside a checkout. The test
writes it into a scratch repository holding only the product's `.gitignore` and asks git itself
whether it is ignored — git's own matching, not a reading of the file — so a rule that looks right
but does not match fails here.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from tools.layout import CORE

#: (what writes it, a path it writes) — every one must be ignored.
WRITTEN_IN_A_CHECKOUT: tuple[tuple[str, str], ...] = (
    ("harness.apply: the deployment's passwords", "deploy/generated/local-lite/deployment.env"),
    ("harness.render: the rendered compose file", "deploy/generated/local-lite/compose.yaml"),
    ("harness.backup: a backup set", "backups/2026-10-19T07-00-00/manifest.json"),
    ("local data", "data/tmp/scratch.bin"),
    ("the guided install page's answers", ".install/answers.json"),
    ("OpenTofu state for a cloud install", ".cloud/aws/terraform.tfstate"),
    ("the real-data exceptions list (rule 9)", "config/real_data_exceptions.yaml"),
    ("a local configuration", "osprey.local.yaml"),
    ("Python environment", ".venv/bin/python"),
    ("Python bytecode", "services/api/__pycache__/app.cpython-312.pyc"),
    ("Node packages", "node_modules/react/index.js"),
    ("the Glass's build", "apps/workspace/dist/index.html"),
    ("the harness page's build", "apps/harness/dist/index.html"),
    ("browser-test output", "apps/workspace/test-results/run.json"),
)

#: Paths that must stay trackable: an over-broad rule would hide the product itself.
TRACKED: tuple[str, ...] = (
    "osprey.yaml",
    "deploy/compose/dev.yaml",
    "config/real_data_exceptions.example.yaml",
    "services/api/app.py",
    "apps/workspace/src/App.tsx",
)


@pytest.fixture
def scratch(tmp_path: Path) -> Path:
    if shutil.which("git") is None:
        pytest.skip("git is not installed")
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    shutil.copyfile(CORE / ".gitignore", tmp_path / ".gitignore")
    return tmp_path


def _ignored(repo: Path, relative: str) -> bool:
    path = repo / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x")
    result = subprocess.run(
        ["git", "-C", str(repo), "check-ignore", "-q", relative], check=False
    )
    return result.returncode == 0


@pytest.mark.parametrize(("what", "relative"), WRITTEN_IN_A_CHECKOUT)
def test_what_ospreyflow_writes_in_a_checkout_is_ignored(
    scratch: Path, what: str, relative: str
) -> None:
    assert _ignored(scratch, relative), f"{relative} ({what}) would be committed by `git add -A`"


@pytest.mark.parametrize("relative", TRACKED)
def test_the_product_itself_is_not_ignored(scratch: Path, relative: str) -> None:
    assert not _ignored(scratch, relative), f"{relative} is the product's and must be trackable"
