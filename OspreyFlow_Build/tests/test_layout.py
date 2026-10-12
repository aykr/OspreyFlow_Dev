"""Where a repository path lives now that the tree has three folders (ADR-054).

Every check and many tests find files by their old repository-relative name (`spec/06_DECISIONS.md`,
`harness/apply.py`). Those names are kept as logical names and mapped to a folder in one place,
`tools/layout.py`. A mapping that is wrong sends a check to a file that is not there, and a check
that reads nothing passes, so each test below names what it would catch.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tools import layout


@pytest.mark.parametrize(
    ("logical", "folder"),
    [
        ("spec/06_DECISIONS.md", "OspreyFlow_Build"),
        ("tests/test_layout.py", "OspreyFlow_Build"),
        ("process/07_BUILD_PLAN.md", "OspreyFlow_Build"),
        ("tools/layout.py", "OspreyFlow_Build"),
        ("CLAUDE.md", "OspreyFlow_Build"),
        ("graphify-out/graph.json", "OspreyFlow_Build"),
        ("harness/apply.py", "core"),
        ("apps/workspace/src/App.tsx", "core"),
        ("scripts/launch.py", "core"),
        ("osprey.yaml", "core"),
        ("OspreyFlow_Data/enron/x.csv", ""),
        (".github/workflows/ci.yml", ""),
        ("internal_demos/seed_enron.py", "OspreyFlow_Build"),  # ADR-114 Am. 2
        ("Makefile", "OspreyFlow_Build"),  # the gates; Core's own Makefile is named by path (ADR-114 Am. 2)
        (".claude/settings.json", ""),
    ],
)
def test_each_logical_name_is_mapped_to_its_folder(logical: str, folder: str) -> None:
    """Catches a name sent to the wrong folder: the check then reads a file that is not there."""
    where = layout.home(logical)
    base = layout.CORE if folder == "core" else layout.ROOT / folder
    assert where == base / logical


def test_the_logical_root_maps_a_first_segment_and_leaves_the_rest_alone() -> None:
    assert layout.REPO / "spec" / "06_DECISIONS.md" == layout.BUILD / "spec" / "06_DECISIONS.md"
    assert layout.REPO / "apps/workspace/src" == layout.CORE / "apps" / "workspace" / "src"


def test_a_path_maps_back_to_its_logical_name() -> None:
    """The reverse, for messages and allowlists: they name `spec/x.md`, never an absolute path."""
    assert layout.logical(layout.BUILD / "spec" / "a.md") == "spec/a.md"
    assert layout.logical(layout.CORE / "harness" / "apply.py") == "harness/apply.py"
    assert layout.logical(layout.DATA / "enron" / "x") == "OspreyFlow_Data/enron/x"


def test_the_three_folders_and_the_root_are_where_the_names_say() -> None:
    assert layout.BUILD.name == "OspreyFlow_Build"
    assert layout.CORE.name == "OspreyFlow_Core"
    assert layout.CORE.parent == layout.ROOT
    assert layout.DATA.name == "OspreyFlow_Data"
    assert layout.BUILD.parent == layout.ROOT


def test_a_plain_repository_root_is_left_as_it_is(tmp_path: Path) -> None:
    """The checks are tested against small throwaway repositories, which have no three folders."""
    assert layout.at(tmp_path, "spec/x.md") == tmp_path / "spec" / "x.md"
    assert layout.at(layout.REPO, "spec/x.md") == layout.BUILD / "spec" / "x.md"


def test_rel_gives_a_logical_name_under_the_repository_and_a_plain_one_under_any_other_root(
    tmp_path: Path,
) -> None:
    """The checks print names into messages and compare them with allowlists written as
    `spec/x.md`. Catches a check that prints `OspreyFlow_Build/spec/x.md` and so never matches."""
    assert layout.rel(layout.BUILD / "spec" / "a.md", layout.REPO) == "spec/a.md"
    assert layout.rel(layout.CORE / "harness" / "b.py", layout.REPO) == "harness/b.py"
    assert layout.rel(tmp_path / "spec" / "a.md", tmp_path) == "spec/a.md"


def test_no_product_folder_is_left_at_the_root() -> None:
    """Catches the half-finished move (ADR-054 step 5): a product folder or manifest still at the
    root beside the three folders, found by `layout.home` in the wrong place or by nobody."""
    stayed = {"Makefile", ".git", ".gitignore", ".github", ".claude", "CLAUDE.md", ".trivyignore"}
    allowed = stayed | {"OspreyFlow_Core", "OspreyFlow_Build", "OspreyFlow_Data"}
    untracked_or_machine = {".venv", "data", "Icon\r", ".DS_Store", ".playwright-mcp"}
    left = {
        p.name
        for p in layout.ROOT.iterdir()
        if p.name not in allowed
        and p.name not in untracked_or_machine
        and not p.name.endswith("_cache")
        and not p.name.startswith("Icon")
    }
    assert left == set(), f"still at the root: {sorted(left)}"
