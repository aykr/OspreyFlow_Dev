"""ADR-114 decision 13, Amendment 6 point 1 and Amendment 8 points 1–3: a deployment's version, and
the update notice `ospreyflow update --check` writes for the Conduit to read.

GitHub is stood in for by a real HTTP server on loopback, which refuses as GitHub does (rule 15): an
unknown repository is a 404, a rate limit a 403 with `X-RateLimit-Remaining: 0`, and the list holds
drafts, pre-releases and tags that are not versions, none of which may be offered as an update.
"""

from __future__ import annotations

import json
import subprocess
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest
from harness.release import (
    ReleaseRefused,
    check_for_update,
    checkout_version,
    github_repository,
    newer,
    read_notice,
    write_notice,
)

NOW = "2026-10-13T08:00:00Z"


def _release(tag: str, *, draft: bool = False, prerelease: bool = False, body: str = "") -> dict:
    return {
        "tag_name": tag,
        "draft": draft,
        "prerelease": prerelease,
        "body": body,
        "html_url": f"https://github.com/acme/ospreyflow/releases/tag/{tag}",
    }


class _GitHub:
    """`GET /repos/acme/ospreyflow/releases` answered from `releases`; anything else as GitHub
    answers it."""

    def __init__(self) -> None:
        self.releases: list[dict] = []
        self.rate_limited = False
        self.failing = False
        self.asked: list[str] = []

    def handler(self) -> type[BaseHTTPRequestHandler]:
        github = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802 - the http.server name
                github.asked.append(self.path)
                if github.failing:
                    self._answer(502, {"message": "Server Error"})
                elif github.rate_limited:
                    self._answer(403, {"message": "API rate limit exceeded"},
                                 {"X-RateLimit-Remaining": "0"})  # fmt: skip
                elif self.path.startswith("/repos/acme/ospreyflow/releases"):
                    self._answer(200, github.releases)
                else:
                    self._answer(404, {"message": "Not Found"})

            def _answer(self, status: int, body: object, headers: dict | None = None) -> None:
                data = json.dumps(body).encode()
                self.send_response(status)
                for name, value in (headers or {}).items():
                    self.send_header(name, value)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *args: object) -> None:
                pass

        return Handler


@pytest.fixture
def github() -> Iterator[tuple[_GitHub, str]]:
    fake = _GitHub()
    server = HTTPServer(("127.0.0.1", 0), fake.handler())
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield fake, f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()


# --- versions ---------------------------------------------------------------------------------


def test_versions_compare_by_number_not_by_text() -> None:
    assert newer("v1.10.0", "v1.9.3")
    assert not newer("v1.9.3", "v1.10.0")
    assert not newer("v1.2.0", "v1.2.0")
    with pytest.raises(ReleaseRefused, match="not a version"):
        newer("v1.2", "v1.0.0")


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


@pytest.fixture
def checkout(tmp_path: Path) -> Path:
    repo = tmp_path / "checkout"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty",
         "-m", "a")  # fmt: skip
    return repo


def test_a_checkout_on_a_release_tag_is_that_release(checkout: Path) -> None:
    _git(checkout, "tag", "v0.4.1")
    assert checkout_version(checkout) == "v0.4.1"


def test_a_checkout_off_a_release_tag_is_dev_and_its_commit(checkout: Path) -> None:
    _git(checkout, "tag", "not-a-version")
    short = subprocess.run(
        ["git", "-C", str(checkout), "rev-parse", "--short", "HEAD"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()  # fmt: skip
    assert checkout_version(checkout) == f"dev-{short}"


def test_a_folder_that_is_no_checkout_says_so(tmp_path: Path) -> None:
    assert checkout_version(tmp_path) == "dev-unknown"


# --- the repository -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "origin",
    ["https://github.com/acme/ospreyflow.git", "https://github.com/acme/ospreyflow",
     "git@github.com:acme/ospreyflow.git"],
)  # fmt: skip
def test_the_repository_is_the_checkouts_origin_on_github(origin: str) -> None:
    assert github_repository(origin) == ("acme", "ospreyflow")


@pytest.mark.parametrize(
    "origin", ["https://gitlab.com/acme/ospreyflow.git", "", "/srv/mirror/ospreyflow",
               "https://github.com/acme"],
)  # fmt: skip
def test_an_origin_that_is_not_a_github_repository_is_refused_in_words(origin: str) -> None:
    with pytest.raises(ReleaseRefused, match="update --from"):
        github_repository(origin)


# --- the check -----------------------------------------------------------------------------------


def test_a_newer_release_is_offered_with_its_notes_and_address(
    github: tuple[_GitHub, str],
) -> None:
    fake, base = github
    fake.releases = [_release("v0.5.0", body="## v0.5.0\\n- Find connections"), _release("v0.4.1")]
    notice = check_for_update("v0.4.1", ("acme", "ospreyflow"), api_base=base, now=NOW)
    assert notice == {
        "current": "v0.4.1", "checked_at": NOW, "latest": "v0.5.0", "update_available": True,
        "notes": "## v0.5.0\\n- Find connections",
        "url": "https://github.com/acme/ospreyflow/releases/tag/v0.5.0", "problem": None,
    }  # fmt: skip
    assert fake.asked == ["/repos/acme/ospreyflow/releases?per_page=100"]


def test_drafts_prereleases_and_tags_that_are_not_versions_are_never_offered(
    github: tuple[_GitHub, str],
) -> None:
    fake, base = github
    fake.releases = [
        _release("v9.0.0", draft=True),
        _release("v8.0.0", prerelease=True),
        _release("nightly"),
        _release("v0.4.1"),
    ]
    notice = check_for_update("v0.4.1", ("acme", "ospreyflow"), api_base=base, now=NOW)
    assert notice["latest"] == "v0.4.1" and notice["update_available"] is False


def test_the_newest_is_chosen_by_number_whatever_order_github_lists_them_in(
    github: tuple[_GitHub, str],
) -> None:
    fake, base = github
    fake.releases = [_release("v0.9.0"), _release("v0.10.0"), _release("v0.2.0")]
    assert check_for_update("v0.2.0", ("acme", "ospreyflow"), api_base=base, now=NOW)[
        "latest"
    ] == "v0.10.0"


def test_a_deployment_built_from_a_checkout_is_never_told_to_update(
    github: tuple[_GitHub, str],
) -> None:
    fake, base = github
    fake.releases = [_release("v0.5.0")]
    notice = check_for_update("dev-abc1234", ("acme", "ospreyflow"), api_base=base, now=NOW)
    assert notice["latest"] == "v0.5.0" and notice["update_available"] is False


@pytest.mark.parametrize(
    ("set_up", "words"),
    [
        (lambda f: setattr(f, "releases", []), "has published no release yet"),
        (lambda f: setattr(f, "rate_limited", True), "limit"),
        (lambda f: setattr(f, "failing", True), "GitHub answered 502"),
    ],
)
def test_a_check_that_cannot_answer_says_why_and_offers_nothing(
    github: tuple[_GitHub, str], set_up: object, words: str
) -> None:
    fake, base = github
    set_up(fake)  # type: ignore[operator]
    notice = check_for_update("v0.4.1", ("acme", "ospreyflow"), api_base=base, now=NOW)
    assert notice["update_available"] is False and notice["latest"] is None
    assert words in (notice["problem"] or "")


def test_an_unknown_repository_is_said_as_such(github: tuple[_GitHub, str]) -> None:
    _, base = github
    notice = check_for_update("v0.4.1", ("acme", "missing"), api_base=base, now=NOW)
    assert "acme/missing" in (notice["problem"] or "") and "not found" in notice["problem"]


def test_github_out_of_reach_is_said_in_words() -> None:
    notice = check_for_update(
        "v0.4.1", ("acme", "ospreyflow"), api_base="http://127.0.0.1:9", now=NOW
    )
    assert "could not reach" in (notice["problem"] or "")


# --- the file the Conduit reads -----------------------------------------------------------------


def test_the_notice_is_written_where_the_conduit_reads_it_and_read_back(tmp_path: Path) -> None:
    notice = {"current": "v0.4.1", "checked_at": NOW, "latest": "v0.5.0",
              "update_available": True, "notes": None, "url": None, "problem": None}  # fmt: skip
    write_notice(tmp_path, notice)
    assert json.loads((tmp_path / "state" / "update.json").read_text()) == notice
    assert read_notice(tmp_path / "state") == notice


def test_no_file_or_a_damaged_one_reads_as_never_checked(tmp_path: Path) -> None:
    assert read_notice(tmp_path / "state") is None
    (tmp_path / "state").mkdir()
    (tmp_path / "state" / "update.json").write_text("{not json")
    assert read_notice(tmp_path / "state") is None
