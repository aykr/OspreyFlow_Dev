"""The synthetic phone extraction (ADR-094 step 3): its export and its media. The media is made by ffmpeg and `say`
where they are present. Offline: nothing here reaches a store. The extraction's load through the recipe the Studio
would build stages its rows in the object store, so it is a live test, in the live set's tests/ingest:
tests/ingest/test_phone_extraction_load.py."""

from __future__ import annotations

import csv
import shutil
from pathlib import Path

import pytest

from demo_fixtures.phone_extraction import FIELDS, write_phone_extraction


def test_without_the_tools_the_rows_are_written_and_what_was_left_out_is_said(
    tmp_path: Path,
) -> None:
    path, missing = write_phone_extraction(tmp_path, ffmpeg="", say="")
    rows = list(csv.DictReader(path.read_text(encoding="utf-8").splitlines()))
    assert tuple(rows[0]) == FIELDS
    assert all(r["photo"] == "" and r["video"] == "" for r in rows)
    assert any("IMG_0001.png" in m and "ffmpeg" in m for m in missing)


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg makes the media")
def test_with_ffmpeg_the_pictures_and_the_video_are_made(tmp_path: Path) -> None:
    path, _ = write_phone_extraction(tmp_path)
    assert (path.parent / "IMG_0001.png").read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    assert (path.parent / "VID_0001.mp4").read_bytes()[4:8] == b"ftyp"
