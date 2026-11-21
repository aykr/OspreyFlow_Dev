"""PL13 round 1 (the scout): the findings file exists, is complete, and carries no key.

`spec/PL13_GATEWAY_SCOUT.md` answers the owner's nine questions about building OspreyFlow's own
gateway image from the MIT code only. This test is pure and reads one file by its fixed path; it
**walks no folder** (it lists no folder by any means), so the scan map needs no row for it. The
plants are written to pytest's own temporary folder, which is the only other place it looks.

What it holds:

* nine numbered rows, each with a non-empty answer cell and a non-empty evidence cell;
* exactly one verdict line, `VERDICT: clean cut` or `VERDICT: not a clean cut`, with a reason;
* no key-shaped string anywhere in the file. The scan is the repository's own credential scan
  (`CREDENTIAL` in `tests/test_sites.py`: an AWS key id, a PEM private-key header, GitHub, fine-
  grained GitHub and Slack tokens, a `password`, `secret`, `api_key` or `token` assignment) plus
  the brief's `sk-` with eight or more further characters and a Google API key. The builder's own
  synthetic master key cannot be known here, so the shape is what is checked; a 64-character hex
  image digest is not key-shaped and is allowed, since the file must quote the pinned image's
  digest.

Rule 15: each of the three plants (a missing row 4, no verdict, a key-shaped string) is run through
the same `problems` function the real file is, each taking the shape the file really has (a row of
the table, the verdict line), and each is asserted to fail for its own reason and no other.
"""

from __future__ import annotations

import re
import secrets
from pathlib import Path

import pytest

FINDINGS = Path(__file__).resolve().parent.parent / "spec" / "PL13_GATEWAY_SCOUT.md"

ROWS = range(1, 10)
# `| 4 | question | answer | evidence |`: the number, then at least an answer and an evidence cell.
ROW = re.compile(r"^\|\s*(\d+)\s*\|(.*)\|\s*$")
VERDICT = re.compile(
    r"^(?:\*\*)?`?VERDICT: (clean cut|not a clean cut)`?(?:\*\*)?\s*[-:–—]\s*\S.*$"
)
_SHAPES = (
    re.compile(r"sk-[A-Za-z0-9_\-]{8,}"),  # an OpenAI-style, gateway or provider key (brief: 8+)
    re.compile(r"AIza[0-9A-Za-z_\-]{20,}"),  # a Google API key
    # The repository's own credential scan (`CREDENTIAL` in `tests/test_sites.py`), shape for shape:
    re.compile(r"AKIA[0-9A-Z]{16}"),  # an AWS access key id (row 4 discusses the Bedrock route)
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}"),  # a GitHub token
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),  # a fine-grained GitHub token
    re.compile(r"\bxox[abpr]-[A-Za-z0-9-]{10,}"),  # a Slack token
    re.compile(r"\b(?:password|passwd|secret|api[_-]?key|token)\s*[:=]\s*\S"),
)
# The repository's scan is case-insensitive over every alternative, so every shape here is too.
KEY_SHAPES = tuple(re.compile(shape.pattern, re.IGNORECASE) for shape in _SHAPES)


def problems(text: str) -> list[str]:
    """Every way `text` falls short of what the brief asked the findings file to be."""
    found: list[str] = []
    cells: dict[int, list[str]] = {}
    for line in text.splitlines():
        match = ROW.match(line)
        if match and int(match.group(1)) in ROWS:
            cells[int(match.group(1))] = [c.strip() for c in match.group(2).split("|")]
    for number in ROWS:
        if number not in cells:
            found.append(f"row {number} is missing")
            continue
        parts = cells[number]
        # The first cell after the number is the question; then the answer; then the evidence.
        if len(parts) < 3:
            found.append(f"row {number} has no answer and evidence cells")
            continue
        if not parts[-2]:
            found.append(f"row {number} has an empty answer")
        if not parts[-1]:
            found.append(f"row {number} has an empty evidence cell")
    verdicts = [
        ln.strip() for ln in text.splitlines() if ln.strip().strip("*`").startswith("VERDICT")
    ]
    if not verdicts:
        found.append("no verdict line")
    elif len(verdicts) > 1:
        found.append("more than one verdict line")
    elif not VERDICT.match(verdicts[0]):
        found.append("the verdict line is not one of the two forms with a reason")
    for shape in KEY_SHAPES:
        if shape.search(text):
            found.append(f"a key-shaped string matches {shape.pattern!r}")
    return found


def _template() -> str:
    """A findings file as the real one is shaped: a table of nine rows, then the verdict line."""
    rows = "\n".join(
        f"| {n} | question {n} | an answer for {n} | read: a file at a line |" for n in ROWS
    )
    return (
        "# PL13 gateway scout\n\n"
        "| # | Question | Answer | Evidence |\n| --- | --- | --- | --- |\n"
        f"{rows}\n\n"
        "VERDICT: clean cut — the open code runs without the folder.\n"
    )


def test_the_findings_file_exists() -> None:
    assert FINDINGS.is_file(), f"{FINDINGS} does not exist: round 1 writes it"


def test_the_findings_file_is_complete_and_carries_no_key() -> None:
    assert not problems(FINDINGS.read_text(encoding="utf-8"))


def test_the_template_is_accepted() -> None:
    # A gate that has only ever seen failures has not been shown to pass (rule 15).
    assert problems(_template()) == []


def test_a_file_without_row_4_is_refused() -> None:
    text = "\n".join(ln for ln in _template().splitlines() if not ln.startswith("| 4 |"))
    assert problems(text) == ["row 4 is missing"]


@pytest.mark.parametrize("cell", ["answer", "evidence"])
def test_a_row_with_an_empty_cell_is_refused(cell: str) -> None:
    row = "| 6 | question 6 | an answer for 6 | read: a file at a line |"
    emptied = (
        "| 6 | question 6 |  | read: a file at a line |"
        if cell == "answer"
        else "| 6 | question 6 | an answer for 6 |  |"
    )
    assert row in _template()
    expected = (
        "row 6 has an empty answer" if cell == "answer" else "row 6 has an empty evidence cell"
    )
    assert problems(_template().replace(row, emptied)) == [expected]


def test_a_row_with_no_evidence_column_is_refused() -> None:
    # Three cells in all (number, question, answer): without the `len(parts) < 3` guard the
    # question would be read as the answer and the answer as the evidence, and the row would pass.
    row = "| 4 | question 4 | an answer for 4 | read: a file at a line |"
    short = "| 4 | question 4 | an answer for 4 |"
    assert row in _template()
    assert problems(_template().replace(row, short)) == ["row 4 has no answer and evidence cells"]


def test_a_row_with_only_a_number_and_one_cell_is_refused() -> None:
    row = "| 4 | question 4 | an answer for 4 | read: a file at a line |"
    assert problems(_template().replace(row, "| 4 | question 4 |")) == [
        "row 4 has no answer and evidence cells"
    ]


def test_a_file_with_no_verdict_is_refused() -> None:
    text = "\n".join(ln for ln in _template().splitlines() if not ln.startswith("VERDICT"))
    assert problems(text) == ["no verdict line"]


def test_a_verdict_in_neither_form_is_refused() -> None:
    text = _template().replace("VERDICT: clean cut", "VERDICT: mostly clean")
    assert problems(text) == ["the verdict line is not one of the two forms with a reason"]


@pytest.mark.parametrize(
    "bare",
    [
        "VERDICT: clean cut",
        "VERDICT: not a clean cut",
        "**VERDICT: clean cut**",
        "VERDICT: clean cut —",
        "VERDICT: clean cut - ",
    ],
)
def test_a_verdict_without_a_reason_is_refused(bare: str) -> None:
    # Each is one of the two forms but gives no reason, so only the reason clause can refuse it.
    text = _template().replace("VERDICT: clean cut — the open code runs without the folder.", bare)
    assert bare in text
    assert problems(text) == ["the verdict line is not one of the two forms with a reason"]


def test_the_other_verdict_form_is_accepted() -> None:
    text = _template().replace(
        "VERDICT: clean cut — the open code runs without the folder.",
        "VERDICT: not a clean cut — a route the product uses imports the folder.",
    )
    assert problems(text) == []


@pytest.mark.parametrize(
    ("first", "second"),
    [
        ("VERDICT: clean cut", "VERDICT: not a clean cut"),
        ("VERDICT: not a clean cut", "VERDICT: clean cut"),
        ("VERDICT: clean cut", "VERDICT: clean cut"),
    ],
)
def test_a_file_with_two_verdict_lines_is_refused(first: str, second: str) -> None:
    # Each line is well formed on its own, so only the count can refuse the file: with the
    # "more than one" branch gone, `verdicts[0]` alone would match and the file would pass.
    text = _template().replace(
        "VERDICT: clean cut — the open code runs without the folder.\n",
        f"{first} — the open code runs without the folder.\n\n{second} — a route imports it.\n",
    )
    assert text.count("VERDICT") == 2
    assert problems(text) == ["more than one verdict line"]


def test_sk_with_exactly_eight_characters_is_refused_and_seven_is_not() -> None:
    # The brief's threshold, at its edge on both sides: the repository's own scan wants 20, the
    # brief says 8, and a pattern loosened to anything above 8 must fail here.
    eight = "sk-" + secrets.token_hex(4)  # 3 + 8 characters, made at run time
    seven = "sk-" + secrets.token_hex(4)[:7]
    assert len(eight) == 11 and len(seven) == 10
    refused = problems(_template().replace("an answer for 3", f"the key was {eight}"))
    assert len(refused) == 1 and refused[0].startswith("a key-shaped string matches")
    assert problems(_template().replace("an answer for 3", f"the key was {seven}")) == []


def test_a_file_with_a_key_shaped_string_is_refused() -> None:
    planted = "sk-" + secrets.token_hex(12)  # made at run time, never written to the repository
    text = _template().replace("an answer for 3", f"the master key was {planted}")
    found = problems(text)
    assert len(found) == 1 and found[0].startswith("a key-shaped string matches")


def _planted_shapes() -> dict[str, str]:
    """One synthetic string per credential shape, made at run time and never written to the repo."""
    upper = "".join(secrets.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ234567") for _ in range(16))
    # The PEM header is put together at run time so that no whole header is written in this file.
    pem = "-----BEGIN " + "RSA" + " PRIVATE" + " KEY-----"
    return {
        "an AWS access key id": "AKIA" + upper,
        "a Google API key": "AIza" + secrets.token_urlsafe(30)[:35],
        "a PEM private key header": pem,
        "a classic GitHub token": "ghp_" + secrets.token_hex(18),
        "an upper-case GitHub token": "GHP_" + secrets.token_hex(18),
        "a fine-grained GitHub token": "github_pat_" + secrets.token_hex(15),
        "a Slack token": "xoxb-" + secrets.token_hex(8),
        "a password assignment": "password=" + secrets.token_hex(6),
        "an upper-case password assignment": "PASSWORD=" + secrets.token_hex(6),
        "a secret assignment in YAML": "secret: " + secrets.token_hex(6),
        "a token assignment": "token = " + secrets.token_hex(6),
        "an api key assignment": "api_key: " + secrets.token_hex(6),
    }


@pytest.mark.parametrize("shape", sorted(_planted_shapes()))
def test_each_credential_shape_the_repository_scans_for_is_refused(shape: str) -> None:
    planted = _planted_shapes()[shape]
    # In the cell where row 4 (the Bedrock route, the key listing) would really say it.
    text = _template().replace("an answer for 4", f"the route used {planted} here")
    found = problems(text)
    assert len(found) >= 1 and all(f.startswith("a key-shaped string matches") for f in found), (
        shape,
        found,
    )


def test_prose_about_keys_without_a_value_is_not_refused() -> None:
    # The scan must not refuse the file's own words about keys (a gate that refuses honest text
    # would be removed): "a master key", "the token budget", "key tags", "secrets" and the like.
    words = "a master key made at run time, the token budget, key tags, no secrets in the env file"
    assert problems(_template().replace("an answer for 4", words)) == []


def test_a_sha256_digest_is_not_key_shaped() -> None:
    digest = "sha256:" + secrets.token_hex(32)
    assert problems(_template().replace("an answer for 3", f"the image is {digest}")) == []


def test_the_plants_are_read_from_a_file_as_the_real_one_is(tmp_path: Path) -> None:
    # The same path the real file is read by: written, then read back as UTF-8 text.
    planted = tmp_path / "PL13_GATEWAY_SCOUT.md"
    planted.write_text(_template().replace("| 4 |", "| 14 |"), encoding="utf-8")
    assert problems(planted.read_text(encoding="utf-8")) == ["row 4 is missing"]
