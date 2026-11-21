"""The Python allowlist reads `OFL-1.1` and `Python-2.0` (PL11; the gap DC1a found on 20 November
2026).

`spec/00_ARCHITECTURE.md` §7 allows SIL-OFL-1.1 and Python-2.0 outright. The Node half of the gate
(`tools/licence_check.mjs`) already read both spellings; the Python half read "sil open font" and
"psf-2.0" only, so a package that declared the SPDX identifier `OFL-1.1` or `Python-2.0` failed
the gate although the specification allows it. Each case below is the shape pip-licenses actually
hands the gate: one identifier, or several joined by "; ".

Rule 15: a bare identifier could be allowed by some other marker, so the first test takes each new
marker out of the gate's own list and shows the identifier refused. That is what proves the spelling
is what admits it, and not a fallthrough.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest
from tools import licence_check
from tools.layout import CORE


def _package(licence: str, name: str = "pkg") -> dict[str, str]:
    return {"Name": name, "Version": "1.0", "License": licence}


@pytest.mark.parametrize(
    "licence", ["OFL-1.1", "SIL-OFL-1.1", "OFL-1.1-RFN", "SIL OFL 1.1 (OFL-1.1)"]
)
def test_the_ofl_spellings_pass(licence: str) -> None:
    assert licence_check.find_offenders([_package(licence)]) == []


@pytest.mark.parametrize(
    "licence", ["Python-2.0", "Python-2.0.1", "Python-2.0; MIT", "MIT; Python-2.0"]
)
def test_the_python_2_spellings_pass(licence: str) -> None:
    assert licence_check.find_offenders([_package(licence)]) == []


@pytest.mark.parametrize(
    "licence", ["OFL-1.1; GPL-3.0-only", "Python-2.0; AGPL-3.0", "Python-2.0 AND GPL-2.0-only"]
)
def test_a_gpl_term_beside_either_still_fails(licence: str) -> None:
    assert [p["Name"] for p in licence_check.find_offenders([_package(licence)])] == ["pkg"]


@pytest.mark.parametrize(
    ("marker", "licence"), [("ofl-1.1", "OFL-1.1"), ("python-2.0", "Python-2.0")]
)
def test_each_spelling_is_what_admits_it(
    marker: str, licence: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert marker in licence_check.ALLOWED_MARKERS
    kept = tuple(m for m in licence_check.ALLOWED_MARKERS if m != marker)
    monkeypatch.setattr(licence_check, "_MARKERS", tuple(licence_check._word(m) for m in kept))
    assert [p["Name"] for p in licence_check.find_offenders([_package(licence)])] == ["pkg"]


def test_the_two_images_copies_of_the_allowlist_read_both_spellings() -> None:
    """`services/ner/licence_gate.py` and `services/laurium/licence_gate.py` carry a copy, held to
    the gate's own list by `test_ner_licence_gate.py` and
    `tests/services/laurium/test_licence_gate.py`; each now answers the two identifiers the same
    way."""
    for relative in ("services/ner/licence_gate.py", "services/laurium/licence_gate.py"):
        spec = importlib.util.spec_from_file_location(
            Path(relative).parent.name + "_gate", CORE / relative
        )
        assert spec and spec.loader
        gate = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(gate)
        assert gate.ALLOWED_MARKERS == licence_check.ALLOWED_MARKERS
        assert gate.is_allowed("OFL-1.1") and gate.is_allowed("Python-2.0")
        assert not gate.is_allowed("OFL-1.1; GPL-3.0-only")


def test_the_node_half_reads_the_same_two_spellings() -> None:
    text = (Path(licence_check.__file__).parent / "licence_check.mjs").read_text(encoding="utf-8")
    assert re.search(r'"ofl-1\.1"', text) and re.search(r'"python-2\.0"', text)
