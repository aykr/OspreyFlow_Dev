"""The licence gate's recorded entries (`06_DECISIONS.md` ADR-135 Amendment 6 decision 7; the owner's
ruling 2 of 11 November 2026 on P12's licence check): `laurium` 0.6.0, `arrow-pd-parser` 2.2.0 and
`tiktoken` 0.14.0 are MIT on the evidence of their licence files, which their metadata does not say in
a form the gate reads. Each entry admits that package at that version and nothing else.

Each plant is the row pip-licenses really gives the gate (`find_offenders`' input): `UNKNOWN` for the
two with no licence metadata, the full MIT text in `License` for tiktoken (which the gate's expression
parser refuses, `process/lanes/platform/p12/LICENCE_CHECK.md`).
"""

from __future__ import annotations

import pytest

from tools import licence_check

MIT_TEXT = (
    "MIT License\n\nCopyright (c) 2022 OpenAI, Shantanu Jain\n\nPermission is hereby granted, free "
    "of charge, to any person obtaining a copy of this software and associated documentation files "
    '(the "Software"), to deal in the Software without restriction, including without limitation '
    "the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies"
)


def _row(name: str, version: str, licence: str) -> dict[str, str]:
    return {"Name": name, "Version": version, "License": licence}


RECORDED = [
    _row("laurium", "0.6.0", "UNKNOWN"),
    _row("arrow-pd-parser", "2.2.0", "UNKNOWN"),
    _row("tiktoken", "0.14.0", MIT_TEXT),
]


def test_the_entries_are_the_three_the_owner_ruled_on() -> None:
    assert set(licence_check.RECORDED_LICENCE_EVIDENCE) == {
        ("laurium", "0.6.0"),
        ("arrow-pd-parser", "2.2.0"),
        ("tiktoken", "0.14.0"),
    }
    for evidence in licence_check.RECORDED_LICENCE_EVIDENCE.values():
        assert "MIT" in evidence


@pytest.mark.parametrize("row", RECORDED, ids=lambda r: r["Name"])
def test_without_its_entry_the_gate_refuses_it(row: dict[str, str]) -> None:
    """Red first: the rows really fail the gate's own reading, so the entries are what admits them."""
    assert not licence_check.is_allowed(row["License"], package=row["Name"])


@pytest.mark.parametrize("row", RECORDED, ids=lambda r: r["Name"])
def test_a_recorded_package_at_its_version_passes(row: dict[str, str]) -> None:
    assert licence_check.find_offenders([row]) == []


@pytest.mark.parametrize("row", RECORDED, ids=lambda r: r["Name"])
def test_a_recorded_package_at_another_version_fails_again(row: dict[str, str]) -> None:
    moved = {**row, "Version": row["Version"] + ".post1"}
    assert licence_check.find_offenders([moved]) == [moved]


def test_a_package_of_another_name_with_the_same_licence_text_fails() -> None:
    planted = _row("lauriumx", "0.6.0", "UNKNOWN")
    assert licence_check.find_offenders([planted]) == [planted]


def test_a_recorded_package_now_declaring_the_gpl_fails() -> None:
    """The entry stands for its evidence of MIT; a release that says GPL is not that release."""
    planted = _row("laurium", "0.6.0", "GPL-3.0-or-later")
    assert licence_check.find_offenders([planted]) == [planted]


def test_the_name_is_matched_as_pip_licenses_writes_it() -> None:
    """pip-licenses gives a distribution's own spelling (`arrow_pd_parser`, `Laurium`); the entry is
    the normalised name, as PyPI's."""
    assert licence_check.find_offenders([_row("arrow_pd_parser", "2.2.0", "UNKNOWN")]) == []
    assert licence_check.find_offenders([_row("Laurium", "0.6.0", "UNKNOWN")]) == []
