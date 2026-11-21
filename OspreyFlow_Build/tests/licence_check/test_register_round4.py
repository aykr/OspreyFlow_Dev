"""The register's gate, round 4 (PL11): a test must fit the row's kind, and `named_in` must hold
every file that names the thing.

Two faults the verifier found in round 3, each shown red here before the code that answers it:

1. **The gate let a row pick whichever test its licence passed, whatever its kind.** The owner's
   definition (21 November 2026, ruling 1) is per kind: software and base images by OSI approval,
   model weights by the same test on the weights' own licence, data by a recognised open-data
   licence. A `weight` row at `CC-BY-4.0` / `open-data` / `confirmed` passed, though the OSI does
   not approve CC-BY-4.0 and the definition refuses that weight. Each kind below is planted at a
   real row's shape (the real row, with the licence and the test changed together).
2. **`named_in` was checked only for being a file.** Six files name `python:3.12-slim`; B13a listed
   three. The derivation already carries every naming file, so a row now fails when a file the code
   names it in is missing from its `named_in`.

**The folders this test walks:** none of its own. It reads the register and what
`tools.licence_register.read_sources` reads (that module's docstring lists the folders: under
`OspreyFlow_Core`, `Dockerfile*` by one `rglob` over the whole of Core, `harness/**/*.py`,
`cli/**/*.py`, `scripts/*.py`, `providers/*.yaml` and the named files; under `OspreyFlow_Build`,
`spec/LICENCE_REGISTER.yaml` by name).
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


@pytest.fixture
def sources() -> dict[str, str]:
    return dict(reg.read_sources())


def _planted(
    rows: list[dict[str, Any]], row_id: str, change: Callable[[dict[str, Any]], None]
) -> list[dict[str, Any]]:
    copied = copy.deepcopy(rows)
    change(next(r for r in copied if r["id"] == row_id))
    return copied


def _found(rows: list[dict[str, Any]]) -> list[str]:
    return reg.find_register_violations(rows, reg.named_by_code(reg.read_sources()))


def _first(rows: list[dict[str, Any]], kind: str) -> dict[str, Any]:
    return next(r for r in rows if r["kind"] == kind and r["name"] != "planetiler")


# --- 1. the test must fit the kind ---------------------------------------------------------------

#: `(kind, a licence that passes the data test but not the OSI's, the test the row claims)`. The
#: image and the weight cases are the finding's own; the others close the gap for the other kinds.
WRONG_TEST = [
    ("weight", "CC-BY-4.0", "open-data"),
    ("weight", "public-domain", "open-data"),
    ("weight", "Apache-2.0", "osi-software"),
    ("image", "public-domain", "open-data"),
    ("image", "CC-BY-4.0", "open-data"),
    ("image", "Apache-2.0", "osi-weights"),
    ("font", "CC-BY-4.0", "open-data"),
    ("font", "OFL-1.1", "osi-weights"),
    ("map-data", "Apache-2.0", "osi-software"),
    ("map-data", "Apache-2.0", "osi-weights"),
]


@pytest.mark.parametrize(("kind", "licence", "test"), WRONG_TEST)
def test_a_test_that_does_not_fit_the_kind_is_flagged(
    real_rows: list[dict[str, Any]], kind: str, licence: str, test: str
) -> None:
    row = _first(real_rows, kind)

    def change(r: dict[str, Any]) -> None:
        r.update(licence=licence, test=test, status="confirmed")
        r["where_read"] = r.get("where_read") or "the licence file at the pin, 21 November 2026"

    found = _found(_planted(real_rows, row["id"], change))
    assert any(
        row["id"] in v and f"a {kind} row cannot pass by the test {test}" in v for v in found
    ), found


@pytest.mark.parametrize("status", ["confirmed", "conditional", "unconfirmed"])
def test_a_wrong_test_is_flagged_whatever_the_status(
    real_rows: list[dict[str, Any]], status: str
) -> None:
    row = next(r for r in real_rows if r["kind"] == "weight")

    def change(r: dict[str, Any]) -> None:
        r.update(test="open-data", status=status, owner_ruling="21 November 2026, a ruling")
        if status == "unconfirmed":
            r.update(licence=None, where_read=None, must_read="the model card at the revision")

    found = _found(_planted(real_rows, row["id"], change))
    assert any(
        row["id"] in v and "a weight row cannot pass by the test open-data" in v for v in found
    ), (status, found)


def test_the_map_build_tool_may_pass_the_software_test(real_rows: list[dict[str, Any]]) -> None:
    """Planetiler is a tool the map build runs, not data: it is the one map-data row that passes by
    `osi-software`, and the real register already says so."""
    row = next(r for r in real_rows if r["name"] == "planetiler")
    assert row["kind"] == "map-data" and row["test"] == "osi-software"
    assert _found(real_rows) == []


def test_another_map_row_may_not_borrow_the_map_tools_exception(
    real_rows: list[dict[str, Any]],
) -> None:
    """The exception is by name: a dataset that passes by `osi-software` is a licence the data test
    does not cover and is flagged (it would be a tool, and a tool has its own row)."""
    row = next(r for r in real_rows if r["name"] == "planetiler:natural_earth")
    found = _found(
        _planted(real_rows, row["id"], lambda r: r.update(licence="MIT", test="osi-software"))
    )
    assert any(
        row["id"] in v and "a map-data row cannot pass by the test osi-software" in v for v in found
    ), found


@pytest.mark.parametrize("kind", ["weight", "image", "font", "map-data"])
def test_restricted_is_open_to_every_kind_so_a_ruled_exception_still_registers(
    real_rows: list[dict[str, Any]], kind: str
) -> None:
    """`restricted` is the name of failing, and a `conditional` row with an owner ruling is how the
    gate lets a failing row in (GDS Transport). The kind check must not refuse it."""
    row = _first(real_rows, kind)

    def change(r: dict[str, Any]) -> None:
        r.update(
            licence="LicenseRef-Proprietary",
            test="restricted",
            status="conditional",
            owner_ruling="21 November 2026, a ruling",
            where_read="the licence file at the pin, 21 November 2026",
        )

    found = _found(_planted(real_rows, row["id"], change))
    assert not [v for v in found if "cannot pass by the test" in v], found


def test_every_real_row_uses_a_test_its_kind_may_use(real_rows: list[dict[str, Any]]) -> None:
    for row in real_rows:
        allowed = reg.tests_for(row["kind"], row["name"])
        assert row["test"] in allowed, (row["id"], row["test"], allowed)


# --- 2. named_in holds every file that names the thing -------------------------------------------


def test_b13a_lists_every_file_that_names_python_slim(
    real_rows: list[dict[str, Any]], sources: dict[str, str]
) -> None:
    code = sorted(
        f
        for n in reg.named_by_code(sources)
        if (n.kind, n.name, n.pin) == ("image", "python", "3.12-slim")
        for f in n.files
    )
    row = next(r for r in real_rows if r["id"] == "B13a")
    assert len(code) >= 6, code
    assert sorted(row["named_in"]) == code


def test_a_file_the_code_names_an_image_in_but_the_row_leaves_out_is_flagged(
    real_rows: list[dict[str, Any]], sources: dict[str, str]
) -> None:
    """A new Dockerfile with `FROM python:3.12-slim`, at the shape every other one has."""
    sources["services/newthing/Dockerfile"] = "FROM python:3.12-slim\nRUN true\n"
    found = reg.find_register_violations(real_rows, reg.named_by_code(sources))
    assert any(
        "B13a" in v and "services/newthing/Dockerfile" in v and "named_in" in v for v in found
    ), found


def test_a_naming_file_removed_from_a_real_row_is_flagged(
    real_rows: list[dict[str, Any]],
) -> None:
    rows = _planted(real_rows, "B13a", lambda r: r["named_in"].remove("services/ner/Dockerfile"))
    found = _found(rows)
    assert any("B13a" in v and "services/ner/Dockerfile" in v and "named_in" in v for v in found), (
        found
    )


@pytest.mark.parametrize("row_id", ["W1", "F1", "M2", "B3"])
def test_a_row_of_each_kind_loses_a_naming_file_and_is_flagged(
    real_rows: list[dict[str, Any]], row_id: str
) -> None:
    row = next(r for r in real_rows if r["id"] == row_id)
    victim = row["named_in"][0]
    rows = _planted(real_rows, row_id, lambda r: r["named_in"].remove(victim))
    found = _found(rows)
    assert any(row_id in v and victim in v and "named_in" in v for v in found), found


# --- round 5: the two branches no test reached ---------------------------------------------------


def test_a_conditional_row_whose_licence_fails_its_stated_test_is_flagged(
    real_rows: list[dict[str, Any]],
) -> None:
    """The real F3 (GDS Transport): still `conditional` with its owner ruling and its restricted
    licence text, but now claiming `osi-software`. The only licence check for a conditional row is
    the one that runs the claimed test on the text, so this fails only if that branch is there."""
    f3 = next(r for r in real_rows if r["id"] == "F3")
    assert f3["status"] == "conditional" and f3["owner_ruling"]  # the real row's own shape
    rows = _planted(real_rows, "F3", lambda r: r.update(test="osi-software"))
    found = _found(rows)
    assert any(
        "F3" in v and "does not pass the test osi-software" in v and f3["licence"] in v
        for v in found
    ), found
    assert not any("F3" in v for v in _found(real_rows)), "the real F3 must stay clean"


def test_a_register_pin_the_code_no_longer_names_is_flagged_while_the_code_names_the_image(
    real_rows: list[dict[str, Any]], sources: dict[str, str]
) -> None:
    """Laurium's `FROM` moves to another image, which gets its own row. `python` is still named by
    B13a's six Dockerfiles and B13b's file still exists, so the only thing left to report B13b's
    pin is the register-side check on a pin that no code names."""
    b13b = next(r for r in real_rows if r["id"] == "B13b")
    path = b13b["named_in"][0]
    assert path == "services/laurium/Dockerfile"
    text = sources[path]
    moved = text.replace(f"FROM python:{b13b['pin']}", "FROM debian:12-slim")
    assert moved != text
    sources[path] = moved
    new_row = copy.deepcopy(b13b)
    new_row.update(id="B13c", name="debian", pin="12-slim")
    new_row["named_in"] = [path]
    found = reg.find_register_violations([*real_rows, new_row], reg.named_by_code(sources))
    assert any(
        "'python'" in v and repr(b13b["pin"]) in v and "no code names" in v for v in found
    ), found
    # the planted state is otherwise settled: nothing but that pin is reported
    assert not any("debian" in v for v in found), found
    assert not any("is not in the register" in v for v in found), found
