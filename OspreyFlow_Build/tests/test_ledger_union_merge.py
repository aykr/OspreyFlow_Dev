"""Slice BL1b: two appended rows no longer bounce a merge (the owner's order of 20 November 2026).

`ADR_RESERVATIONS.md` takes git's union merge (`.gitattributes` at the repository root), so two
branches
that each append a reservation row merge cleanly, in either order, and keep both rows. The decision
log
(`06_DECISIONS.md`) is **not** on the list: it has content edited in place, which a union merge
would
double, so two appended amendment blocks still conflict there until the owner says otherwise.

Everything here runs git in a temporary directory only, never in the real repository: the folder
this
file walks is the system's temporary directory (one repository per case), plus a read of the real
`.gitattributes` and nothing else.

Rule 15: each plant takes the shape the tools really receive: a row appended to the end of the real
file's layout (after its baseline table), a real amendment block, and the two files merged by git
itself.
The attributes come from the tree being merged, so `.gitattributes` is committed on the base before
the
branches part.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest
from tools.adr_reservations_check import find_ledger_edits, find_unreserved
from tools.layout import ROOT

LEDGER = "OspreyFlow_Build/spec/ADR_RESERVATIONS.md"
LOG = "OspreyFlow_Build/spec/06_DECISIONS.md"

BASE_LEDGER = """\
# ADR and amendment reservations

## Reservations

Status is `reserved` or `written`.

| Number | Title | Lane | Date | Status |
| --- | --- | --- | --- | --- |
| ADR-142 | Parallel lanes | orchestrator | 2026-11-06 | written |
| ADR-110 Amendment 14 | The Admin area becomes a place | orchestrator | 2026-11-06 | written |
| ADR-110 Amendment 17 | A held number | slice-x | 2026-11-19 | reserved |

## Baseline

Nothing at or below these numbers needs a row. This section is never edited.

Last ADR at the baseline: ADR-141
Amendment headings in another form at the baseline: 0

| ADR | Last amendment at the baseline |
| --- | --- |
| ADR-110 | 13 |
| ADR-114 | 36 |
| ADR-146 Amendment 6 | The rule editor as built | case | 2026-11-12 | written |
"""

LAST_HELD = "| ADR-110 Amendment 18 | The last held row | slice-y | 2026-11-20 | reserved |\n"

BASE_LOG = """\
## ADR-110 — The Admin area — ACCEPTED

Some text.

### ADR-110, Amendment 14 (6 November 2026) — The Admin area becomes a place

Status: accepted.

## ADR-142 — Parallel lanes — ACCEPTED

More text.
"""


def _row(n: int, title: str, lane: str = "slice-a", status: str = "written") -> str:
    return f"| ADR-110 Amendment {n} | {title} | {lane} | 2026-11-20 | {status} |\n"


def _block(n: int, title: str) -> str:
    return (
        f"\n### ADR-110, Amendment {n} (20 November 2026) — {title}\n\n"
        "Status: accepted from a planted ruling.\n"
    )


def _git(cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(
        GIT_CONFIG_GLOBAL=os.devnull,
        GIT_CONFIG_NOSYSTEM="1",
        GIT_AUTHOR_NAME="Test",
        GIT_AUTHOR_EMAIL="test@example.invalid",
        GIT_COMMITTER_NAME="Test",
        GIT_COMMITTER_EMAIL="test@example.invalid",
    )
    return subprocess.run(
        ["git", *args], cwd=cwd, env=env, text=True, capture_output=True, check=check
    )


def _real_attributes() -> str:
    path = ROOT / ".gitattributes"
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _write(repo: Path, rel: str, text: str) -> None:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _read(repo: Path, rel: str) -> str:
    return (repo / rel).read_text(encoding="utf-8")


def _new_repo(tmp_path: Path, attributes: str, ledger: str = BASE_LEDGER) -> Path:
    """A base commit on `main` holding the attributes (if any) and small copies of the two files."""
    repo = tmp_path / "repo"
    repo.mkdir(parents=True)
    _git(repo, "init", "-q", "-b", "main")
    if attributes:
        _write(repo, ".gitattributes", attributes)
    _write(repo, LEDGER, ledger)
    _write(repo, LOG, BASE_LOG)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "base")
    return repo


def _branch(
    repo: Path,
    name: str,
    *,
    ledger: Callable[[str], str] = lambda t: t,
    log: Callable[[str], str] = lambda t: t,
) -> None:
    """A branch off `main` that edits the two files, committed; the repository ends on `main`."""
    _git(repo, "checkout", "-q", "-b", name, "main")
    _write(repo, LEDGER, ledger(_read(repo, LEDGER)))
    _write(repo, LOG, log(_read(repo, LOG)))
    _git(repo, "commit", "-q", "-am", name)
    _git(repo, "checkout", "-q", "main")


def _merge(repo: Path, branch: str) -> tuple[bool, list[str]]:
    """Merge on the current branch; whether it was clean and which files conflicted."""
    done = _git(repo, "merge", "--no-ff", "--no-edit", branch, check=False)
    conflicted = _git(repo, "diff", "--name-only", "--diff-filter=U").stdout.split()
    return done.returncode == 0, conflicted


def _appends(n: int, title: str, *, block: bool) -> dict[str, Callable[[str], str]]:
    return {
        "ledger": lambda t: t + _row(n, title),
        "log": (lambda t: t + _block(n, title)) if block else (lambda t: t),
    }


# --- the attributes themselves ------------------------------------------------


def test_the_root_gitattributes_lists_the_reservations_table_alone() -> None:
    text = _real_attributes()
    entries = [
        line.split() for line in text.splitlines() if line.strip() and not line.startswith("#")
    ]
    assert entries == [[LEDGER, "merge=union"]]
    comment = " ".join(line for line in text.splitlines() if line.startswith("#"))
    assert "06_DECISIONS.md" in comment, "the comment must say why the decision log is not listed"


# --- two appended rows ----------------------------------------------------------


@pytest.mark.parametrize("order", [("a", "b"), ("b", "a")])
def test_two_appended_reservation_rows_merge_clean_in_either_order(
    tmp_path: Path, order: tuple[str, str]
) -> None:
    repo = _new_repo(tmp_path, _real_attributes())
    _branch(repo, "a", **_appends(15, "First appended", block=True))
    _branch(repo, "b", **_appends(16, "Second appended", block=False))

    for branch in order:
        clean, conflicted = _merge(repo, branch)
        assert clean, f"merging {branch} conflicted in {conflicted}"

    ledger, log = _read(repo, LEDGER), _read(repo, LOG)
    assert _row(15, "First appended") in ledger and _row(16, "Second appended") in ledger
    assert "### ADR-110, Amendment 15 " in log
    assert find_unreserved(log, ledger) == []


def test_two_appended_amendment_blocks_still_conflict_in_the_decision_log(tmp_path: Path) -> None:
    """The limit, pinned: the log is not on the list, so only the log bounces (the reservations
    merge)."""
    repo = _new_repo(tmp_path, _real_attributes())
    _branch(repo, "a", **_appends(15, "First appended", block=True))
    _branch(repo, "b", **_appends(16, "Second appended", block=True))

    assert _merge(repo, "a") == (True, [])
    clean, conflicted = _merge(repo, "b")
    assert (clean, conflicted) == (False, [LOG])


@pytest.mark.parametrize("order", [("a", "b"), ("b", "a")])
def test_with_the_log_listed_too_two_rows_and_two_blocks_merge_clean(
    tmp_path: Path, order: tuple[str, str]
) -> None:
    """What the owner would get by adding the log to the list (not built: the owner's word
    first)."""
    repo = _new_repo(tmp_path, _real_attributes() + f"{LOG} merge=union\n")
    _branch(repo, "a", **_appends(15, "First appended", block=True))
    _branch(repo, "b", **_appends(16, "Second appended", block=True))

    for branch in order:
        clean, conflicted = _merge(repo, branch)
        assert clean, f"merging {branch} conflicted in {conflicted}"

    ledger, log = _read(repo, LEDGER), _read(repo, LOG)
    assert _row(15, "First appended") in ledger and _row(16, "Second appended") in ledger
    assert "### ADR-110, Amendment 15 " in log and "### ADR-110, Amendment 16 " in log
    assert find_unreserved(log, ledger) == []


# --- what union lets through, and the checks that catch it ------------------------


def test_the_same_number_in_both_branches_merges_clean_and_the_reservation_check_is_red(
    tmp_path: Path,
) -> None:
    repo = _new_repo(tmp_path, _real_attributes())
    _branch(repo, "a", **_appends(15, "Reserved by the first", block=True))
    _branch(repo, "b", **_appends(15, "Reserved by the second", block=False))

    assert _merge(repo, "a") == (True, [])
    assert _merge(repo, "b") == (True, [])

    problems = find_unreserved(_read(repo, LOG), _read(repo, LEDGER))
    assert "ADR-110 Amendment 15 is reserved 2 times" in problems


def test_a_status_flip_edited_two_ways_leaves_a_doubled_row_that_the_check_reports(
    tmp_path: Path,
) -> None:
    """Both flip the held row to written; one also changes its title: union keeps both versions."""
    held = "| ADR-110 Amendment 17 | A held number | slice-x | 2026-11-19 | reserved |\n"
    repo = _new_repo(tmp_path, _real_attributes())
    _branch(repo, "a", ledger=lambda t: t.replace(held, _row(17, "A held number", "slice-x")))
    _branch(
        repo, "b", ledger=lambda t: t.replace(held, _row(17, "A held number, reworded", "slice-x"))
    )

    assert _merge(repo, "a") == (True, [])
    assert _merge(repo, "b") == (True, [])

    ledger = _read(repo, LEDGER)
    assert ledger.count("| ADR-110 Amendment 17 |") == 2
    assert "ADR-110 Amendment 17 is reserved 2 times" in find_unreserved(BASE_LOG, ledger)


_FLIPPED = LAST_HELD.replace("reserved", "written")


def _held_last_in_table() -> str:
    """BASE_LEDGER with the held row as the last row of the Reservations table (above Baseline)."""
    return BASE_LEDGER.replace("\n## Baseline", LAST_HELD + "\n## Baseline", 1)


@pytest.mark.parametrize("order", [("flip", "append"), ("append", "flip")])
@pytest.mark.parametrize("where", ["end of the file", "end of the table"])
def test_a_flip_of_the_last_row_with_a_row_appended_straight_after_it_leaves_the_number_twice(
    tmp_path: Path, order: tuple[str, str], where: str
) -> None:
    """The commonest shape, measured with a real `git merge` (not reasoned from git's merge rules):
    the orchestrator reserves a row, the slice flips it to `written`, another slice appends the
    next row straight after it. The two changes touch adjacent lines, so git does not combine them;
    the union driver settles it without markers by keeping both sides, and the result is the row
    twice (once `reserved`, once `written`) beside the new row. The merge is clean and **not**
    right: the number is held twice, which is what the checks report (the merge is bounced by
    them, not silently wrong). Which of the two comes first depends on the order of the merges."""
    base = BASE_LEDGER + LAST_HELD if where == "end of the file" else _held_last_in_table()
    repo = _new_repo(tmp_path, _real_attributes(), base)
    _branch(repo, "flip", ledger=lambda t: t.replace(LAST_HELD, _FLIPPED))
    new_row = _row(19, "Appended straight after it")
    if where == "end of the file":
        _branch(repo, "append", ledger=lambda t: t + new_row)
    else:
        _branch(repo, "append", ledger=lambda t: t.replace(LAST_HELD, LAST_HELD + new_row))

    for branch in order:
        assert _merge(repo, branch) == (True, [])

    merged = _read(repo, LEDGER)
    assert merged.count("| ADR-110 Amendment 18 |") == 2, "union kept both sides of the row"
    assert LAST_HELD in merged and _FLIPPED in merged and new_row in merged
    # The existing duplicate check reports it ...
    assert "ADR-110 Amendment 18 is reserved 2 times" in find_unreserved(BASE_LOG, merged)
    # ... and so does the comparison with the base (a second row for a number the base holds).
    problems = find_ledger_edits(base, merged)
    assert any(
        "ADR-110 Amendment 18" in p and "duplicates a row of the base" in p for p in problems
    )


def test_an_edit_to_an_existing_row_merges_clean_and_the_edit_check_is_red(tmp_path: Path) -> None:
    edited = "| ADR-110 Amendment 14 | The Admin area becomes a place of its own | orchestrator |"
    repo = _new_repo(tmp_path, _real_attributes())
    base = _read(repo, LEDGER)
    _branch(
        repo,
        "a",
        ledger=lambda t: t.replace(
            "| ADR-110 Amendment 14 | The Admin area becomes a place | orchestrator |", edited
        ),
    )
    # The second branch adds its row at the end of the Reservations table, above `## Baseline`.
    new_row = _row(16, "Second appended")
    _branch(repo, "b", ledger=lambda t: t.replace("\n## Baseline", new_row + "\n## Baseline", 1))

    assert _merge(repo, "a") == (True, [])
    assert _merge(repo, "b") == (True, [])

    merged = _read(repo, LEDGER)
    assert edited in merged and _row(16, "Second appended") in merged
    assert find_unreserved(BASE_LOG, merged) == [], "the reservation check alone cannot see it"
    [problem] = find_ledger_edits(base, merged)
    assert "ADR-110 Amendment 14" in problem


# --- measured (reported to the owner) -----------------------------------------------


def test_merge_tree_write_tree_honours_the_union_attribute(tmp_path: Path) -> None:
    """What `merge_slice.py`'s description of a failed merge uses: with the attribute on the base
    the
    merge-tree is clean; with none, the same two branches conflict (the control)."""
    for attributes, clean in ((_real_attributes(), True), ("", False)):
        repo = _new_repo(tmp_path / ("with" if attributes else "without"), attributes)
        _branch(repo, "a", **_appends(15, "First appended", block=False))
        _branch(repo, "b", **_appends(16, "Second appended", block=False))
        done = _git(repo, "merge-tree", "--write-tree", "a", "b", check=False)
        assert (done.returncode == 0) is clean, done.stdout


def test_a_builders_first_merge_of_main_bounces_once_and_not_again(tmp_path: Path) -> None:
    """The commit that brings `.gitattributes` to a branch, met by the builder's plain `git merge
    main`.

    The attributes are read from the tree being merged into, which does not hold the file yet, so
    that
    one merge bounces; resolved once, the next merge of main (the file now in the builder's tree) is
    clean. The orchestrator's direction is not affected: it merges in a checkout of main, and
    `merge-tree`
    run there sees the file whichever side it names first (run in the builder's checkout it does
    not).
    """
    repo = _new_repo(tmp_path, "")
    _branch(repo, "builder", **_appends(15, "The builder's row", block=False))
    _write(repo, ".gitattributes", _real_attributes())
    _write(repo, LEDGER, _read(repo, LEDGER) + _row(16, "Main's row"))
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "main gains the attributes and a row")

    for first, second in (("main", "builder"), ("builder", "main")):
        assert _git(repo, "merge-tree", "--write-tree", first, second, check=False).returncode == 0

    _git(repo, "checkout", "-q", "builder")
    # `merge-tree` reads the attributes from the checkout it is run in, not from the trees it names.
    assert _git(repo, "merge-tree", "--write-tree", "main", "builder", check=False).returncode == 1
    assert _merge(repo, "main") == (False, [LEDGER])
    resolved = _read(repo, LEDGER)
    for row in (_row(15, "The builder's row"), _row(16, "Main's row")):
        assert row in resolved
    _write(
        repo,
        LEDGER,
        "".join(
            line
            for line in resolved.splitlines(keepends=True)
            if not line.startswith(("<<<<<<<", "=======", ">>>>>>>"))
        ),
    )
    _git(repo, "add", LEDGER)
    _git(repo, "commit", "-q", "--no-edit")

    _git(repo, "checkout", "-q", "main")
    _write(repo, LEDGER, _read(repo, LEDGER) + _row(17, "Main's next row"))
    _git(repo, "commit", "-q", "-am", "main appends again")
    _git(repo, "checkout", "-q", "builder")
    _write(repo, LEDGER, _read(repo, LEDGER) + _row(18, "The builder's next row"))
    _git(repo, "commit", "-q", "-am", "builder appends again")
    assert _merge(repo, "main") == (True, [])
