"""`python -m tools.adr_reservations_check --against` (slice BL1b): the reservations file compared
with
its merge-base with `main`, in a temporary git repository (the only folder this file walks is the
system's temporary directory). The text-level cases are in `test_adr_reservations.py`; these prove
the
git half: the base is found, an edit is reported and an append is not, and with no `main` it skips
with
a word instead of passing silently or failing."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
from tools import adr_reservations_check as check

RELATIVE = "OspreyFlow_Build/spec/ADR_RESERVATIONS.md"
BASE = (
    "| Number | Title | Lane | Date | Status |\n| --- | --- | --- | --- | --- |\n"
    "| ADR-142 | Parallel lanes | orchestrator | 2026-11-06 | written |\n"
    "| ADR-110 Amendment 17 | A held number | slice-x | 2026-11-19 | reserved |\n"
)


def _git(cwd: Path, *args: str) -> None:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(
        GIT_CONFIG_GLOBAL=os.devnull,
        GIT_CONFIG_NOSYSTEM="1",
        GIT_AUTHOR_NAME="Test",
        GIT_AUTHOR_EMAIL="test@example.invalid",
        GIT_COMMITTER_NAME="Test",
        GIT_COMMITTER_EMAIL="test@example.invalid",
    )
    subprocess.run(["git", *args], cwd=cwd, env=env, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A repository whose `main` holds the base file, left on a branch `lane` off it."""
    root = tmp_path / "repo"
    path = root / RELATIVE
    path.parent.mkdir(parents=True)
    path.write_text(BASE, encoding="utf-8")
    _git(root, "init", "-q", "-b", "main")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "base")
    _git(root, "checkout", "-q", "-b", "lane")
    monkeypatch.setattr(check, "ROOT", root)
    monkeypatch.setattr(check, "RESERVATIONS_PATH", path)
    # git's own environment would otherwise point at the real repository
    for name in [k for k in os.environ if k.startswith("GIT_")]:
        monkeypatch.delenv(name)
    return root


def _commit(root: Path, text: str) -> None:
    (root / RELATIVE).write_text(text, encoding="utf-8")
    _git(root, "commit", "-q", "-am", "lane")


def test_an_appended_row_and_a_status_flip_pass(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    flipped = BASE.replace("| reserved |", "| written |")
    new_row = "| ADR-110 Amendment 18 | Another | slice-y | 2026-11-20 | reserved |\n"
    _commit(repo, flipped + new_row)
    assert check.against() == 0
    assert "only appended rows and status flips since main" in capsys.readouterr().out


def test_an_edited_title_is_reported_against_the_merge_base(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _commit(repo, BASE.replace("Parallel lanes", "Parallel lanes, reworded"))
    assert check.against() == 1
    out = capsys.readouterr().out
    assert "the row for ADR-142 was edited, not appended to" in out


def test_an_edit_main_made_after_the_branch_point_is_not_this_branchs(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _git(repo, "checkout", "-q", "main")
    (repo / RELATIVE).write_text(BASE.replace("A held number", "A held number, reworded"))
    _git(repo, "commit", "-q", "-am", "main edits a row")
    _git(repo, "checkout", "-q", "lane")
    _commit(repo, BASE + "| ADR-110 Amendment 18 | Another | slice-y | 2026-11-20 | reserved |\n")
    assert check.against() == 0


def test_with_no_main_it_skips_and_says_why(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _git(repo, "branch", "-q", "-m", "main", "trunk")
    _commit(repo, BASE.replace("Parallel lanes", "Parallel lanes, reworded"))
    assert check.against() == 0
    assert "skipped, there is no main to take a merge-base with" in capsys.readouterr().out


def test_with_no_git_directory_it_skips_and_says_why(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / RELATIVE
    path.parent.mkdir(parents=True)
    path.write_text(BASE, encoding="utf-8")
    monkeypatch.setattr(check, "ROOT", tmp_path)
    monkeypatch.setattr(check, "RESERVATIONS_PATH", path)
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path.parent))
    assert check.against() == 0
    assert "skipped, there is no main" in capsys.readouterr().out


# --- the command as `make lanes-check` runs it: main(argv), not the functions it calls -------------


def test_main_with_against_reports_an_edited_row_and_returns_1(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`python -m tools.adr_reservations_check --against` reaches the comparison only through
    main's mode check: a main that fell through to the ordinary check would pass on this tree."""
    _commit(repo, BASE.replace("Parallel lanes", "Parallel lanes, reworded"))
    assert check.main(["adr_reservations_check", "--against"]) == 1
    out = capsys.readouterr().out
    assert "the row for ADR-142 was edited, not appended to" in out
    assert "headings in spec/06_DECISIONS.md with no reservation" not in out


def test_main_with_against_passes_an_appended_row(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _commit(repo, BASE + "| ADR-110 Amendment 18 | Another | slice-y | 2026-11-20 | reserved |\n")
    assert check.main(["adr_reservations_check", "--against"]) == 0
    assert "only appended rows and status flips since main" in capsys.readouterr().out


def test_main_with_against_and_a_ref_compares_with_that_ref(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _git(repo, "branch", "-q", "trunk", "main")
    _git(repo, "branch", "-q", "-m", "main", "elsewhere")
    _commit(repo, BASE.replace("Parallel lanes", "Parallel lanes, reworded"))
    assert check.main(["adr_reservations_check", "--against", "trunk"]) == 1
    assert "the row for ADR-142 was edited" in capsys.readouterr().out


def test_main_reports_a_stale_known_duplicate_and_returns_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The stale-entry check is called from main; as a bare function it proves nothing about the
    command. The real log with its second copy of the known repeat removed is otherwise clean."""
    decisions = check.DECISIONS_PATH.read_text(encoding="utf-8")
    repaired = tmp_path / "06_DECISIONS.md"
    repaired.write_text(
        decisions[: decisions.rindex("### ADR-148, Amendment 10")], encoding="utf-8"
    )
    monkeypatch.setattr(check, "DECISIONS_PATH", repaired)
    assert check.main(["adr_reservations_check"]) == 1
    out = capsys.readouterr().out
    assert "ADR-148 Amendment 10 is in KNOWN_DUPLICATE_HEADINGS but has 1 heading(s)" in out


def test_main_passes_on_the_real_tree(capsys: pytest.CaptureFixture[str]) -> None:
    assert check.main(["adr_reservations_check"]) == 0
    assert "every heading above the baseline is reserved" in capsys.readouterr().out
