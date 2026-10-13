"""The folder watch (`06_DECISIONS.md` ADR-110 decision 5, Amendment 4): which files in a recipe's
own dataset folder are waiting to be run, and what a watch may be.

A watch is a filename pattern — `*.csv` — matched against the whole name of each file directly in
the recipe's dataset's folder, as the Studio's Connect stage lists it (`list_source_files`, with
every refusal that listing makes: nothing outside, no subfolders, no dotfiles). A file is waiting
once it arrived after the watch was set and has settled for a minute; *arrived* is the later of its
modification and status-change times, since a copy can keep the first but never the second.

The executor (`scheduler.ScheduleExecutor`) takes waiting files one at a time, each once, by its
identity — name, size and modification time.
"""

from __future__ import annotations

import fnmatch
from datetime import UTC, datetime, timedelta
from pathlib import Path

from pydantic import BaseModel

from schemas.ingest import StudioRecipeDraft

from .ingest_sources import ingest_root, list_source_files
from .scheduler import ScheduleRefused

#: How long a file must have been left alone before it is taken: one still being copied is not.
SETTLE = timedelta(minutes=1)
_MAX_PATTERN = 200


class WatchedFile(BaseModel):
    name: str
    #: The container path the run reads, as the Studio's listing gives it.
    location: str
    #: Name, size and modification time: a file is taken once by this; a replaced one is new.
    identity: str
    arrived_at: datetime


def validate_watch(pattern: str, recipe: StudioRecipeDraft) -> None:
    """Refuses, in words, a watch the executor could not keep (Amendment 4, point 1)."""
    if recipe.dataset_id is None:
        raise ScheduleRefused(
            "this recipe belongs to no dataset, so it has no folder to watch; make it again in a "
            "case's dataset to watch one"
        )
    if not pattern.strip():
        raise ScheduleRefused("give a filename pattern to watch for, such as *.csv")
    if len(pattern) > _MAX_PATTERN:
        raise ScheduleRefused("a filename pattern may be at most 200 characters")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in pattern):
        raise ScheduleRefused("a filename pattern may not hold a control character")
    if "/" in pattern or "\\" in pattern or ":" in pattern:
        raise ScheduleRefused(
            "a filename pattern names files, with no folder: the folder watched is always the "
            "recipe's own dataset's"
        )
    if pattern.startswith("."):
        raise ScheduleRefused(
            "a hidden file is never offered, so a pattern may not start with a dot"
        )


def describe_watch(pattern: str, dataset_id: str) -> str:
    return f"when a file matching `{pattern}` arrives in the {dataset_id} folder"


def waiting_files(
    recipe: StudioRecipeDraft, *, root: Path | None = None, now: datetime
) -> list[WatchedFile]:
    """The files the recipe's watch would take now, earliest arrival first — before the ledger is
    asked which of them were already taken."""
    pattern, dataset = recipe.schedule_watch, recipe.dataset_id
    if not pattern or dataset is None or recipe.schedule_set_at is None:
        return []
    listing = list_source_files(root if root is not None else ingest_root(), datasets=[dataset])
    found: list[tuple[datetime, float, WatchedFile]] = []
    for offered in listing.files:
        if offered.dataset_id != dataset or not fnmatch.fnmatchcase(offered.name, pattern):
            continue
        try:
            status = Path(offered.source_location).stat()
        except OSError:
            continue
        arrived = datetime.fromtimestamp(max(status.st_mtime, status.st_ctime), UTC)
        if arrived <= recipe.schedule_set_at or arrived > now - SETTLE:
            continue
        found.append(
            (
                arrived,
                status.st_mtime,
                WatchedFile(
                    name=offered.name,
                    location=offered.source_location,
                    identity=f"{offered.name}|{status.st_size}|{status.st_mtime:.6f}",
                    arrived_at=arrived,
                ),
            )
        )
    found.sort(key=lambda item: (item[0], item[1], item[2].name))
    return [file for _, _, file in found]
