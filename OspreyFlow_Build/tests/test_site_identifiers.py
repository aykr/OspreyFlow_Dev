"""publish_pages.sh's personal-identifier rule (marketing_site/identifier_check.py): the Team page's six names in
their own cards and nowhere else. Every planted violation takes the shape build.py emits (rule 15)."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

MARKETING = Path(__file__).resolve().parents[1] / "marketing_site"
sys.path.insert(0, str(MARKETING))
import identifier_check  # noqa: E402

ORG = MARKETING / "sites" / "org"
#: A person card exactly as build.py's `person()` writes it, avatar included.
CARD = '<article class="person"><div class="avatar" aria-hidden="true"></div><div><h3>{}</h3><p class="role">{}</p></div></article>'


SYNTHETIC_CLIENT = "Example Shire Constabulary"


@pytest.fixture(autouse=True)
def hashes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A local hash file of the test's own, holding a synthetic name, in place of the owner's."""
    import client_hashes

    path = tmp_path / "client_names.local.sha256"
    path.write_text(client_hashes.digest(SYNTHETIC_CLIENT) + "\n")
    monkeypatch.setattr(client_hashes, "HASHES", path)
    monkeypatch.setattr(identifier_check.violations, "__defaults__", (path,))
    return path


@pytest.fixture
def site(tmp_path: Path) -> Path:
    copy = tmp_path / "org"
    shutil.copytree(ORG, copy)
    return copy


def _plant(path: Path, before: str, new: str) -> None:
    text = path.read_text()
    assert before in text
    path.write_text(text.replace(before, new + before, 1))


def test_the_site_as_built_passes(site: Path) -> None:
    assert identifier_check.violations(site) == []


def test_the_old_rule_refused_the_team_page() -> None:
    """Why the rule changes: the publish script's grep, as it stood, refuses the owner's own Team page."""
    old = subprocess.run(
        ["grep", "-lI", "-i", "-E", "ayan[[:space:]._-]?(d[._-])?kar|ayankarsolirius", str(ORG / "team.html")],
        capture_output=True, text=True)
    assert old.returncode == 0


def test_a_seventh_person_card_is_refused(site: Path) -> None:
    _plant(site / "team.html", '<article class="person">', CARD.format("Jane Example", "Founding contributor"))
    assert any("person cards" in v for v in identifier_check.violations(site))


def test_a_renamed_card_is_refused(site: Path) -> None:
    team = site / "team.html"
    team.write_text(team.read_text().replace("<h3>Will Forbes</h3>", "<h3>Will Example</h3>"))
    assert any("person cards" in v for v in identifier_check.violations(site))


def test_a_name_twice_on_the_team_page_is_refused(site: Path) -> None:
    _plant(site / "team.html", "</main>", "<p>Ask Graham Burnside.</p>")
    assert any("outside their own card" in v for v in identifier_check.violations(site))


@pytest.mark.parametrize("name", identifier_check.team_names())
def test_each_team_name_on_another_page_is_refused(site: Path, name: str) -> None:
    _plant(site / "governance.html", "</main>", f"<p>{name} decides.</p>")
    assert identifier_check.violations(site) == [
        "governance.html: a personal identifier (people are named on team.html alone)"]


def test_the_owners_address_on_the_team_page_is_refused(site: Path) -> None:
    _plant(site / "team.html", "</main>", "<p>ayan.kar@example.org</p>")
    assert any("outside the person cards" in v for v in identifier_check.violations(site))


def test_a_local_path_is_refused(site: Path) -> None:
    _plant(site / "features.html", "</main>", "<p>/Users/someone/site</p>")
    assert "features.html: a path on this machine" in identifier_check.violations(site)


def test_the_team_page_under_another_name_is_refused(site: Path) -> None:
    (site / "team.html").rename(site / "people.html")
    found = identifier_check.violations(site)
    assert any(v.startswith("people.html: a personal identifier") for v in found)
    assert any(v.startswith("team.html") for v in found) is False


def test_a_clients_name_is_refused_without_printing_it(site: Path) -> None:
    _plant(site / "governance.html", "</main>", f"<p>For the {SYNTHETIC_CLIENT}.</p>")
    found = identifier_check.violations(site)
    assert found == ["governance.html: a client's name (by its hash; the name is not printed)"]
    assert SYNTHETIC_CLIENT.lower() not in " ".join(found).lower()


def test_nothing_is_published_without_the_local_hash_file(site: Path, hashes: Path) -> None:
    hashes.unlink()
    assert any("nothing is published without it" in v for v in identifier_check.violations(site))


def test_the_command_exits_one_on_a_violation(site: Path) -> None:
    _plant(site / "index.html", "</main>", "<p>Laurence Rawlings</p>")
    run = subprocess.run([sys.executable, str(MARKETING / "identifier_check.py"), str(site)], capture_output=True, text=True)
    assert run.returncode == 1 and "index.html" in run.stderr


def test_the_organisations_shared_mailbox_is_not_a_personal_identifier(site: Path) -> None:
    """The owner's decision 2: servicecentre@solirius.com. Planted on a page that names nobody, so only the rule's
    own reading of the address can fail it."""
    _plant(site / "governance.html", "</main>",
           '<p><a href="mailto:servicecentre@solirius.com">servicecentre@solirius.com</a></p>')  # fmt: skip
    assert identifier_check.violations(site) == []


@pytest.mark.parametrize("shape", ["MATTHEW COULDRIDGE", "Will&nbsp;Forbes", "Graham\nBurnside"])
def test_a_team_name_in_another_case_or_spacing_is_refused(site: Path, shape: str) -> None:
    _plant(site / "features.html", "</main>", f"<p>{shape}</p>")
    assert identifier_check.violations(site) == [
        "features.html: a personal identifier (people are named on team.html alone)"]
