"""`tools.client_name_check` and files that are not text (slice BL6, round 2). The abbreviation is three letters and
compressed bytes spell it by chance: the real tree has three such hits (a video, a screenshot and a PDF) that no reword
can remove. Those three files are exempt by exact path, and only while they are not text; no other file that is not
UTF-8 is exempt. Such a file is read as `identifier_check._read` reads it, runs of four printable characters or more,
so the abbreviation is seen only with a printable byte beside it. Planted as the real caller produces them: tracked files in a
repository, the names hashed into a list of the test's own.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

MARKETING = Path(__file__).resolve().parents[1] / "marketing_site"
sys.path.insert(0, str(MARKETING))
import client_hashes  # noqa: E402
from tools import client_name_check  # noqa: E402
from tests.test_client_name_check import SYNTHETIC_ABBREVIATION, SYNTHETIC_CLIENT, _repo  # noqa: E402

NOT_TEXT = b"\xff\xd8\x00 junk \x80\x81 " + SYNTHETIC_ABBREVIATION.encode() + b") \x90\x91 more bytes\n"
LATIN_1_TEXT = ("Price \xa3 5, caf\xe9, filed by the " + SYNTHETIC_ABBREVIATION + "\n").encode("latin-1")


def _scan(tmp_path: Path, files: dict[str, str | bytes]) -> list[str]:
    held = {client_hashes.digest(SYNTHETIC_CLIENT), client_hashes.digest(SYNTHETIC_ABBREVIATION)}
    return client_name_check.scan(_repo(tmp_path, files), held)


@pytest.mark.parametrize("path", sorted(client_name_check.CHANCE_IN_COMPRESSED))
def test_a_named_compressed_file_is_exempt(tmp_path: Path, path: str) -> None:
    assert _scan(tmp_path, {path: NOT_TEXT}) == []


@pytest.mark.parametrize("path", sorted(client_name_check.CHANCE_IN_COMPRESSED))
def test_a_named_file_that_is_text_is_still_read(tmp_path: Path, path: str) -> None:
    assert len(_scan(tmp_path, {path: f"the {SYNTHETIC_ABBREVIATION} view\n"})) == 1


@pytest.mark.parametrize("content", [NOT_TEXT, LATIN_1_TEXT], ids=["noise", "latin-1 text"])
def test_the_abbreviation_in_any_other_file_that_is_not_utf_8_is_flagged(tmp_path: Path, content: bytes) -> None:
    assert len(_scan(tmp_path, {"OspreyFlow_Core/data/other.log": content})) == 1


def test_the_exemption_is_by_exact_path(tmp_path: Path) -> None:
    other = "OspreyFlow_Build/marketing_site/deploy/assets/other.jpg"
    assert len(_scan(tmp_path, {other: NOT_TEXT})) == 1


def test_the_shortest_run_that_is_read_is_flagged(tmp_path: Path) -> None:
    """Four printable characters: the abbreviation and one byte beside it."""
    content = b"\xff\x00\x80" + SYNTHETIC_ABBREVIATION.encode() + b")\x90\x91"
    assert len(_scan(tmp_path, {"OspreyFlow_Core/data/other.log": content})) == 1


def test_an_isolated_three_character_run_is_not_read(tmp_path: Path) -> None:
    """The limit of reading by printable runs, stated so the docstring's claim has a test: a name three characters long
    between bytes that are not printable is not seen (the backlog row on reading inside binary files)."""
    content = b"\xff\x00\x80" + SYNTHETIC_ABBREVIATION.encode() + b"\x90\x91"
    assert _scan(tmp_path, {"OspreyFlow_Core/data/other.log": content}) == []
