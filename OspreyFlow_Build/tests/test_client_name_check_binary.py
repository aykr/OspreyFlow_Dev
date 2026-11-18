"""`tools.client_name_check` in a file that is not text (slice BL6). The owner's list holds a three-letter abbreviation,
and compressed bytes (a video, a screenshot, a PDF) spell three letters by chance: the real tree has three such
"hits" no reword can remove. A run shorter than `BINARY_MINIMUM` characters is therefore not read as a name in a file
that is not text, and one of the full name's length still is. Planted in the shape `_read` produces for such a file
(runs of printable characters, between bytes that do not decode).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

MARKETING = Path(__file__).resolve().parents[1] / "marketing_site"
sys.path.insert(0, str(MARKETING))
import client_hashes  # noqa: E402
from tools import client_name_check  # noqa: E402

SYNTHETIC_CLIENT = "Example Shire Constabulary"
SYNTHETIC_ABBREVIATION = "ESC"


def _lines(content: bytes, is_text: bool) -> list[int]:
    held = {client_hashes.digest(SYNTHETIC_CLIENT), client_hashes.digest(SYNTHETIC_ABBREVIATION)}
    text = content.decode("utf-8") if is_text else "\n".join(
        run.decode("ascii") for run in client_name_check.identifier_check._PRINTABLE.findall(content)
    )
    return client_name_check.client_lines(text, "OspreyFlow_Core/data/x.bin", held, is_text)


NOISE = b"\xff\xd8\x00 junk \x80\x81 " + SYNTHETIC_ABBREVIATION.encode() + b") \x90\x91 more bytes\n"


def test_a_short_name_in_noise_is_not_a_hit() -> None:
    assert _lines(NOISE, is_text=False) == []


def test_the_same_short_name_in_text_is_a_hit() -> None:
    assert _lines(f"the {SYNTHETIC_ABBREVIATION} view\n".encode(), is_text=True) == [1]


def test_the_full_name_in_a_files_metadata_is_a_hit() -> None:
    assert _lines(b"\xff\xd8\x00\x01 \x80\x81 Author: Example Shire Constabulary \x90\x91\n", is_text=False) == [1]


@pytest.mark.parametrize("name", ["Example Shire Constabulary", "ESC"])
def test_the_minimum_is_the_only_difference(name: str) -> None:
    run = client_hashes.normalise(name)
    assert (len(run) < client_name_check.BINARY_MINIMUM) == (name == "ESC")
