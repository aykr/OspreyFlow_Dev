"""`tools/no_langchain_check.py` (`06_DECISIONS.md` ADR-135 Amendment 6 decision 1): an image or
deployment without Laurium carries no LangChain, spaCy or Laurium.

Two legs, each shown red here on a plant of the shape it really reads (rule 15):

- **the image leg** reads the distributions installed in a built image, as the JSON its in-image
  script prints (`IMAGE_SCRIPT`, run by `docker run` in CI's image jobs): a planted LangChain,
  Laurium or spaCy among real-looking rows is named;
- **the source leg** reads the tree a Conduit or worker image is built from: Laurium's folder left
  out of the Conduit's build context (`.dockerignore`), and no LangChain or Laurium in the Conduit's
  `pyproject.toml` or `uv.lock`, nor installed by any Dockerfile but Laurium's own. Planted in a copy
  of those files.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from tools import no_langchain_check as check
from tools.layout import CORE

REAL_ROWS = [
    {"name": "fastapi", "version": "0.146.0"},
    {"name": "httpx", "version": "0.28.1"},
    {"name": "pydantic", "version": "2.14.3"},
]


def _printed(rows: list[dict[str, str]]) -> str:
    """What `IMAGE_SCRIPT` prints inside an image: one JSON list of name and version."""
    return json.dumps(rows)


def test_an_image_without_any_passes() -> None:
    assert check.forbidden_in_image(_printed(REAL_ROWS)) == []


@pytest.mark.parametrize(
    "name",
    ["langchain-core", "langchain_openai", "LangChain", "laurium", "spacy", "en-core-web-sm",
     "langsmith", "langchain-community"],  # fmt: skip
)
def test_a_planted_distribution_is_named(name: str) -> None:
    rows = [*REAL_ROWS, {"name": name, "version": "1.0"}]
    assert check.forbidden_in_image(_printed(rows)) == [f"{name} 1.0"]


def test_the_image_script_prints_what_the_leg_reads() -> None:
    """The script run inside the image is run here, on this interpreter, and its output read by
    the same function: the shape the leg receives is the script's, not a hand-written one."""
    out = subprocess.run(
        [sys.executable, "-c", check.IMAGE_SCRIPT], capture_output=True, text=True, check=True
    )
    rows = json.loads(out.stdout)
    assert {"name", "version"} <= set(rows[0])
    assert check.forbidden_in_image(out.stdout) == []  # the Conduit's own environment


def test_output_that_is_not_the_list_is_a_refusal_not_a_pass() -> None:
    with pytest.raises(check.Unreadable):
        check.forbidden_in_image("Traceback (most recent call last): ...")


def _tree(tmp_path: Path) -> Path:
    root = tmp_path / "core"
    root.mkdir()
    for name in (".dockerignore", "pyproject.toml", "uv.lock"):
        shutil.copy(CORE / name, root / name)
    for dockerfile in CORE.glob("services/*/Dockerfile"):
        target = root / dockerfile.relative_to(CORE)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(dockerfile, target)
    return root


def test_the_real_tree_passes() -> None:
    assert check.source_problems(CORE) == []


def test_the_copied_tree_passes(tmp_path: Path) -> None:
    assert check.source_problems(_tree(tmp_path)) == []


def test_laurium_left_in_the_conduits_build_context_is_named(tmp_path: Path) -> None:
    root = _tree(tmp_path)
    ignore = root / ".dockerignore"
    lines = ignore.read_text().splitlines()
    ignore.write_text("\n".join(line for line in lines if line.strip() != "services/laurium") + "\n")
    assert any(".dockerignore" in p for p in check.source_problems(root))


def test_langchain_in_the_conduits_dependencies_is_named(tmp_path: Path) -> None:
    root = _tree(tmp_path)
    pyproject = root / "pyproject.toml"
    pyproject.write_text(
        pyproject.read_text().replace("dependencies = [", 'dependencies = [\n    "langchain-core>=1.0",', 1)
    )
    assert any("pyproject.toml" in p for p in check.source_problems(root))


def test_laurium_in_the_lock_is_named(tmp_path: Path) -> None:
    root = _tree(tmp_path)
    lock = root / "uv.lock"
    lock.write_text(lock.read_text() + '\n[[package]]\nname = "laurium"\nversion = "0.6.0"\n')
    assert any("uv.lock" in p for p in check.source_problems(root))


def test_another_dockerfile_installing_langchain_is_named(tmp_path: Path) -> None:
    root = _tree(tmp_path)
    worker = root / "services/worker/Dockerfile"
    worker.write_text(worker.read_text() + "\nRUN pip install langchain-openai==1.7.4\n")
    problems = check.source_problems(root)
    assert any("services/worker/Dockerfile" in p for p in problems)


def test_laurium_s_own_dockerfile_may_install_it(tmp_path: Path) -> None:
    root = _tree(tmp_path)
    assert (root / "services/laurium/Dockerfile").is_file()
    assert not any("services/laurium/Dockerfile" in p for p in check.source_problems(root))
