"""`ospreyflow update --check` (ADR-114 Amendment 6 point 1, Amendment 8 point 2): asks the user
repository's releases from the machine it runs on and writes the notice the Conduit reads; says the
answer in words. The deployment's version is the one it was rendered with (`deployment.env`), not
whatever the checkout has moved to since."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from harness import update

from tests.harness.test_release import _GitHub, _release, github  # noqa: F401 - the fixture

__all__ = ["github"]


def _deployment(tmp_path: Path, version: str = "v0.4.1") -> Path:
    directory = tmp_path / "deploy" / "generated" / "local-lite"
    directory.mkdir(parents=True)
    (directory / "deployment.env").write_text(
        f"OSPREY_PROFILE=local-lite\nOSPREY_RELEASE_VERSION={version}\nOSPREY_X_PASSWORD=s3cret\n"
    )
    return directory


def _checkout(tmp_path: Path, origin: str) -> Path:
    repo = tmp_path / "checkout"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "remote", "add", "origin", origin], check=True)
    return repo


def _check(directory: Path, repo: Path, api: str) -> int:
    return update.main(
        ["--deployment", str(directory), "--check", "--github-api", api], repo_root=repo
    )


def test_a_newer_release_is_written_for_the_conduit_and_said(
    tmp_path: Path, github: tuple[_GitHub, str], capsys: pytest.CaptureFixture[str]
) -> None:
    fake, base = github
    fake.releases = [_release("v0.5.0", body="- Find connections")]
    directory = _deployment(tmp_path)
    repo = _checkout(tmp_path, "https://github.com/acme/ospreyflow.git")
    assert _check(directory, repo, base) == 0
    notice = json.loads((directory / "state" / "update.json").read_text())
    assert notice["current"] == "v0.4.1" and notice["latest"] == "v0.5.0"
    assert notice["update_available"] is True
    said = capsys.readouterr().out
    assert "v0.5.0 is available (this deployment is v0.4.1)" in said
    assert "ospreyflow update" in said and "- Find connections" in said


def test_up_to_date_is_said(
    tmp_path: Path, github: tuple[_GitHub, str], capsys: pytest.CaptureFixture[str]
) -> None:
    fake, base = github
    fake.releases = [_release("v0.4.1")]
    directory = _deployment(tmp_path)
    assert _check(directory, _checkout(tmp_path, "https://github.com/acme/ospreyflow"), base) == 0
    assert "Up to date: v0.4.1 is the newest release." in capsys.readouterr().out


def test_a_deployment_built_from_its_checkout_is_told_how_it_moves(
    tmp_path: Path, github: tuple[_GitHub, str], capsys: pytest.CaptureFixture[str]
) -> None:
    fake, base = github
    fake.releases = [_release("v0.5.0")]
    directory = _deployment(tmp_path, "dev-abc1234")
    assert _check(directory, _checkout(tmp_path, "https://github.com/acme/ospreyflow"), base) == 0
    said = capsys.readouterr().out
    assert "builds from its checkout (dev-abc1234)" in said and "v0.5.0" in said


def test_a_check_that_fails_is_written_too_and_exits_non_zero(
    tmp_path: Path, github: tuple[_GitHub, str], capsys: pytest.CaptureFixture[str]
) -> None:
    """The notice says why, so Admin → System does not keep showing an older answer as current."""
    fake, base = github
    fake.rate_limited = True
    directory = _deployment(tmp_path)
    assert _check(directory, _checkout(tmp_path, "https://github.com/acme/ospreyflow"), base) == 1
    notice = json.loads((directory / "state" / "update.json").read_text())
    assert "limit" in notice["problem"] and notice["update_available"] is False
    assert "limit" in capsys.readouterr().err


def test_an_origin_off_github_is_refused_in_words_and_written(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    directory = _deployment(tmp_path)
    repo = _checkout(tmp_path, "https://gitlab.com/acme/ospreyflow.git")
    assert _check(directory, repo, "http://127.0.0.1:9") == 1
    assert "update --from" in capsys.readouterr().err
    written = json.loads((directory / "state" / "update.json").read_text())
    assert "not a GitHub repository" in written["problem"]


def test_no_secret_from_the_deployment_is_ever_written_or_said(
    tmp_path: Path, github: tuple[_GitHub, str], capsys: pytest.CaptureFixture[str]
) -> None:
    fake, base = github
    fake.releases = [_release("v0.5.0")]
    directory = _deployment(tmp_path)
    _check(directory, _checkout(tmp_path, "https://github.com/acme/ospreyflow"), base)
    said = capsys.readouterr()
    assert "s3cret" not in (directory / "state" / "update.json").read_text()
    assert "s3cret" not in said.out + said.err
