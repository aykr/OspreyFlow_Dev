"""ADR-110 decision 5 and Amendment 4: which files a folder watch takes, against a real folder.

The executor's side — once per file, across replicas, as the owner — is
`test_schedule_executor.py`'s; this is what counts as a waiting file and what a watch may be.
"""

from __future__ import annotations

import os
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from conduit_common.identity import new_id
from schemas.ingest import StudioRecipeDraft, StudioRecipeStatus
from services.api.folder_watch import describe_watch, validate_watch, waiting_files
from services.api.scheduler import ScheduleRefused

NOW = datetime(2026, 6, 2, 12, tzinfo=UTC)
SET_AT = NOW - timedelta(hours=1)


def _recipe(**overrides: Any) -> StudioRecipeDraft:
    fields: dict[str, Any] = {
        "recipe_id": new_id(),
        "version": 1,
        "status": StudioRecipeStatus.PUBLISHED,
        "label": "Carrier B daily",
        "handling": {"classification": "OFFICIAL", "handling_code": "P",
                     "owning_unit": "unit-1", "originator": "unit-1"},
        "owning_unit": "unit-1",
        "created_by": "author-1",
        "created_at": SET_AT,
        "ready_for_profile": True,
        "dataset_id": "carrier-b",
        "schedule_watch": "*.csv",
        "schedule_owner": "approver-1",
        "schedule_set_at": SET_AT,
        "schedule_case": "case-1",
    }  # fmt: skip
    fields.update(overrides)
    return StudioRecipeDraft(**fields)


def _put(
    folder: Path, name: str, data: bytes = b"a,b\n1,2\n", *, at: datetime | None = None
) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    path.write_bytes(data)
    if at is not None:
        os.utime(path, (at.timestamp(), at.timestamp()))
    return path


def _names(recipe: StudioRecipeDraft, root: Path, now: datetime) -> list[str]:
    return [f.name for f in waiting_files(recipe, root=root, now=now)]


def _real_now() -> datetime:
    """The status-change time cannot be set, so cases that rely on it run on the real clock."""
    return datetime.now(UTC)


# --- what a watch may be ---------------------------------------------------------------------


@pytest.mark.parametrize("pattern", ["*.csv", "carrier-b-*.xlsx", "export_??.json", "[ab]*.csv"])
def test_a_plain_filename_pattern_is_accepted(pattern: str) -> None:
    validate_watch(pattern, _recipe())


@pytest.mark.parametrize(
    ("pattern", "words"),
    [
        ("", "a filename pattern"),
        ("   ", "a filename pattern"),
        ("in/*.csv", "no folder"),
        ("..\\*.csv", "no folder"),
        (".*", "hidden"),
        ("a\tb.csv", "control"),
        ("x" * 201, "200 characters"),
        ("s3://ingest/*.csv", "no folder"),
    ],
)
def test_a_watch_it_could_not_keep_is_refused_in_words(pattern: str, words: str) -> None:
    with pytest.raises(ScheduleRefused, match=words):
        validate_watch(pattern, _recipe())


def test_a_recipe_in_no_dataset_cannot_be_watched() -> None:
    with pytest.raises(ScheduleRefused, match="belongs to no dataset"):
        validate_watch("*.csv", _recipe(dataset_id=None))


def test_the_watch_in_words_names_the_folder_and_the_pattern() -> None:
    assert describe_watch("*.csv", "carrier-b") == (
        "when a file matching `*.csv` arrives in the carrier-b folder"
    )


# --- which files are waiting -----------------------------------------------------------------


def test_a_settled_new_matching_file_in_the_datasets_folder_is_waiting(tmp_path: Path) -> None:
    arrived = NOW - timedelta(minutes=5)
    # Written in this order so the status-change times agree with the modification times.
    _put(tmp_path / "uploaded" / "carrier-b", "upload.csv", at=arrived - timedelta(minutes=1))
    _put(tmp_path / "carrier-b", "2026-06-02.csv", at=arrived)
    _put(tmp_path / "carrier-b", "notes.txt", at=arrived)  # does not match
    (found_upload, found) = waiting_files(_recipe(), root=tmp_path, now=_far(NOW))
    assert (found_upload.name, found.name) == ("upload.csv", "2026-06-02.csv")  # earliest first
    assert found.location == str(tmp_path / "carrier-b" / "2026-06-02.csv")
    assert found.identity == f"2026-06-02.csv|{len(b'a,b\n1,2\n')}|{arrived.timestamp():.6f}"


def _far(now: datetime) -> datetime:
    """Every file written by a test has a status-change time of the real now; a `now` ahead of it
    lets the modification time alone decide, as it does for a file that was written, not copied."""
    return max(now, _real_now() + timedelta(minutes=2))


def test_the_roots_own_files_and_other_datasets_are_never_watched(tmp_path: Path) -> None:
    arrived = NOW - timedelta(minutes=5)
    _put(tmp_path, "shared.csv", at=arrived)
    _put(tmp_path / "uploaded", "shared-upload.csv", at=arrived)
    _put(tmp_path / "carrier-a", "theirs.csv", at=arrived)
    _put(tmp_path / "carrier-b" / "sub", "deeper.csv", at=arrived)
    assert _names(_recipe(), tmp_path, _far(NOW)) == []


def test_a_file_outside_the_folder_through_a_link_is_never_watched(tmp_path: Path) -> None:
    outside = _put(tmp_path / "elsewhere", "secret.csv", at=NOW - timedelta(minutes=5))
    (tmp_path / "carrier-b").mkdir()
    (tmp_path / "carrier-b" / "link.csv").symlink_to(outside)
    assert _names(_recipe(), tmp_path, _far(NOW)) == []


def test_a_file_still_being_written_waits_until_it_has_settled(tmp_path: Path) -> None:
    path = _put(tmp_path / "carrier-b", "growing.csv")
    written = datetime.fromtimestamp(path.stat().st_mtime, UTC)
    assert _names(_recipe(schedule_set_at=written - timedelta(hours=1)), tmp_path,
                  written + timedelta(seconds=30)) == []  # fmt: skip
    assert _names(_recipe(schedule_set_at=written - timedelta(hours=1)), tmp_path,
                  written + timedelta(seconds=61)) == ["growing.csv"]  # fmt: skip


def test_a_file_there_before_the_watch_was_set_is_not_taken(tmp_path: Path) -> None:
    path = _put(tmp_path / "carrier-b", "old.csv", at=SET_AT - timedelta(days=3))
    changed = datetime.fromtimestamp(path.stat().st_ctime, UTC)
    # Set after the file's last status change too: it was there, untouched, before the watch.
    recipe = _recipe(schedule_set_at=changed + timedelta(seconds=1))
    assert _names(recipe, tmp_path, changed + timedelta(minutes=5)) == []


def test_a_file_copied_in_with_its_old_modification_time_still_counts_as_arriving(
    tmp_path: Path,
) -> None:
    """A copy that keeps the original's modification time (Finder, `cp -p`) cannot keep its
    status-change time, which is when it arrived here."""
    before = _real_now() - timedelta(seconds=2)
    _put(tmp_path / "carrier-b", "kept-date.csv", at=SET_AT - timedelta(days=30))
    recipe = _recipe(schedule_set_at=before)
    assert _names(recipe, tmp_path, _real_now() + timedelta(minutes=2)) == ["kept-date.csv"]


def test_the_pattern_matches_the_whole_name_and_its_case(tmp_path: Path) -> None:
    arrived = NOW - timedelta(minutes=5)
    # Distinct names: a case-insensitive disk (macOS's) would make `a.csv` and `a.CSV` one file.
    for name in ("a.csv", "b.CSV", "c.csv.bak", "d.csv"):
        _put(tmp_path / "carrier-b", name, at=arrived)
    assert sorted(_names(_recipe(), tmp_path, _far(NOW))) == ["a.csv", "d.csv"]


def test_a_recipe_without_a_watch_or_a_dataset_has_nothing_waiting(tmp_path: Path) -> None:
    _put(tmp_path / "carrier-b", "a.csv", at=NOW - timedelta(minutes=5))
    assert _names(_recipe(schedule_watch=None), tmp_path, _far(NOW)) == []
    assert _names(_recipe(dataset_id=None), tmp_path, _far(NOW)) == []


def test_the_identity_changes_when_the_file_is_replaced(tmp_path: Path) -> None:
    _put(tmp_path / "carrier-b", "a.csv", at=NOW - timedelta(minutes=5))
    (first,) = waiting_files(_recipe(), root=tmp_path, now=_far(NOW))
    time.sleep(0.01)
    _put(tmp_path / "carrier-b", "a.csv", b"a,b\n1,2\n3,4\n", at=NOW - timedelta(minutes=4))
    (second,) = waiting_files(_recipe(), root=tmp_path, now=_far(NOW))
    assert first.identity != second.identity
