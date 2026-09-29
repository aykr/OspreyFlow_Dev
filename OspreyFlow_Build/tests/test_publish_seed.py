"""The Trigger B rehearsal's own seed script — `tools/publish_seed.py`'s own docstring has the
full reasoning, including why it copies file content at a given commit rather than the live
working tree, and why the identity is set per-repository rather than `--global`."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from tools.layout import CORE

sys.path.insert(0, str(CORE))

from tools.publish_seed import (  # noqa: E402
    NEUTRAL_EMAIL,
    NEUTRAL_NAME,
    classify,
    init_neutral_repo,
    is_private_tree_path,
    seed_tree,
)


def test_a_process_path_is_private() -> None:
    assert is_private_tree_path("process/07_BUILD_PLAN.md")
    assert is_private_tree_path("process/archive/README.md")


def test_the_root_claude_md_stub_is_private() -> None:
    assert is_private_tree_path("CLAUDE.md")


def test_dot_claude_and_graphifyignore_are_private() -> None:
    assert is_private_tree_path(".claude/settings.json")
    assert is_private_tree_path(".graphifyignore")


def test_a_lookalike_path_is_not_private() -> None:
    """The exact-path/prefix rule, not a substring one — a real file that merely contains the
    marker text as part of a longer name must not be wrongly excluded."""
    assert not is_private_tree_path("not-process/thing.md")
    assert not is_private_tree_path("packages/schemas/CLAUDE_MD_PARSER.py")


def test_product_source_is_not_private() -> None:
    for path in ("README.md", "spec/00_ARCHITECTURE.md", "packages/schemas/domain.py"):
        assert not is_private_tree_path(path)


def test_06_decisions_is_excluded_even_though_it_lives_in_spec() -> None:
    """Regression: a first version of this script used PRIVATE_TREE_MARKERS alone as its own
    exclusion set and seeded `spec/06_DECISIONS.md` into the publishable tree — found running this
    round's own rehearsal against the real repository, not assumed safe from the constant's name.
    ADR-034 §B2 is explicit and separate from `product_tree_link_check.py`'s own marker list:
    `06_DECISIONS.md` is "Excluded and private" from publication even though it physically sits in
    `spec/` and is not one of `PRIVATE_TREE_MARKERS`'s own four entries."""
    assert is_private_tree_path("spec/06_DECISIONS.md")
    # The other spec/ files must NOT be swept up by the same fix.
    assert not is_private_tree_path("spec/00_ARCHITECTURE.md")
    assert not is_private_tree_path("spec/01_DOMAIN_MODEL.md")


def test_classify_actually_flags_a_planted_private_file(tmp_path: Path) -> None:
    """Non-vacuous, the same discipline this repository's other gates are held to: red first
    against a real, isolated commit carrying a planted private-tree file, not just the marker
    function in isolation."""
    repo = tmp_path / "fixture-repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    (repo / "README.md").write_text("# Fixture\n", encoding="utf-8")
    (repo / "process").mkdir()
    (repo / "process" / "07_BUILD_PLAN.md").write_text("leaked\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "fixture"],
        cwd=repo,
        check=True,
        env={
            "PATH": os.environ["PATH"],
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@t",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@t",
        },
    )

    from tools.publish_seed import list_tracked_files

    included, excluded = classify(list_tracked_files("HEAD", repo_root=repo))
    assert excluded == ["process/07_BUILD_PLAN.md"]
    assert included == ["README.md"]

    # Remove the private file and show green — the same file is no longer flagged once it's gone.
    (repo / "process" / "07_BUILD_PLAN.md").unlink()
    (repo / "process").rmdir()
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "remove leaked file"],
        cwd=repo,
        check=True,
        env={
            "PATH": os.environ["PATH"],
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@t",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@t",
        },
    )
    included2, excluded2 = classify(list_tracked_files("HEAD", repo_root=repo))
    assert excluded2 == []
    assert included2 == ["README.md"]


def test_seed_tree_copies_content_at_the_given_commit_not_the_working_tree(tmp_path: Path) -> None:
    """The load-bearing property: an uncommitted change on disk must never leak into the seed, and
    a commit other than the latest must seed exactly what was tracked then."""
    repo = tmp_path / "fixture-repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    env = {
        "PATH": os.environ["PATH"],
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@t",
    }
    (repo / "README.md").write_text("committed content\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "c1"], cwd=repo, check=True, env=env)

    # An uncommitted change on disk after the commit — must not appear in the seed.
    (repo / "README.md").write_text("uncommitted change\n", encoding="utf-8")

    dest = tmp_path / "seeded"
    included, excluded = seed_tree("HEAD", dest, repo_root=repo)
    assert included == ["README.md"]
    assert excluded == []
    assert (dest / "README.md").read_text(encoding="utf-8") == "committed content\n"


def test_init_neutral_repo_commits_under_the_neutral_identity(tmp_path: Path) -> None:
    dest = tmp_path / "seeded"
    dest.mkdir()
    (dest / "README.md").write_text("# Fixture\n", encoding="utf-8")
    init_neutral_repo(dest)

    log = subprocess.run(
        ["git", "log", "--format=%an|%ae", "-1"],
        cwd=dest,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert log == f"{NEUTRAL_NAME}|{NEUTRAL_EMAIL}"

    count = subprocess.run(
        ["git", "rev-list", "--count", "HEAD"],
        cwd=dest,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert count == "1", "the seeded repository must have exactly one commit, not inherited history"
