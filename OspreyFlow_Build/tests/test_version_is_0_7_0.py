"""The coming release is numbered 0.7.0 (the owner's ruling of 24 November 2026, D227: one release at the end of the
plan, no interim release; rename once, now). Slice RL1b.

What the ruling asks, and what here fails if it is broken:

- `OspreyFlow_Core/VERSION` says `v0.7.0` -> `test_the_version_file_says_v0_7_0`.
- No text still to be read names the old number (guides, the CHANGELOG, a message, a docstring that says what this
  release does) -> `test_no_text_still_to_be_read_names_the_old_number`, which walks every file git tracks in the
  repository and leaves out the records. The records (decision records, the reservations table, the slice line's own
  papers under `OspreyFlow_Build/process/`) say what was written and stay as written, so they are not walked.
- A file that may keep the old number is listed below with its heap (b: a record of what was written, or the name of
  the slice line; c: not this product's version) and the one shape of line that is allowed; an entry that no longer
  matches anything is itself red, so the list cannot go stale -> `test_every_allowance_still_matches_something`.

Planted, at the shape the scan really reads (a tracked path and the file's own text):
`test_the_old_number_added_to_a_guide_is_red`, `test_the_old_number_added_to_the_changelog_is_red`,
`test_the_old_number_added_to_a_record_is_not_red`, `test_a_new_line_in_an_allowed_file_is_red`.

Folders walked (for the scan map): the whole of the repository's tracked files (`git ls-files`), less the records:
`OspreyFlow_Build/process/`, `OspreyFlow_Build/spec/06_DECISIONS.md` and `OspreyFlow_Build/spec/ADR_RESERVATIONS.md`.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
CORE = REPO / "OspreyFlow_Core"

#: The number the ruling retired, written so that this file does not itself contain it.
OLD = "0." + "6." + "2"
OLD_NUMBER = re.compile(r"(?<![\d.])0\.6\.2(?![\d])")

#: Heap (b), the records: never walked (the owner: "records already written stay as they are").
RECORDS = (
    "OspreyFlow_Build/process/",
    "OspreyFlow_Build/spec/06_DECISIONS.md",
    "OspreyFlow_Build/spec/ADR_RESERVATIONS.md",
)

#: Files that may keep the old number: path -> (heap, why, the one shape of line allowed). Heap (a), this product's
#: coming version in text still to be read, has no entry: it is the number that must change.
SLICE_LINE = r"(?i)the v0\.6\.2 slice line"
ALLOWED: dict[str, tuple[str, str, str]] = {
    "OspreyFlow_Core/harness/render.py": ("c", "a third party's image tag", r"speaches:0\.6\.2"),
    "OspreyFlow_Build/tests/harness/test_image_references.py": ("c", "a third party's image tag", r"speaches:0\.6\.2"),
    "OspreyFlow_Core/apps/pages/test/server/forward.test.ts": (
        "c",
        "an arbitrary guide-version header value a test passes through, not the product's version",
        r'"0\.6\.2"',
    ),
    "OspreyFlow_Build/Makefile": ("b", "names the slice line, whose folder is not renamed", SLICE_LINE),
    "OspreyFlow_Build/scripts/publish_user_repo_update.sh": ("b", "names the slice line", SLICE_LINE),
    "OspreyFlow_Build/tests/test_release_owed.py": ("b", "names the slice line", SLICE_LINE),
    "OspreyFlow_Build/tools/release_local.py": ("b", "names the slice line", SLICE_LINE),
    "OspreyFlow_Build/tests/harness/test_refresh_plain_lines.py": (
        "b",
        "quotes the owner's request of 23 November 2026 (D216) as it was written",
        r"v0\.6\.2 only",
    ),
    "OspreyFlow_Core/docs/administration-guide.md": (
        "b",
        "document control's row 2.37, a record of what that revision of the guide said",
        r"^\| 2\.37 \|",
    ),
    ".claude/agents/slice-builder.md": ("b", "names the slice line", SLICE_LINE),
    ".claude/agents/slice-conductor.md": ("b", "names the slice line", SLICE_LINE),
    ".claude/agents/slice-scout.md": ("b", "names the slice line", SLICE_LINE),
    ".claude/agents/slice-verifier.md": ("b", "names the slice line", SLICE_LINE),
}


def tracked() -> list[str]:
    done = subprocess.run(
        ["git", "-C", str(REPO), "ls-files", "-z"], capture_output=True, check=True, text=True, timeout=60
    )
    return [p for p in done.stdout.split("\0") if p]


def scanned(paths: list[str]) -> list[str]:
    """The paths the scan reads: every tracked path but a record."""
    return [p for p in paths if not p.startswith(RECORDS)]


def offenders(files: dict[str, str]) -> list[str]:
    """`path:line` for each line naming the old number in a scanned file, bar the shape its allowance names."""
    found = []
    for path in scanned(list(files)):
        allowance = ALLOWED.get(path)
        for number, line in enumerate(files[path].splitlines(), 1):
            if not OLD_NUMBER.search(line):
                continue
            if allowance is not None and re.search(allowance[2], line):
                continue
            found.append(f"{path}:{number}")
    return found


def read_tracked() -> dict[str, str]:
    files = {}
    for path in scanned(tracked()):
        try:
            files[path] = (REPO / path).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue  # a binary file (a PDF, an image) or one removed in this worktree: not text to be read
    return files


def test_the_version_file_says_v0_7_0() -> None:
    assert (CORE / "VERSION").read_text(encoding="utf-8") == "v0.7.0\n"


def test_no_text_still_to_be_read_names_the_old_number() -> None:
    assert offenders(read_tracked()) == []


def test_the_scan_reads_the_guides_the_changelog_and_the_tests_and_leaves_the_records_out() -> None:
    paths = scanned(tracked())
    for read in (
        "OspreyFlow_Core/docs/administration-guide.md",
        "OspreyFlow_Core/docs/architecture-guide.md",
        "OspreyFlow_Core/CHANGELOG.md",
        "OspreyFlow_Build/spec/10_ADMINISTRATION_GUIDE.md",
        "OspreyFlow_Build/tests/test_intent_in_the_guides.py",
    ):
        assert read in paths, read
    assert [p for p in paths if p.startswith(RECORDS)] == []


def test_every_allowance_still_matches_something() -> None:
    files = read_tracked()
    stale = []
    for path, (heap, why, shape) in ALLOWED.items():
        assert heap in ("b", "c") and why, path
        text = files.get(path, "")
        if not any(OLD_NUMBER.search(line) and re.search(shape, line) for line in text.splitlines()):
            stale.append(path)
    assert stale == [], "drop the allowance for a file that no longer needs it"


@pytest.mark.parametrize(
    "path",
    ["OspreyFlow_Core/docs/administration-guide.md", "OspreyFlow_Core/docs/architecture-guide.md"],
)
def test_the_old_number_added_to_a_guide_is_red(path: str) -> None:
    """The guide's own sentence, as the file holds it, with the old number put back."""
    text = (REPO / path).read_text(encoding="utf-8")
    planted = text + f"\nThe fix is in v{OLD}: a content policy that allows no outside address.\n"
    assert f"{path}:{len(planted.splitlines())}" in offenders({path: planted})


def test_the_old_number_added_to_the_changelog_is_red() -> None:
    path = "OspreyFlow_Core/CHANGELOG.md"
    text = (REPO / path).read_text(encoding="utf-8")
    planted = text.replace("## Unreleased\n", f"## Unreleased\n\n- Planted: new in v{OLD}.\n", 1)
    assert planted != text
    assert f"{path}:{planted.splitlines().index(f'- Planted: new in v{OLD}.') + 1}" in offenders({path: planted})


@pytest.mark.parametrize("path", ["OspreyFlow_Build/spec/06_DECISIONS.md", "OspreyFlow_Build/spec/ADR_RESERVATIONS.md"])
def test_the_old_number_added_to_a_record_is_not_red(path: str) -> None:
    planted = f"### ADR-999 (24 November 2026) — planted, the release was to be v{OLD}\n"
    assert offenders({path: planted}) == []
    assert offenders({"OspreyFlow_Build/process/lanes/v062/slice-line/README.md": f"v{OLD}\n"}) == []


def test_a_new_line_in_an_allowed_file_is_red() -> None:
    """An allowed file keeps one shape of line, not a licence for the old number anywhere in it."""
    path = "OspreyFlow_Core/harness/render.py"
    text = (REPO / path).read_text(encoding="utf-8")
    planted = text + f"\n# This release, v{OLD}, changes the render.\n"
    assert offenders({path: planted}) == [f"{path}:{len(planted.splitlines())}"]
    assert offenders({path: text}) == []
