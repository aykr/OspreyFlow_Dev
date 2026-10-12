"""The publish step (`06_DECISIONS.md` ADR-114 decision 1, Amendment 2 point 4): the product folder,
as committed, copied into the user repository — and nothing at all if any file would carry this
repository's name, an internal demo's data or code, a home-folder path or a personal authorship
identifier out with it. Each refusal is planted in a real commit of a throwaway repository, in the
shape it would really take.

What a mistake would do, and the case that catches it:
- the Build folder named in a published file — `test_a_mention_of_the_build_folder_is_refused`;
- an internal demo's data, code or the local exceptions list leaving —
  `test_an_internal_demos_data_code_or_the_exceptions_list_is_refused`;
- a machine path leaving — `test_a_home_folder_path_is_refused_in_each_shape`;
- the owner's identity leaving — `test_a_personal_authorship_identifier_is_refused`;
- a refused publish leaving a half-written folder — every refusal asserts nothing was written;
- an uncommitted local change leaving (the owner's `osprey.yaml`) —
  `test_only_what_is_committed_is_copied`;
- publishing into this repository, or over something — `test_the_destination_must_be_new_and_outside`.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tools.publish_user_repo import PublishRefused, publish

CLEAN = {
    "README.md": "# OspreyFlow\n\nRun `ospreyflow install`.\n",
    "osprey.yaml": "profile: local-lite\nbasemap:\n  tiles: ./data/basemap\n",
    "scripts/demo_registry.py": "REGISTRY = ()\n",
    "packages/demo_fixtures/hmp.py": "PEOPLE = 400\n",
}


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                          check=True).stdout.strip()  # fmt: skip


def _commit(repo: Path, files: dict[str, str], message: str = "c") -> str:
    for name, text in files.items():
        path = repo / "OspreyFlow_Core" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-q", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q")
    (root / "OspreyFlow_Build").mkdir()
    (root / "OspreyFlow_Build" / "spec.md").write_text("private\n", encoding="utf-8")
    return root


def _refused(repo: Path, commit: str, out: Path) -> list[str]:
    with pytest.raises(PublishRefused) as refusal:
        publish(commit, out, repo_root=repo)
    assert not out.exists() or not any(out.iterdir()), "a refused publish writes nothing"
    return refusal.value.findings


def test_a_clean_commit_is_copied_whole_and_nothing_else(repo: Path, tmp_path: Path) -> None:
    commit = _commit(repo, CLEAN)
    out = tmp_path / "user-repo"
    written = publish(commit, out, repo_root=repo)
    assert sorted(written) == sorted(CLEAN)
    assert (out / "packages/demo_fixtures/hmp.py").read_text(encoding="utf-8") == "PEOPLE = 400\n"
    assert not (out / "OspreyFlow_Build").exists() and not (out / "OspreyFlow_Core").exists()


def test_a_mention_of_the_build_folder_is_refused(repo: Path, tmp_path: Path) -> None:
    commit = _commit(repo, {**CLEAN, "Makefile": "lint:\n\tPYTHONPATH=../OspreyFlow_Build python -m tools.x\n"})
    (finding,) = _refused(repo, commit, tmp_path / "out")
    assert finding.startswith("Makefile:2:") and "OspreyFlow_Build" in finding


def test_an_internal_demos_data_code_or_the_exceptions_list_is_refused(repo: Path, tmp_path: Path) -> None:
    commit = _commit(repo, {**CLEAN, "scripts/seed_enron.py": "def main(): ...\n",
                            "config/real_data_exceptions.yaml": "entries: []\n",
                            "OspreyFlow_Data/Enron_Mails/allen-p/1.": "From: someone\n"})  # fmt: skip
    findings = _refused(repo, commit, tmp_path / "out")
    assert {f.split(":")[0] for f in findings} == {
        "scripts/seed_enron.py", "config/real_data_exceptions.yaml", "OspreyFlow_Data/Enron_Mails/allen-p/1.",
    }  # fmt: skip


@pytest.mark.parametrize("line", ["tiles: /Users/someone/OspreyFlow_Data/basemap",
                                  "mount: /home/someone/data", "path: C:\\Users\\someone\\data"])  # fmt: skip
def test_a_home_folder_path_is_refused_in_each_shape(repo: Path, tmp_path: Path, line: str) -> None:
    commit = _commit(repo, {**CLEAN, "osprey.yaml": f"profile: local-lite\n{line}\n"})
    findings = _refused(repo, commit, tmp_path / "out")
    assert any(f.startswith("osprey.yaml:2:") and "home folder" in f for f in findings), findings


def test_a_container_users_home_is_not_a_machine_path(repo: Path, tmp_path: Path) -> None:
    """`/home/arcadedb/…` and `/home/ubuntu/…` are inside the images this product runs, not on
    anyone's machine (`harness/restore.py`, `deploy/compose/dev.yaml`); only those named users pass."""
    commit = _commit(repo, {**CLEAN, "harness/restore.py": 'BACKUPS = "/home/arcadedb/backups"\n',
                            "deploy/dev.yaml": "- models:/home/ubuntu/.cache/hub\n"})  # fmt: skip
    assert "harness/restore.py" in publish(commit, tmp_path / "out", repo_root=repo)


def test_a_personal_authorship_identifier_is_refused(repo: Path, tmp_path: Path) -> None:
    from tools.packaging_gate import AUTHORSHIP_PATTERN

    planted = "solirius"
    assert AUTHORSHIP_PATTERN.search(planted), "the planted name is one the gate knows"
    commit = _commit(repo, {**CLEAN, "NOTICE": f"Copyright {planted}\n"})
    (finding,) = _refused(repo, commit, tmp_path / "out")
    assert finding.startswith("NOTICE:1:") and "authorship" in finding


def test_only_what_is_committed_is_copied(repo: Path, tmp_path: Path) -> None:
    commit = _commit(repo, CLEAN)
    local = repo / "OspreyFlow_Core" / "osprey.yaml"
    local.write_text("tiles: /Users/someone/OspreyFlow_Data/basemap\n", encoding="utf-8")
    (repo / "OspreyFlow_Core" / "notes.txt").write_text("uncommitted\n", encoding="utf-8")
    out = tmp_path / "user-repo"
    publish(commit, out, repo_root=repo)
    assert (out / "osprey.yaml").read_text(encoding="utf-8") == CLEAN["osprey.yaml"]
    assert not (out / "notes.txt").exists()


def test_the_destination_must_be_new_and_outside(repo: Path, tmp_path: Path) -> None:
    commit = _commit(repo, CLEAN)
    with pytest.raises(PublishRefused, match="inside the repository"):
        publish(commit, repo / "published", repo_root=repo)
    taken = tmp_path / "taken"
    taken.mkdir()
    (taken / "keep.txt").write_text("mine\n", encoding="utf-8")
    with pytest.raises(PublishRefused, match="not empty"):
        publish(commit, taken, repo_root=repo)
    assert (taken / "keep.txt").read_text(encoding="utf-8") == "mine\n"
