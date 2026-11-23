"""Slice BL1c: the citation check leaves the slice line's own working papers alone, by folder, and
says how many files it left.

The owner's ruling 1 of 21 November 2026: `tools/doc_citations_check.py` scanned every `.md` under
`process/`, so a brief or table of the conductor's that cited a file not yet written (or mistyped)
turned `main` red and stopped whichever slice picked it up: four stops in two days, none a fault in
the product. The skip is **by path, in code** (`tools/doc_citations_check.py`'s `LANE_PAPERS_*`
constants), not by an entry in `tests/fixtures/citation_allowlist.txt`.

**Folders this file walks** (for the scan row): none of the real repository's folders is walked
from here by name. Every case builds a throwaway tree under `tmp_path` with the real folder names
(`process/lanes/v062/...`, `spec/`, `apps/`, `scripts/`), which is the shape the check really sees;
two cases read the real tree through the check's own scan (`scanned_files`, `skipped_files`) and
one runs the check as the Makefile does (`python -m tools.doc_citations_check`, from the product
folder with the Build folder on `PYTHONPATH`).

`CLAUDE.md` rule 15: the planted violation has the shape the real ones take (a backticked
repository path with a source extension, in a Markdown document, naming a file that is not
there), and each skipped case is paired with the same citation in a place that is still checked,
so a skip that swallows everything cannot pass.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from tools import doc_citations_check as check
from tools.layout import BUILD, CORE

#: A citation of a file that is not there, in the shape every real instance took.
BROKEN = "See `tests/never_written/test_missing.py` for the case.\n"
CITED = "tests/never_written/test_missing.py"

LANE = "process/lanes/v062"

#: One planted working paper under each folder the owner's ruling names, and the files directly in
#: `process/lanes/v062/` (item 5 of the brief). Each is a Markdown file, the suffix the papers use.
SKIPPED_PAPERS = (
    f"{LANE}/slices/BL1c.md",
    f"{LANE}/slices/BL1c_OUT/notes/deep/report.md",
    f"{LANE}/backlog/N16_N22.md",
    f"{LANE}/slice-line/proposals/LINE_FIXES_BRIEF.md",
    f"{LANE}/slice-line/diffs/APPLIED_2026-11-20.md",
    f"{LANE}/RULINGS.md",
    f"{LANE}/MORNING_HOLD_2026-11-21.md",
)

#: Places that are still checked, each with the same broken citation.
STILL_CHECKED = (
    "spec/06_DECISIONS.md",
    "apps/workspace/README.md",
    "tools/x.md",
    "scripts/slice_line/README.md",
    f"{LANE}/slice-line/README.md",
    f"{LANE}/slice-line/LINE_FAULTS_2026-11-18.md",
    f"{LANE}/other/x.md",
    f"{LANE}/slices_extra/x.md",
    f"{LANE}/sub/slices/x.md",
    "process/lanes/v061/slices/x.md",
    "process/lanes/CARRIES.md",
    "process/07_BUILD_PLAN.md",
)


def _tree(root: Path, files: dict[str, str]) -> Path:
    for name, body in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    return root


@pytest.mark.parametrize("paper", SKIPPED_PAPERS)
def test_a_broken_citation_in_a_working_paper_passes(tmp_path: Path, paper: str) -> None:
    """Red on main: every one of these was flagged."""
    root = _tree(tmp_path, {paper: BROKEN})

    assert check.find_broken(root) == []


@pytest.mark.parametrize("place", STILL_CHECKED)
def test_the_same_broken_citation_elsewhere_still_fails(tmp_path: Path, place: str) -> None:
    """The pair of the case above: the identical text, one folder over, is still caught. This is
    the case that goes red if the skip is widened to all of `process/`, to `lanes/`, or to any
    sub-folder the owner's ruling did not name, and it checks the folder is matched by whole path
    parts (`slices_extra/` is not `slices/`)."""
    root = _tree(tmp_path, {place: BROKEN})

    broken = check.find_broken(root)

    assert len(broken) == 1, broken
    assert place in broken[0]
    assert CITED in broken[0]


def test_a_working_paper_and_a_specification_in_one_tree_only_the_specification_fails(
    tmp_path: Path,
) -> None:
    root = _tree(
        tmp_path,
        {f"{LANE}/slices/BL1c.md": BROKEN, "spec/00_ARCHITECTURE.md": BROKEN},
    )

    broken = check.find_broken(root)

    assert len(broken) == 1, broken
    assert broken[0].startswith("spec/00_ARCHITECTURE.md:1")


def test_the_repository_gate_is_clean_on_a_tree_where_a_working_paper_cites_a_missing_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """What the owner asked for: `main()` passes (exit 0) on a tree whose only fault is a working
    paper citing a file that is not there, the way `test_the_repository_itself_is_clean` would see
    the real tree after a conductor's brief cites a file not yet written."""
    root = _tree(
        tmp_path,
        {
            f"{LANE}/slices/BL1d.md": BROKEN,
            "spec/00_ARCHITECTURE.md": "No citations here.\n",
        },
    )

    assert check.find_broken(root) == []
    assert check.main(root) == 0
    assert capsys.readouterr().out.strip().splitlines()[-1].startswith("citation-check: skipped 1 ")


def test_a_file_with_a_scanned_suffix_is_counted_and_one_without_is_not(tmp_path: Path) -> None:
    """The count is the number of files the skip took out of the scan, so a `.diff` or `.sh` (never
    scanned) is not in it, and a `.py` (scanned) is."""
    root = _tree(
        tmp_path,
        {
            f"{LANE}/slices/a.md": "x\n",
            f"{LANE}/slices/b.py": "x = 1\n",
            f"{LANE}/slice-line/diffs/helper.sh": "true\n",
            f"{LANE}/slice-line/proposals/p.diff": "+x\n",
            f"{LANE}/slice-line/proposals/p.md": "x\n",
            f"{LANE}/RULINGS.md": "x\n",
            "spec/kept.md": "x\n",
        },
    )

    skipped = check.skipped_files(root)

    assert sorted(p.relative_to(root).as_posix() for p in skipped) == [
        f"{LANE}/RULINGS.md",
        f"{LANE}/slice-line/proposals/p.md",
        f"{LANE}/slices/a.md",
        f"{LANE}/slices/b.py",
    ]
    assert [p.relative_to(root).as_posix() for p in check.scanned_files(root)] == ["spec/kept.md"]


def test_the_last_line_of_output_says_how_many_files_were_skipped_on_success(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _tree(tmp_path, {path: "Nothing cited.\n" for path in SKIPPED_PAPERS})

    assert check.main(root) == 0

    last = capsys.readouterr().out.strip().splitlines()[-1]
    assert last == (
        f"citation-check: skipped {len(SKIPPED_PAPERS)} files "
        "(the slice line's working papers under process/lanes/v062/)"
    )


def test_the_last_line_of_output_says_how_many_files_were_skipped_on_failure(
    tmp_path: Path, capfd: pytest.CaptureFixture[str]
) -> None:
    """On failure too, and still last: after the list of broken citations, not before it."""
    root = _tree(
        tmp_path,
        {
            **{path: BROKEN for path in SKIPPED_PAPERS},
            "spec/00_ARCHITECTURE.md": BROKEN,
        },
    )

    assert check.main(root) == 1

    captured = capfd.readouterr()
    assert captured.out.strip().splitlines()[-1] == (
        f"citation-check: skipped {len(SKIPPED_PAPERS)} files "
        "(the slice line's working papers under process/lanes/v062/)"
    )
    assert "spec/00_ARCHITECTURE.md:1" in captured.err


def test_the_count_is_counted_not_written_in(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Two trees with different numbers of papers print different numbers."""
    one = _tree(tmp_path / "one", {f"{LANE}/slices/a.md": "x\n"})
    three = _tree(
        tmp_path / "three",
        {f"{LANE}/slices/a.md": "x\n", f"{LANE}/backlog/b.md": "x\n", f"{LANE}/c.md": "x\n"},
    )

    check.main(one)
    first = capsys.readouterr().out.strip().splitlines()[-1]
    check.main(three)
    second = capsys.readouterr().out.strip().splitlines()[-1]

    assert first.startswith("citation-check: skipped 1 files")
    assert second.startswith("citation-check: skipped 3 files")


def test_the_skip_is_by_path_in_code_not_by_allowlist_entries() -> None:
    """The allowlist is as it was: no entry under the working papers' folders, and the skipped
    folders are named in the check's own constants."""
    entries = check.load_allowlist()

    assert not [e for e in entries if e.startswith("process/lanes/v062/")], entries
    assert check.LANE_PAPERS_ROOT == "process/lanes/v062"
    assert set(check.LANE_PAPERS_FOLDERS) == {
        "slices",
        "backlog",
        "slice-line/proposals",
        "slice-line/diffs",
    }


def test_on_the_real_tree_the_skip_covers_only_the_named_folders() -> None:
    """The real shape. Every file the skip takes is under one of the four folders or directly in
    `process/lanes/v062/`; the slice line's README and the other `process/` folders are scanned."""
    skipped = {check.rel(p, check.REPO_ROOT) for p in check.skipped_files()}
    scanned = {check.rel(p, check.REPO_ROOT) for p in check.scanned_files()}

    assert skipped, "the real tree has working papers; a skip that takes none is not wired"
    for name in skipped:
        rest = name.removeprefix(f"{LANE}/")
        assert name.startswith(f"{LANE}/"), name
        assert "/" not in rest or rest.split("/", 1)[0] in {"slices", "backlog"} or rest.startswith(
            ("slice-line/proposals/", "slice-line/diffs/")
        ), name
    assert f"{LANE}/slice-line/README.md" in scanned
    assert "process/07_BUILD_PLAN.md" in scanned
    assert not skipped & scanned


def test_the_make_target_prints_the_skipped_count_as_its_last_line_on_the_real_tree() -> None:
    """The gate as `make citation-check` runs it, from the product folder with the Build folder on
    `PYTHONPATH`. The count it prints is the count of the real skip."""
    result = subprocess.run(
        [sys.executable, "-m", "tools.doc_citations_check"],
        cwd=CORE,
        env={**os.environ, "PYTHONPATH": str(BUILD)},
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip().splitlines()[-1] == (
        f"citation-check: skipped {len(check.skipped_files())} files "
        "(the slice line's working papers under process/lanes/v062/)"
    )
