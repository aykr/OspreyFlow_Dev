"""The register's own row checks, each shown red (PL11, round 2's finding; rule 12).

`find_register_violations` checks more than the acceptance file plants: an image row's
`os_packages`, a repeated row id, a status or kind outside the lists, a `conditional` row with
nothing of where it was read, and a `named_in` that is not a file. If any of these checks were
deleted the first round's tests would still pass. Each case below takes the real register's row,
changes the one thing, and asserts the message that names it (rule 15), so a fallthrough that
fails for another reason does not pass.

**The folders this test walks:** none of its own. It reads the register and what
`tools.licence_register.read_sources` reads (that module's docstring lists the folders).
"""

from __future__ import annotations

import copy
from collections.abc import Callable
from typing import Any

import pytest
from tools import licence_register as reg


@pytest.fixture(scope="module")
def real_rows() -> list[dict[str, Any]]:
    return reg.load_register()


@pytest.fixture(scope="module")
def named() -> list[reg.Named]:
    return reg.named_by_code(reg.read_sources())


def _planted(
    rows: list[dict[str, Any]], row_id: str, change: Callable[[dict[str, Any]], None]
) -> list[dict[str, Any]]:
    copied = copy.deepcopy(rows)
    change(next(r for r in copied if r["id"] == row_id))
    return copied


def _found(rows: list[dict[str, Any]], named: list[reg.Named]) -> list[str]:
    return reg.find_register_violations(rows, named)


def test_the_real_register_has_none_of_these_faults(
    real_rows: list[dict[str, Any]], named: list[reg.Named]
) -> None:
    assert _found(real_rows, named) == []


@pytest.mark.parametrize(
    ("what", "change", "says"),
    [
        ("no os_packages", lambda r: r.pop("os_packages"), "needs os_packages"),
        ("os_packages not a mapping", lambda r: r.update(os_packages="no"), "needs os_packages"),
        (
            "scan not yes, no or partly",
            lambda r: r["os_packages"].update(scan="maybe"),
            "needs os_packages with scan one of yes, no, partly",
        ),
        (
            "scan a boolean (YAML reads an unquoted no as one)",
            lambda r: r["os_packages"].update(scan=False),
            "needs os_packages with scan one of",
        ),
        (
            "covered_by empty",
            lambda r: r["os_packages"].update(covered_by="  "),
            "does not say how the operating-system packages are covered",
        ),
        (
            "covered_by missing",
            lambda r: r["os_packages"].pop("covered_by"),
            "does not say how the operating-system packages are covered",
        ),
    ],
)
def test_an_image_row_without_a_usable_os_packages_is_flagged(
    real_rows: list[dict[str, Any]],
    named: list[reg.Named],
    what: str,
    change: Callable[[dict[str, Any]], None],
    says: str,
) -> None:
    image = next(r for r in real_rows if r["kind"] == "image")
    found = _found(_planted(real_rows, image["id"], change), named)
    assert any(image["id"] in v and says in v for v in found), (what, found)


def test_os_packages_is_asked_of_every_image_row_and_only_of_images(
    real_rows: list[dict[str, Any]], named: list[reg.Named]
) -> None:
    for row in real_rows:
        if row["kind"] == "image":
            planted = _planted(real_rows, row["id"], lambda r: r.pop("os_packages"))
            assert any(row["id"] in v and "os_packages" in v for v in _found(planted, named)), row
        else:
            assert "os_packages" not in row, f"{row['id']} is not an image"


def test_a_repeated_row_id_is_flagged(
    real_rows: list[dict[str, Any]], named: list[reg.Named]
) -> None:
    rows = copy.deepcopy(real_rows)
    rows[1]["id"] = rows[0]["id"]
    found = _found(rows, named)
    assert any(f"the row id {rows[0]['id']!r} is used twice" in v for v in found), found


@pytest.mark.parametrize("status", ["done", "Confirmed", "", None])
def test_a_status_outside_the_three_is_flagged(
    real_rows: list[dict[str, Any]], named: list[reg.Named], status: str | None
) -> None:
    rows = _planted(real_rows, "W1", lambda r: r.update(status=status))
    found = _found(rows, named)
    assert any("W1" in v and "is not one of confirmed, unconfirmed, conditional" in v for v in found)


@pytest.mark.parametrize("kind", ["model", "Image", "", None])
def test_a_kind_outside_the_four_is_flagged(
    real_rows: list[dict[str, Any]], named: list[reg.Named], kind: str | None
) -> None:
    rows = _planted(real_rows, "W1", lambda r: r.update(kind=kind))
    found = _found(rows, named)
    assert any("W1" in v and "is not one of weight, map-data, font, image" in v for v in found)


def test_a_conditional_row_that_says_nothing_of_where_it_was_read_is_flagged(
    real_rows: list[dict[str, Any]], named: list[reg.Named]
) -> None:
    conditional = next(r for r in real_rows if r["status"] == "conditional")
    for blank in (None, "", "   "):
        rows = _planted(real_rows, conditional["id"], lambda r, b=blank: r.update(where_read=b))
        found = _found(rows, named)
        assert any(
            conditional["id"] in v and "conditional, but says nothing of where it was read" in v
            for v in found
        ), (blank, found)


def test_a_named_in_that_is_not_a_file_is_flagged(
    real_rows: list[dict[str, Any]], named: list[reg.Named]
) -> None:
    rows = _planted(real_rows, "W1", lambda r: r["named_in"].append("harness/not_a_file.py"))
    found = _found(rows, named)
    assert any("W1" in v and "'harness/not_a_file.py' is not a file" in v for v in found), found


def test_a_row_that_lacks_a_column_is_flagged(
    real_rows: list[dict[str, Any]], named: list[reg.Named]
) -> None:
    for column in reg.COLUMNS:
        rows = _planted(real_rows, "W1", lambda r, c=column: r.pop(c))
        found = _found(rows, named)
        assert any(f"no {column} column" in v for v in found), (column, found)
