"""ADR-114 decision 13, Amendment 8 point 7: every release has its changelog section, which becomes
the release's notes (and so the update notice's). `release.yml` runs this check before anything is
built, so a tag with no section is refused before an image exists."""

from __future__ import annotations

from pathlib import Path

import pytest
from scripts.changelog_check import ChangelogRefused, release_notes
from tools.layout import CORE

LOG = """# Changelog

## Unreleased

- Something not yet released.

## v0.2.0 — 2026-11-02

- Find connections, by degrees of separation.
- The scope badge.

## v0.1.0 — 2026-10-20

- The first release.
"""


def test_a_tags_notes_are_its_section_without_its_heading() -> None:
    assert release_notes(LOG, "v0.2.0") == (
        "- Find connections, by degrees of separation.\n- The scope badge."
    )
    assert release_notes(LOG, "v0.1.0") == "- The first release."


@pytest.mark.parametrize(
    ("log", "tag", "words"),
    [
        (LOG, "v0.3.0", "has no section for v0.3.0"),
        (LOG, "0.2.0", "not a version"),
        (LOG.replace("## v0.1.0 — 2026-10-20", "## v0.1.0"), "v0.1.0", "no date"),
        (LOG.replace("## v0.1.0 — 2026-10-20", "## v0.1.0 — 20 Oct"), "v0.1.0", "no date"),
        (LOG.replace("- The first release.\n", ""), "v0.1.0", "says nothing"),
        (LOG + "\n## v0.1.0 — 2026-10-21\n\n- Again.\n", "v0.1.0", "twice"),
    ],
)
def test_a_tag_without_a_proper_section_is_refused_in_words(log: str, tag: str, words: str) -> None:
    with pytest.raises(ChangelogRefused, match=words):
        release_notes(log, tag)


def test_unreleased_work_is_never_a_release() -> None:
    with pytest.raises(ChangelogRefused):
        release_notes(LOG, "Unreleased")


def test_the_check_writes_the_notes_for_the_release_and_exits_non_zero_on_a_refusal(
    tmp_path: Path,
) -> None:
    from scripts import changelog_check

    log = tmp_path / "CHANGELOG.md"
    log.write_text(LOG, encoding="utf-8")
    notes = tmp_path / "notes.md"
    argv = ["--tag", "v0.2.0", "--changelog", str(log), "--notes-out", str(notes)]
    assert changelog_check.main(argv) == 0
    assert notes.read_text(encoding="utf-8").startswith("- Find connections")
    assert changelog_check.main(["--tag", "v9.9.9", "--changelog", str(log)]) == 1


def test_cores_changelog_is_well_formed() -> None:
    """The file the user repository ships: every release section passes the same check."""
    import re

    text = (CORE / "CHANGELOG.md").read_text(encoding="utf-8")
    assert text.startswith("# Changelog\n")
    for tag in re.findall(r"^## (v\d+\.\d+\.\d+)", text, flags=re.M):
        release_notes(text, tag)
