"""Synthetic phone extraction (ADR-094 step 3): what two of the SMS fixture's phones hold, a few
photos with text in them, a short video with speech, and saved notes, so held content can be read
and extracted from without a real dataset (rule 9). Everything is invented; the numbers are the SMS
fixture's own, so the phones meet their messages on one `Endpoint` each.

The media is made, not stored in the repository: each picture is drawn by ffmpeg with its text, and
the video's speech is spoken by macOS `say`. Where a tool is missing the rows are written without
that file and what was left out is said, never pretended.
"""

from __future__ import annotations

import csv
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .sms import PHONES

FOLDER = "phone-extraction"
CSV_NAME = "phone-extraction.csv"
FIELDS = ("phone", "photo", "video", "note")


@dataclass(frozen=True)
class _Item:
    phone: str
    photo: str | None = None
    photo_text: str = ""
    video: str | None = None
    video_speech: str = ""
    note: str = ""


_ITEMS = (
    _Item(
        PHONES["dana"],
        photo="IMG_0001.png",
        photo_text="GREY FORD TRANSIT  AB12 CDE",
        video="VID_0001.mp4",
        video_speech="Tomasz Wolski is driving the van to gate three at seven on Friday.",
        note="Unit 4 Marsh Lane Purfleet. Ask Priya Nair for the Harlow paperwork.",
    ),
    _Item(
        PHONES["callum"],
        photo="IMG_0002.png",
        photo_text="RIVERSIDE CAFE  DOCK ROAD",
        note="Payment 4,500 to the Barclays account ending 1192.",
    ),
)

_FONTS = ("/System/Library/Fonts/Supplemental/Arial.ttf", "/System/Library/Fonts/Helvetica.ttc")


def _font() -> str | None:
    return next((f for f in _FONTS if Path(f).is_file()), None)


def _draw(text: str) -> str:
    font = _font()
    font_part = f"fontfile={font}:" if font else ""
    return f"drawtext={font_part}text='{text}':fontcolor=white:fontsize=40:x=40:y=(h-text_h)/2"


def _make_photo(ffmpeg: str, path: Path, text: str) -> None:
    subprocess.run(
        [
            ffmpeg,
            "-y",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=0x2b2f36:s=900x500",
            "-vf",
            _draw(text),
            "-frames:v",
            "1",
            str(path),
        ],
        check=True,
    )


def _make_video(ffmpeg: str, say: str | None, path: Path, speech: str) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        audio = Path(tmp) / "speech.aiff"
        inputs = ["-f", "lavfi", "-i", "color=c=0x1d2025:s=640x360:d=6"]
        if say is not None:
            subprocess.run([say, "-o", str(audio), speech], check=True)
            inputs += ["-i", str(audio)]
        subprocess.run(
            [
                ffmpeg,
                "-y",
                "-loglevel",
                "error",
                *inputs,
                "-vf",
                _draw("VID 0001"),
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-shortest",
                str(path),
            ],
            check=True,
        )


def write_phone_extraction(
    ingest_root: Path, *, ffmpeg: str | None = None, say: str | None = None
) -> tuple[Path, list[str]]:
    """Writes `<root>/phone-extraction/phone-extraction.csv` and its media. `ffmpeg` and `say` are
    looked up when not given. Returns the CSV's path and what could not be made."""
    ffmpeg = ffmpeg if ffmpeg is not None else shutil.which("ffmpeg")
    say = say if say is not None else shutil.which("say")
    folder = ingest_root / FOLDER
    folder.mkdir(parents=True, exist_ok=True)
    missing: list[str] = []
    rows = []
    for item in _ITEMS:
        photo = video = ""
        if item.photo:
            if ffmpeg:
                _make_photo(ffmpeg, folder / item.photo, item.photo_text)
                photo = item.photo
            else:
                missing.append(f"{item.photo}: ffmpeg was not found, so no picture was drawn")
        if item.video:
            if ffmpeg:
                _make_video(ffmpeg, say, folder / item.video, item.video_speech)
                video = item.video
                if say is None:
                    missing.append(f"{item.video}: `say` was not found, so the video is silent")
            else:
                missing.append(f"{item.video}: ffmpeg was not found, so no video was made")
        rows.append({"phone": item.phone, "photo": photo, "video": video, "note": item.note})
    path = folder / CSV_NAME
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(FIELDS))
        writer.writeheader()
        writer.writerows(rows)
    return path, missing
