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


def test_a_deployment_rendered_from_main_between_releases_is_never_up_to_date(
    tmp_path: Path, github: tuple[_GitHub, str], capsys: pytest.CaptureFixture[str]
) -> None:
    """A deployment stamped `v0.7.0-dev` (main's VERSION before the cut, from a tree with changes or without git: ADR-114
    Amendment 47) is the release it is heading to, not that release: the check says it builds from its checkout, and
    offers no update, never "Up to date"."""
    fake, base = github
    fake.releases = [_release("v0.6.1")]
    directory = _deployment(tmp_path, "v0.7.0-dev")
    assert _check(directory, _checkout(tmp_path, "https://github.com/acme/ospreyflow"), base) == 0
    said = capsys.readouterr().out
    assert "Up to date" not in said
    assert "builds from its checkout (v0.7.0-dev)" in said and "v0.6.1" in said
    notice = json.loads((directory / "state" / "update.json").read_text())
    assert notice["update_available"] is False


def _code_tree(tmp_path: Path, form: str) -> Path:
    """A code tree whose `checkout_version` returns each form it can (ADR-114 Amendment 47):
    `dev-<sha>` (clean git tree, VERSION `-dev`), `v0.7.0-dev` (the stamped text: a tree with no git),
    and a bare tag (VERSION `v0.6.1`)."""
    code = tmp_path / f"code-{form}"
    code.mkdir()
    (code / "VERSION").write_text("v0.6.1\n" if form == "tag" else "v0.7.0-dev\n")
    if form == "stamped":
        return code
    git = ["git", "-C", str(code), "-c", "user.name=t", "-c", "user.email=t@example.invalid"]
    subprocess.run(["git", "init", "-q", str(code)], check=True)
    subprocess.run([*git, "add", "VERSION"], check=True)
    subprocess.run([*git, "commit", "-q", "-m", "x"], check=True)
    return code


@pytest.mark.parametrize(
    ("form", "says_up_to_date"), [("sha", False), ("stamped", False), ("tag", True)]
)
def test_every_form_checkout_version_returns_is_worded_right(
    tmp_path: Path,
    github: tuple[_GitHub, str],
    capsys: pytest.CaptureFixture[str],
    form: str,
    says_up_to_date: bool,
) -> None:
    """The three forms a deployment can be rendered with: `dev-<sha>` and `v0.7.0-dev` are builds from the checkout and
    are never told they are up to date (the newest published release is v0.6.1); a bare tag that is the newest is."""
    from harness.release import checkout_version

    fake, base = github
    fake.releases = [_release("v0.6.1")]
    current = checkout_version(_code_tree(tmp_path, form))
    assert current.startswith("dev-") if form == "sha" else True
    assert current == {"stamped": "v0.7.0-dev", "tag": "v0.6.1"}.get(form, current)
    directory = _deployment(tmp_path, current)
    assert _check(directory, _checkout(tmp_path, "https://github.com/acme/ospreyflow"), base) == 0
    said = capsys.readouterr().out
    assert ("Up to date" in said) is says_up_to_date
    if not says_up_to_date:
        assert f"builds from its checkout ({current})" in said


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
