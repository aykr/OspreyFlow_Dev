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
    ("the store asked at the top clearance with no unit, not as the administrator", APP,
     [("    owned = await ownership.owned_by(user_id, admin=principal, scheme=scheme)\n",
       "    owned = await ownership.owned_by(\n        user_id, admin=principal.model_copy("
       "update={\"clearance\": \"SECRET\", \"org_unit\": None}), scheme=scheme\n    )\n")],
     [f"{R}::test_the_store_is_asked_with_the_administrators_own_unit_and_clearance",
      f"{R}::test_another_units_or_a_lower_cleared_administrator_is_told_only_that_some_are_withheld"]),
    ("the store asked at a lower clearance than the administrator's (the unit kept)", APP,
     [("    owned = await ownership.owned_by(user_id, admin=principal, scheme=scheme)\n",
       "    owned = await ownership.owned_by(\n        user_id, admin=principal.model_copy("
       "update={\"clearance\": \"OFFICIAL\"}), scheme=scheme\n    )\n")],
     [f"{R}::test_the_store_is_asked_with_the_administrators_own_unit_and_clearance"]),
    ("the route open to anyone, signed in or not", APP,
     [(_ROUTE_RIGHT + ")\nasync def person_ownership_route(\n    user_id: str,\n    principal: PrincipalDep,\n",
       '    "/v1/admin/people/{user_id}/ownership",\n)\nasync def person_ownership_route(\n'
       "    user_id: str,\n"),
      ("    owned = await ownership.owned_by(user_id, admin=principal, scheme=scheme)\n",
       '    principal = Principal(id="anonymous", clearance="SECRET", org_unit="unit-1")\n'
       "    owned = await ownership.owned_by(user_id, admin=principal, scheme=scheme)\n")],
     [f"{R}::test_a_person_with_no_token_is_refused"]),
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
     [f"{S}::test_each_item_left_out_is_said_to_be_withheld_and_never_named[proposal_of_another_unit_on_this_units_case]"]),
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
    ("a proposal's case's unit unchecked in the list (its own unit alone)", O,
     [('FROM link_type_proposals p {_CASE.format(col="p.investigation_id")}',
       "FROM link_type_proposals p JOIN investigations i ON i.id = p.investigation_id "
       "AND i.removed_at IS NULL")],
     [f"{S}::test_each_item_left_out_is_said_to_be_withheld_and_never_named[proposal_of_this_unit_on_another_units_case]"]),
    ("a watch's unit unchecked in the list", O,
     [('FROM drawn_watches w {_CASE.format(col="w.case_id")}',
       "FROM drawn_watches w JOIN investigations i ON i.id = w.case_id AND i.removed_at IS NULL "
       "AND $2::text IS DISTINCT FROM 'x'")],
     [f"{S}::test_each_item_left_out_is_said_to_be_withheld_and_never_named[watch_elsewhere]"]),
    ("an administrator with no unit reading every unit", O,
     [('AND i.owning_unit = $2"', 'AND (i.owning_unit = $2 OR $2::text IS NULL)"')],
     [f"{S}::test_another_units_items_are_left_out"]),
    # --- withheld: said for every item left out, and for nothing else ---
    ("Transfer and disable never refused for a withheld item", O,
     [("        raise DisableRefused(WITHHELD_ERROR, WITHHELD_WORDS)\n\n\ndef reach(", "        return\n\n\ndef reach(")],
     [f"{S}::test_disable_is_refused_in_words_naming_nothing_while_an_item_is_withheld"]),
    ("the scheme's lowest read as the highest (an unmarked dataset cleared by everyone)", O,
     [("    return admin.org_unit, cleared_markings(admin, scheme), scheme.classification[-1]",
       "    return admin.org_unit, cleared_markings(admin, scheme), scheme.classification[0]")],
     [f"{S}::test_disable_is_refused_for_an_item_on_an_unmarked_dataset_or_none",
      f"{S}::test_an_item_above_the_administrators_clearance_is_never_named_nor_counted"]),
    ("the refusal's words naming the kind", O,
     [('    "they still own items you may not see:', '    "they still own a view you may not see:')],
     [f"{S}::test_disable_is_refused_in_words_naming_nothing_while_an_item_is_withheld"]),
    ("the refusal's words counting them", O,
     [('    "they still own items you may not see:', '    "they still own 2 items you may not see:')],
     [f"{S}::test_disable_is_refused_in_words_naming_nothing_while_an_item_is_withheld"]),
    ("the refusal's words giving the reason", O,
     [('    "they still own items you may not see:',
       '    "they still own items above your clearance:')],
     [f"{S}::test_disable_is_refused_in_words_naming_nothing_while_an_item_is_withheld"]),
    ("the refusal's words placing them", O,
     [('    "they still own items you may not see:',
       '    "they still own items in another unit:')],
     [f"{S}::test_disable_is_refused_in_words_naming_nothing_while_an_item_is_withheld"]),
    ("Transfer and disable always refused", O,
     [("    if await withheld(conn, person, admin_unit=unit,", "    if True or await withheld(conn, person, admin_unit=unit,")],
     [f"{S}::test_disable_is_refused_in_words_naming_nothing_while_an_item_is_withheld"]),
    ("withheld never said", O,
     [("    return bool(await conn.fetchval(_WITHHELD_SQL, person, admin_unit, cleared, top))",
       "    return False")],
     [f"{S}::test_each_item_left_out_is_said_to_be_withheld_and_never_named"]),
    ("withheld always said", O,
     [("    return bool(await conn.fetchval(_WITHHELD_SQL, person, admin_unit, cleared, top))",
       "    return True")],
     [f"{S}::test_each_kind_the_person_owns_is_listed_by_its_case"]),
    ("withheld blind to a view elsewhere", O,
     [("WHERE v.created_by = $1 AND i.owning_unit IS DISTINCT FROM $2",
       "WHERE v.created_by = $1 AND FALSE")],
     [f"{S}::test_each_item_left_out_is_said_to_be_withheld_and_never_named[view_elsewhere]"]),
    ("withheld blind to a proposal's own unit", O,
     [("NOT COALESCE(p.owning_unit = $2 AND i.owning_unit = $2 AND",
       "NOT COALESCE(i.owning_unit = $2 AND")],
     [f"{S}::test_each_item_left_out_is_said_to_be_withheld_and_never_named[proposal_of_another_unit_on_this_units_case]"]),
    ("withheld blind to a watch's unit", O,
     [("      AND NOT COALESCE(i.owning_unit = $2 AND {_CLEARED}, FALSE)\n)\n",
       "      AND NOT COALESCE({_CLEARED}, FALSE)\n)\n")],
     [f"{S}::test_each_item_left_out_is_said_to_be_withheld_and_never_named[watch_elsewhere]"]),
    ("withheld blind to a watch's marking", O,
     [("      AND NOT COALESCE(i.owning_unit = $2 AND {_CLEARED}, FALSE)\n)\n",
       "      AND NOT COALESCE(i.owning_unit = $2, FALSE)\n)\n")],
     [f"{S}::test_each_item_left_out_is_said_to_be_withheld_and_never_named[watch_above]", f"{S}::test_each_item_left_out_is_said_to_be_withheld_and_never_named[watch_on_no_dataset]"]),
    ("withheld asking about anyone's views", O,
     [("WHERE v.created_by = $1 AND i.owning_unit IS DISTINCT FROM $2",
       "WHERE $1::text IS NOT NULL AND i.owning_unit IS DISTINCT FROM $2")],
     [f"{S}::test_what_is_no_longer_theirs_or_no_longer_open_is_left_out"]),
    ("withheld asking about anyone's proposals", O,
     [("WHERE p.proposed_by = $1 AND p.status = 'pending'\n",
       "WHERE $1::text IS NOT NULL AND p.status = 'pending'\n")],
     [f"{S}::test_what_is_no_longer_theirs_or_no_longer_open_is_left_out"]),
    ("withheld asking about anyone's watches", O,
     [("WHERE w.owner = $1 AND w.ended_at IS NULL\n",
       "WHERE $1::text IS NOT NULL AND w.ended_at IS NULL\n")],
     [f"{S}::test_what_is_no_longer_theirs_or_no_longer_open_is_left_out"]),
    ("withheld blind to a proposal's case's unit", O,
     [("NOT COALESCE(p.owning_unit = $2 AND i.owning_unit = $2 AND",
       "NOT COALESCE(p.owning_unit = $2 AND")],
     [f"{S}::test_each_item_left_out_is_said_to_be_withheld_and_never_named[proposal_of_this_unit_on_another_units_case]"]),
    ("withheld blind to a proposal's marking", O,
     [("AND {_CLEARED}, FALSE)\n) OR EXISTS (\n    SELECT 1 FROM drawn_watches",
       ", FALSE)\n) OR EXISTS (\n    SELECT 1 FROM drawn_watches")],
     [f"{S}::test_each_item_left_out_is_said_to_be_withheld_and_never_named[proposal_above]"]),
    ("withheld counting a removed case's proposal", O,
     [("JOIN investigations i ON i.id = p.investigation_id AND i.removed_at IS NULL\n    LEFT",
       "JOIN investigations i ON i.id = p.investigation_id\n    LEFT")],
     [f"{S}::test_what_is_no_longer_theirs_or_no_longer_open_is_left_out"]),
    ("withheld counting a removed case's watch", O,
     [("JOIN investigations i ON i.id = w.case_id AND i.removed_at IS NULL\n    LEFT",
       "JOIN investigations i ON i.id = w.case_id\n    LEFT")],
     [f"{S}::test_what_is_no_longer_theirs_or_no_longer_open_is_left_out"]),
    ("withheld counting a closed proposal", O,
     [("WHERE p.proposed_by = $1 AND p.status = 'pending'\n",
       "WHERE p.proposed_by = $1\n")],
     [f"{S}::test_what_is_no_longer_theirs_or_no_longer_open_is_left_out"]),
    ("withheld counting an ended watch", O,
     [("WHERE w.owner = $1 AND w.ended_at IS NULL\n", "WHERE w.owner = $1\n")],
     [f"{S}::test_what_is_no_longer_theirs_or_no_longer_open_is_left_out"]),
    ("withheld counting a removed case's view", O,
     [("    SELECT 1 FROM case_views v\n    JOIN investigations i ON i.id = v.case_id AND "
       "i.removed_at IS NULL\n",
       "    SELECT 1 FROM case_views v\n    JOIN investigations i ON i.id = v.case_id\n")],
     [f"{S}::test_what_is_no_longer_theirs_or_no_longer_open_is_left_out"]),
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
