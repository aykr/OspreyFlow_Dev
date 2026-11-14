"""publish_pages.sh's per-site publishing (item 5, the owner's approval of 14 November 2026): `--site org|net` refuses
in words until the owner has created that site's repository and written its address into `sites/REPOSITORIES`, and an
argument it does not know stops it before anything is done. Each case runs a copy of the script in a folder of its
own, beside a copy of `sites/REPOSITORIES`, so no run can reach a checkout on this machine; every refusal held here
comes before the script's first git command.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

MARKETING = Path(__file__).resolve().parents[1] / "marketing_site"
SCRIPT = MARKETING / "publish_pages.sh"
REPOSITORIES = MARKETING / "sites" / "REPOSITORIES"


def _run(tmp_path: Path, *args: str, repositories: str | None = None) -> subprocess.CompletedProcess[str]:
    here = tmp_path / "dev" / "OspreyFlow_Build" / "marketing_site"
    (here / "sites").mkdir(parents=True)
    shutil.copy(SCRIPT, here / "publish_pages.sh")
    (here / "sites" / "REPOSITORIES").write_text(REPOSITORIES.read_text() if repositories is None else repositories)
    return subprocess.run(["sh", str(here / "publish_pages.sh"), *args], check=False, capture_output=True, text=True, timeout=30)


def test_the_committed_repositories_file_gives_no_address_yet() -> None:
    """The owner writes the two addresses once the repositories exist; until then every line is a comment."""
    lines = [line for line in REPOSITORIES.read_text().splitlines() if line.strip() and not line.startswith("#")]
    assert lines == []


@pytest.mark.parametrize("site", ["org", "net"])
def test_a_site_with_no_repository_written_is_refused_in_words(tmp_path: Path, site: str) -> None:
    run = _run(tmp_path, "--site", site)
    assert run.returncode == 1
    assert run.stderr.strip() == (
        f"STOP: sites/REPOSITORIES gives no repository for {site} yet; the owner creates it and writes it there."
    )


@pytest.mark.parametrize("site", ["org", "net"])
def test_an_address_not_on_github_is_refused(tmp_path: Path, site: str) -> None:
    run = _run(tmp_path, "--site", site, repositories=f"{site} https://example.org/{site}\n")
    assert run.returncode == 1
    assert f"gives no repository for {site} yet" in run.stderr


def test_the_push_can_come_first(tmp_path: Path) -> None:
    run = _run(tmp_path, "--push", "--site", "net")
    assert run.returncode == 1 and "gives no repository for net yet" in run.stderr


@pytest.mark.parametrize("args", [["--site"], ["--site", "com"], ["--site", ""]])
def test_site_takes_org_or_net(tmp_path: Path, args: list[str]) -> None:
    run = _run(tmp_path, *args)
    assert run.returncode == 1
    assert run.stderr.strip() == "STOP: --site takes org or net."


@pytest.mark.parametrize("arg", ["--Push", "push", "org", "--sites"])
def test_an_unknown_argument_stops_before_anything_is_done(tmp_path: Path, arg: str) -> None:
    run = _run(tmp_path, arg)
    assert run.returncode == 1
    assert run.stderr.strip() == f"STOP: unknown argument '{arg}' (--site org|net, --push)."


def test_a_site_is_published_whole_with_its_own_domain() -> None:
    """A generated site goes whole from `sites/<site>/`, with Pages' two files written by the script, never by build.py."""
    text = SCRIPT.read_text()
    assert 'DEPLOY="$HERE/sites/$SITE"' in text
    assert 'cp -R "$DEPLOY/." "$WORK/"' in text
    assert ': > "$WORK/.nojekyll"' in text and 'echo "ospreyflow.$SITE" > "$WORK/CNAME"' in text
    # Its checkout's origin must be the address the owner wrote, in any of git's three spellings of it.
    assert re.search(r'"\$EXPECTED"\|"\$EXPECTED\.git"\|"\$SSH"\) ;;', text)
