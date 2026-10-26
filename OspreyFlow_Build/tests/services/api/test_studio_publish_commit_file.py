"""`commit_recipe_file` (ADR-127 Amendment 23, "The recipes"): the Prison Intelligence seed copies
each committed recipe byte for byte to `recipes/<id>.yaml` in the recipe repository and commits it
"as `write_and_commit_recipe` does". A re-serialisation (`serialise_recipe`) is not a byte-for-byte
copy: it reorders and drops the comments the committed files carry. So the commit half of
`write_and_commit_recipe` is one function both use, and what would fail if it broke:

- a copy that was re-serialised would differ from the source file
  (`test_the_file_in_the_repository_is_the_bytes_given`);
- a commit that failed silently would leave a registry row naming a path nobody committed
  (`test_the_file_is_committed_at_the_path_the_registry_row_will_name`);
- republishing identical bytes must not be an error, as for `write_and_commit_recipe`
  (`test_committing_the_same_bytes_again_is_not_an_error`);
- a changed file is a second commit (`test_changed_bytes_are_a_second_commit`);
- `write_and_commit_recipe` itself still writes `serialise_recipe` through the same function
  (`test_write_and_commit_recipe_goes_through_the_same_commit`).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from services.api import studio_publish
from services.api.studio_publish import (
    GitCommitError,
    commit_recipe_file,
    recipe_git_relative_path,
    serialise_recipe,
    write_and_commit_recipe,
)

from schemas.ingest import Recipe

DATA = b"# a comment a re-serialisation would drop\nid: r-one\nversion: 1\n"


def _git(repo: Path, *args: str) -> str:
    done = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True)
    return done.stdout


async def test_the_file_in_the_repository_is_the_bytes_given(tmp_path: Path) -> None:
    path = await commit_recipe_file("r-one", DATA, version=1, repo_root=tmp_path)
    assert path == recipe_git_relative_path("r-one") == "recipes/r-one.yaml"
    assert (tmp_path / path).read_bytes() == DATA


async def test_the_file_is_committed_at_the_path_the_registry_row_will_name(
    tmp_path: Path,
) -> None:
    path = await commit_recipe_file("r-one", DATA, version=1, repo_root=tmp_path)
    assert _git(tmp_path, "ls-files").split() == [path]
    assert _git(tmp_path, "log", "--format=%s").strip() == "ingest: publish r-one v1"
    assert _git(tmp_path, "status", "--porcelain").strip() == ""


async def test_committing_the_same_bytes_again_is_not_an_error(tmp_path: Path) -> None:
    await commit_recipe_file("r-one", DATA, version=1, repo_root=tmp_path)
    await commit_recipe_file("r-one", DATA, version=1, repo_root=tmp_path)
    assert len(_git(tmp_path, "log", "--format=%s").split("\n")) == 2  # one line and the end


async def test_changed_bytes_are_a_second_commit(tmp_path: Path) -> None:
    await commit_recipe_file("r-one", DATA, version=1, repo_root=tmp_path)
    await commit_recipe_file("r-one", DATA + b"label: x\n", version=2, repo_root=tmp_path)
    assert _git(tmp_path, "log", "--format=%s").split("\n")[:2] == [
        "ingest: publish r-one v2",
        "ingest: publish r-one v1",
    ]


async def test_a_failed_commit_is_an_error_not_a_quiet_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = studio_publish._run_git

    async def failing(*args: str, cwd: Path) -> tuple[int, str]:
        if args[0] == "commit":
            return 1, "fatal: something else"
        return await real(*args, cwd=cwd)

    monkeypatch.setattr(studio_publish, "_run_git", failing)
    with pytest.raises(GitCommitError):
        await commit_recipe_file("r-one", DATA, version=1, repo_root=tmp_path)


async def test_write_and_commit_recipe_goes_through_the_same_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[tuple[str, bytes, int]] = []
    real = studio_publish.commit_recipe_file

    async def spy(recipe_id: str, data: bytes, *, version: int, repo_root: Path) -> str:
        seen.append((recipe_id, data, version))
        return await real(recipe_id, data, version=version, repo_root=repo_root)

    monkeypatch.setattr(studio_publish, "commit_recipe_file", spy)
    recipe = Recipe.model_validate(
        {
            "id": "r-two", "version": 4, "label": "x", "connector": {"profile": "generic-csv"},
            "ontology_version": 16, "defaults": {"legal_basis": "x"},
            "row_template": {"entities": [], "edges": []},
        }
    )  # fmt: skip
    path = await write_and_commit_recipe(recipe, repo_root=tmp_path)
    assert path == "recipes/r-two.yaml"
    assert seen == [("r-two", serialise_recipe(recipe).encode("utf-8"), 4)]
    assert (tmp_path / path).read_text(encoding="utf-8") == serialise_recipe(recipe)
