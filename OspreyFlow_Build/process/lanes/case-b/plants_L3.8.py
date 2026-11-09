"""L3.8's red record, reproducible (rule 15): each plant breaks one rule at the call site its test
reaches, runs that test, and puts the file back. Run from `OspreyFlow_Core`, offline with closed
ports pinned (59991-59994), or with `--live` under a lease, against the leased Postgres:

    .venv/bin/python ../OspreyFlow_Build/process/lanes/case-b/plants_L3.8.py [--live]

Each row prints the plant, the tests run and pytest's tally; every plant must fail at least one,
with failed tests and no error (a plant that breaks collection proves nothing).
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys
import tempfile

R = "../OspreyFlow_Build/tests/services/api/test_person_ownership_route.py"
RR = "../OspreyFlow_Build/tests/services/api/test_route_rights.py"
S = "../OspreyFlow_Build/tests/services/api/test_person_ownership_store.py"
APP = "services/api/app.py"
O = "services/api/person_ownership.py"

Plant = tuple[str, str, list[tuple[str, str]], list[str]]

_ROUTE_RIGHT = (
    '    "/v1/admin/people/{user_id}/ownership",\n'
    "    dependencies=[Depends(require_right(Right.MANAGE_PEOPLE))],\n"
)

OFFLINE: list[Plant] = [
    ("the route answered without manage_people", APP,
     [(_ROUTE_RIGHT, '    "/v1/admin/people/{user_id}/ownership",\n')],
     [f"{R}::test_everyone_without_manage_people_is_refused",
      f"{RR}::test_every_route_names_the_right_the_table_gives_it"]),
    ("the route behind a right analysts hold", APP,
     [(_ROUTE_RIGHT, '    "/v1/admin/people/{user_id}/ownership",\n'
                     "    dependencies=[Depends(require_right(Right.INVESTIGATE))],\n")],
     [f"{R}::test_everyone_without_manage_people_is_refused",
      f"{RR}::test_every_route_names_the_right_the_table_gives_it"]),
    ("the store asked as the person, not the administrator", APP,
     [("    owned = await ownership.owned_by(user_id, admin=principal, scheme=scheme)\n",
       "    owned = await ownership.owned_by(\n        user_id, admin=principal.model_copy("
       "update={\"clearance\": \"TOP SECRET\", \"org_unit\": None}), scheme=scheme\n    )\n")],
     [f"{R}::test_the_store_is_asked_with_the_administrators_own_unit_and_clearance"]),
    ("the read not audited", APP,
     [('        action="read_person_ownership",\n', '        action="read_person_ownership_x",\n')],
     [f"{R}::test_the_read_is_audited_with_its_count"]),
]

LIVE: list[Plant] = [
    ("the unit clause dropped (every case)", O,
     [('AND i.owning_unit = $2"', 'AND ($2::text IS NULL OR TRUE)"')],
     [f"{S}::test_another_units_items_are_left_out"]),
    ("a proposal's own unit unchecked (the case's alone)", O,
     [("p.status = 'pending' AND p.owning_unit = $2 AND", "p.status = 'pending' AND")],
     [f"{S}::test_each_kind_the_person_owns_is_listed_by_its_case"]),
    ("the clearance clause dropped", O,
     [('_CLEARED = "COALESCE(d.highest_marking, $4) = ANY($3::text[])"',
       '_CLEARED = "($3::text[] IS NOT NULL AND $4::text IS NOT NULL)"')],
     [f"{S}::test_an_item_above_the_administrators_clearance_is_never_named_nor_counted"]),
    ("a dataset with no marking read as unmarked", O,
     [('_CLEARED = "COALESCE(d.highest_marking, $4) = ANY($3::text[])"',
       '_CLEARED = "(d.highest_marking IS NULL OR d.highest_marking = ANY($3::text[])) '
       'AND $4::text IS NOT NULL"')],
     [f"{S}::test_an_item_above_the_administrators_clearance_is_never_named_nor_counted"]),
    ("a removed case's items listed", O,
     [("AND i.removed_at IS NULL AND", "AND")],
     [f"{S}::test_what_is_no_longer_theirs_or_no_longer_open_is_left_out"]),
    ("a decided proposal listed", O,
     [("p.proposed_by = $1 AND p.status = 'pending' AND", "p.proposed_by = $1 AND")],
     [f"{S}::test_what_is_no_longer_theirs_or_no_longer_open_is_left_out"]),
    ("an ended watch listed", O,
     [("w.owner = $1 AND w.ended_at IS NULL AND", "w.owner = $1 AND")],
     [f"{S}::test_what_is_no_longer_theirs_or_no_longer_open_is_left_out"]),
    ("someone else's view listed", O,
     [("WHERE v.created_by = $1\n", "WHERE $1::text IS NOT NULL\n")],
     [f"{S}::test_what_is_no_longer_theirs_or_no_longer_open_is_left_out"]),
    ("the analyst's view name in the label", O,
     [("SELECT v.id, v.case_id, v.shared, v.drawing, i.name AS case_name",
       "SELECT v.id, v.case_id, v.shared, v.drawing, v.name AS case_name")],
     [f"{S}::test_labels_name_the_case_and_never_what_the_analyst_wrote"]),
]


def _pytest(tests: list[str]) -> subprocess.CompletedProcess[str]:
    """Each run with a bytecode cache of its own: two plants of one file can leave it the same
    size within the same second, and Python would then run the first plant's cached bytecode for
    the second (found 9 November 2026: a plant reported green that fails by hand)."""
    with tempfile.TemporaryDirectory() as cache:
        return subprocess.run(
            [".venv/bin/pytest", "-c", "../OspreyFlow_Build/pytest.ini", "-q", "-p", "no:warnings",
             "-p", "no:randomly", "-p", "no:cacheprovider", *tests],
            capture_output=True, text=True, check=False,
            env={**os.environ, "PYTHONPYCACHEPREFIX": cache},
        )  # fmt: skip


def _tally(done: subprocess.CompletedProcess[str]) -> str:
    lines = [ln for ln in done.stdout.splitlines() if " passed" in ln or " failed" in ln
             or " error" in ln]  # fmt: skip
    return lines[-1].strip("= ") if lines else f"exit {done.returncode}"


def run(plants: list[Plant]) -> int:
    """Each plant red, for the right reason: the named tests pass unplanted first (the suite is
    green before), and a plant counts as red only when pytest reports failed tests and no error
    (exit 1): a collection, import or fixture error the plant causes proves nothing."""
    every = sorted({t for _, _, _, tests in plants for t in tests})
    baseline = _pytest(every)
    if baseline.returncode != 0:
        print(f"Not green unplanted: {_tally(baseline)}")
        print(baseline.stdout[-3000:])
        return len(plants)
    print(f"Unplanted: {_tally(baseline)}")
    held = 0
    for title, file, swaps, tests in plants:
        path = pathlib.Path(file)
        before = path.read_text()
        after = before
        for old, new in swaps:
            assert after.count(old) == 1, f"{title}: the plant's text is not found once in {file}"
            after = after.replace(old, new)
        path.write_text(after)
        try:
            done = _pytest(tests)
        finally:
            path.write_text(before)
        tally = _tally(done)
        red = done.returncode == 1 and " failed" in tally and " error" not in tally
        held += 0 if red else 1
        names = ", ".join(t.split("::")[1] for t in tests)
        print(f"| {title} | `{file}` | {names} | {tally}{'' if red else ' (NOT RED)'} |")
    return held


if __name__ == "__main__":
    still_green = run(LIVE if "--live" in sys.argv else OFFLINE)
    sys.exit(1 if still_green else 0)
