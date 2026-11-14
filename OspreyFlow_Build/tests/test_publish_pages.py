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


# ---------------------------------------------------------------- through a checkout, after the lane review


ADDRESS = "https://github.com/example/ospreyflow-site-org"
SYNTHETIC_CLIENT = "Example Shire Constabulary"


def _layout(tmp_path: Path, repositories: str = f"org {ADDRESS}\n", push: str | None = None) -> Path:
    """The script's own folder as it sits in the repository, with ospreyflow.org, a hash file holding a synthetic
    name, and the site's checkout beside the repository (`OspreyFlow_site_org`) whose origin is `ADDRESS`."""
    import sys

    sys.path.insert(0, str(MARKETING))
    import client_hashes

    here = tmp_path / "dev" / "OspreyFlow_Build" / "marketing_site"
    (here / "sites").mkdir(parents=True)
    for name in ("publish_pages.sh", "identifier_check.py", "client_hashes.py", "TEAM_NAMES"):
        shutil.copy(MARKETING / name, here / name)
    shutil.copytree(MARKETING / "sites" / "org", here / "sites" / "org")
    (here / "sites" / "REPOSITORIES").write_text(repositories)
    (here / "client_names.local.sha256").write_text(client_hashes.digest(SYNTHETIC_CLIENT) + "\n")
    checkout = tmp_path / "OspreyFlow_site_org"
    subprocess.run(["git", "init", "-q", str(checkout)], check=True)
    subprocess.run(["git", "-C", str(checkout), "remote", "add", "origin", ADDRESS], check=True)
    if push is not None:
        subprocess.run(["git", "-C", str(checkout), "remote", "set-url", "--push", "origin", push], check=True)
    return here


def _publish(here: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """The script run with git allowed the local file protocol alone: the first fetch from GitHub fails at once, so
    no run reaches the network, and a run that gets that far has passed every check before it."""
    env = {**__import__("os").environ, "GIT_ALLOW_PROTOCOL": "file"}
    return subprocess.run(["sh", str(here / "publish_pages.sh"), *args], check=False, capture_output=True, text=True,
                          timeout=60, env=env)  # fmt: skip


def test_a_clean_site_passes_every_check_and_stops_only_at_the_fetch(tmp_path: Path) -> None:
    run = _publish(_layout(tmp_path), "--site", "org")
    assert run.returncode != 0 and "STOP" not in run.stderr
    assert "transport 'https' not allowed" in run.stderr


@pytest.mark.parametrize(
    ("plant", "why"),
    [("<p>Will Forbes</p>", "a personal identifier"), (f"<p>{SYNTHETIC_CLIENT}</p>", "a client's name"),
     ("<p>/Users/someone/site</p>", "a path on this machine")],
)  # fmt: skip
def test_the_identifier_check_stops_a_site_before_anything_is_fetched(tmp_path: Path, plant: str, why: str) -> None:
    here = _layout(tmp_path)
    page = here / "sites" / "org" / "features.html"
    page.write_text(page.read_text().replace("</main>", plant + "</main>", 1))
    run = _publish(here, "--site", "org")
    assert run.returncode == 1 and f"features.html: {why}" in run.stderr
    assert run.stderr.rstrip().endswith("STOP: the files above carry a personal identifier or a local path.")
    assert "transport" not in run.stderr


def test_nothing_is_published_without_the_hash_file(tmp_path: Path) -> None:
    here = _layout(tmp_path)
    (here / "client_names.local.sha256").unlink()
    run = _publish(here, "--site", "org")
    assert run.returncode == 1 and "client_names.local.sha256 is absent" in run.stderr


def test_a_push_address_other_than_the_sites_is_refused(tmp_path: Path) -> None:
    run = _publish(_layout(tmp_path, push="https://github.com/Solirius/ospreyflow.git"), "--site", "org")
    assert run.returncode == 1
    assert "origin pushes to 'https://github.com/Solirius/ospreyflow.git', not " + ADDRESS + ".git." in run.stderr


@pytest.mark.parametrize(
    "address", ["https://github.com/aykr/OspreyFlow", "https://github.com/AYKR/ospreyflow.git", "https://github.com/solirius/OspreyFlow"]
)
def test_the_products_own_repository_is_never_a_sites(tmp_path: Path, address: str) -> None:
    run = _run(tmp_path, "--site", "org", repositories=f"org {address}\n")
    assert run.returncode == 1 and "which is the product's repository, not a site's own" in run.stderr


def test_one_repository_for_both_sites_is_refused(tmp_path: Path) -> None:
    run = _run(tmp_path, "--site", "net", repositories=f"org {ADDRESS}\nnet https://github.com/EXAMPLE/OspreyFlow-Site-Org.git\n")
    assert run.returncode == 1 and "for both org and net; each site has its own" in run.stderr
