"""The version a deployment shows is the code's, not its `.git`'s (ADR-114 Amendment 47; CARRIES 218).

The demo rebuild of 12 November copied main's code into `/opt/ospreyflow`, whose `.git` still sat on v0.5.0's tag:
glass.json, *Admin › System* and the update check then named v0.5.0 and its commit. The code now carries its own
version (`OspreyFlow_Core/VERSION`), read before `.git`; `.git` is believed only where its tree is the code's.

Every case is a real git checkout in a temporary folder, with the newer code copied over an older `.git`."""

from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from harness import site
from harness.release import VERSION_FILE, checkout_version, version_file_problem
from harness.render import release_version

CORE = Path(__file__).resolve().parents[3] / "OspreyFlow_Core"


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True).stdout.strip()


def _commit(repo: Path, message: str) -> None:
    _git(repo, "add", "-A")
    _git(repo, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", message)


@pytest.fixture
def released(tmp_path: Path) -> Path:
    """A checkout on v0.5.0's tag, its VERSION saying so, the tree its commit's."""
    repo = tmp_path / "ospreyflow"
    repo.mkdir()
    _git(repo, "init", "-q")
    (repo / "code.py").write_text("WHAT = 'v0.5.0'\n")
    (repo / VERSION_FILE).write_text("v0.5.0\n")
    _commit(repo, "v0.5.0")
    _git(repo, "tag", "v0.5.0")
    return repo


def _copy_newer_code(repo: Path, version: str) -> None:
    """What the demo rebuild did: newer code written over the checkout, its `.git` left where it was."""
    (repo / "code.py").write_text(f"WHAT = {version!r}\n")
    (repo / VERSION_FILE).write_text(f"{version}\n")


@pytest.mark.parametrize("version", ["v0.5.2", "v0.5.2-dev"])
def test_newer_code_over_an_older_git_shows_the_codes_version(released: Path, version: str) -> None:
    _copy_newer_code(released, version)
    assert checkout_version(released) == version


@pytest.mark.parametrize("version", ["v0.5.2", "v0.5.2-dev"])
def test_glass_json_and_the_rendered_release_version_are_the_codes(released: Path, version: str) -> None:
    """glass.json's `version` (the welcome page's footer) and `OSPREY_RELEASE_VERSION` (Admin › System, the
    update check) both name the code's version, never `.git`'s tag or commit."""
    _copy_newer_code(released, version)
    sha = _git(released, "rev-parse", "HEAD")
    shown = site.deployment_version(released)
    rendered = release_version(SimpleNamespace(components=SimpleNamespace(source_path=str(released))))  # type: ignore[arg-type]
    assert shown == rendered == version
    assert sha[:7] not in shown and "v0.5.0" not in shown


def test_a_release_checkout_is_its_release(released: Path) -> None:
    assert checkout_version(released) == site.deployment_version(released) == "v0.5.0"


def test_a_dev_checkout_whose_tree_is_its_commits_is_dev_and_its_commit(released: Path) -> None:
    (released / VERSION_FILE).write_text("v0.5.1-dev\n")
    _commit(released, "after v0.5.0")
    assert checkout_version(released) == f"dev-{_git(released, 'rev-parse', '--short', 'HEAD')}"


def test_a_dev_checkout_with_changed_code_is_the_codes_dev_version(released: Path) -> None:
    """A tracked file changed since the commit: the commit no longer names the code."""
    (released / VERSION_FILE).write_text("v0.5.1-dev\n")
    _commit(released, "after v0.5.0")
    (released / "code.py").write_text("WHAT = 'changed'\n")
    assert checkout_version(released) == "v0.5.1-dev"


def test_untracked_files_do_not_unseat_the_commit(released: Path) -> None:
    """A deployment's own files beside the code (osprey.yaml, rendered output) are not the code. On a `-dev`
    checkout, where the tree check decides (a release VERSION is shown before it is asked)."""
    (released / VERSION_FILE).write_text("v0.5.1-dev\n")
    _commit(released, "after v0.5.0")
    (released / "osprey.yaml").write_text("profile: lite\n")
    assert checkout_version(released) == f"dev-{_git(released, 'rev-parse', '--short', 'HEAD')}"


def test_code_with_no_git_at_all_is_its_version(tmp_path: Path) -> None:
    (tmp_path / VERSION_FILE).write_text("v0.5.2\n")
    assert checkout_version(tmp_path) == site.deployment_version(tmp_path) == "v0.5.2"


def test_code_with_no_version_file_keeps_the_checkouts_answer(tmp_path: Path) -> None:
    """A tree from before the file (an older release's checkout) is read from `.git` as before."""
    assert checkout_version(tmp_path) == "dev-unknown"


@pytest.mark.parametrize("text", ["0.5.2", "v0.5", "v0.5.2-rc1", "v0.5.2\nv0.5.3", ""])
def test_a_malformed_version_file_is_flagged(tmp_path: Path, text: str) -> None:
    (tmp_path / VERSION_FILE).write_text(text)
    assert version_file_problem(tmp_path) is not None


def test_a_malformed_version_file_is_never_shown(released: Path) -> None:
    (released / VERSION_FILE).write_text("v0.5.2-rc1\n")
    (released / "code.py").write_text("WHAT = 'newer'\n")
    assert checkout_version(released) != "v0.5.2-rc1"


def test_the_repositorys_own_version_file_is_well_formed() -> None:
    """The gate on the committed file: a release or the release the code is heading to, one line."""
    assert version_file_problem(CORE) is None, version_file_problem(CORE)
