"""L2.5b's red record, reproducible (rule 15): each plant breaks one rule at the call site its test
reaches, runs that test, and puts the file back. Run from `OspreyFlow_Core`, offline with closed
ports pinned (59991-59994), or with `--live` under a lease, against the leased Postgres:

    .venv/bin/python ../OspreyFlow_Build/process/lanes/admin/plants_L2.5b.py [--live]

Each row prints the plant, the tests run and pytest's tally; every plant must fail at least one,
with failed tests and no error (a plant that breaks collection proves nothing). The runner is
case-b's (`process/lanes/case-b/plants_L3.8.py`), copied, not imported, so it reads this lane's
plants alone.
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys
import tempfile

T = "../OspreyFlow_Build/tests/services/api/"
ROUTES = f"{T}test_admin_roles_routes.py"
DRY = f"{T}test_admin_dataset_cases.py"
SYS = f"{T}test_admin_routes.py"
LIVE_T = f"{T}test_disable_l38_transfers.py"
CV = f"{T}test_admin_converted_views.py"
STORE = f"{T}test_custom_roles_store.py"
APP = "services/api/app.py"
P = "services/api/admin_people.py"

Plant = tuple[str, str, list[tuple[str, str]], list[str]]

#: Where the route ends the covers: after the identity provider has disabled the account.
_COVERS = (
    "    # Only now, the account disabled with nothing left elsewhere or withheld, do the person's covers\n"
    "    # end; on the 502 above they stay, with the account still enabled.\n"
    "    await admin_people.end_covers(user_id, by=principal, audit=audit)\n"
)

OFFLINE: list[Plant] = [
    ("refuse_if_withheld never asked after the transfers", APP,
     [("            await admin_people.refuse_if_withheld(user_id, admin=principal, scheme=scheme)\n",
       "            pass\n")],
     [f"{ROUTES}::test_disable_is_refused_while_an_item_is_withheld_and_the_visible_transfers_stand"]),
    ("withheld asked before the transfers (a refused transfer answered withheld_items)", APP,
     [("        try:\n            moved, elsewhere = await admin_people.transfer(\n",
       "        try:\n            await admin_people.refuse_if_withheld(user_id, admin=principal, "
       "scheme=scheme)\n            moved, elsewhere = await admin_people.transfer(\n")],
     [f"{ROUTES}::test_withheld_is_asked_only_once_the_transfers_are_accepted"]),
    ("a view's recipient need not hold investigate", P,
     [('    "view": (Right.INVESTIGATE,),\n', '    "view": (),\n')],
     [f"{ROUTES}::test_each_l38_item_needs_the_right_its_own_route_asks"]),
    ("a board's recipient need not hold draw_on_boards", P,
     [('    "board": (Right.DRAW_ON_BOARDS, Right.INVESTIGATE),\n',
       '    "board": (Right.INVESTIGATE,),\n')],
     [f"{ROUTES}::test_each_l38_item_needs_the_right_its_own_route_asks"]),
    ("a proposal's recipient need not hold propose_types", P,
     [('    "link_type_proposal": (Right.PROPOSE_TYPES,),\n', '    "link_type_proposal": (),\n')],
     [f"{ROUTES}::test_each_l38_item_needs_the_right_its_own_route_asks"]),
    ("L3.8's items given to a person of another unit", P,
     [('            item.kind in ("case_author", "home_case_author") or item.kind in CASE_KINDS\n',
       '            item.kind in ("case_author", "home_case_author")\n')],
     [f"{ROUTES}::test_an_l38_item_never_goes_to_a_person_of_another_unit"]),
    ("Admin's dry run of another unit's dataset answered", APP,
     [("    if principal.org_unit is None or dataset.owning_unit != principal.org_unit:\n"
       "        raise UnknownDatasetEgressError(dataset_id)\n    row = next(",
       "    row = next(")],
     [f"{DRY}::test_a_dry_run_is_for_an_administrator_of_the_datasets_own_unit"]),
    ("a cover ended before withheld is asked (so ended for a refused disable)", APP,
     [(_COVERS, ""),
      ("            await admin_people.refuse_if_withheld(user_id, admin=principal, scheme=scheme)\n",
       "            await admin_people.end_covers(user_id, by=principal, audit=audit)\n"
       "            await admin_people.refuse_if_withheld(user_id, admin=principal, scheme=scheme)\n")],
     [f"{ROUTES}::test_disable_is_refused_while_an_item_is_withheld_and_the_visible_transfers_stand"]),
    ("a cover ended before the identity provider answers (so ended on the 502)", APP,
     [(_COVERS, ""),
      ("        try:\n            person = await identity_admin.set_enabled(user_id, False)\n",
       "        await admin_people.end_covers(user_id, by=principal, audit=audit)\n"
       "        try:\n            person = await identity_admin.set_enabled(user_id, False)\n")],
     [f"{ROUTES}::test_a_disable_the_identity_provider_refuses_after_the_transfers_says_they_stand"]),
    ("System's unread count answered as nothing to draw", APP,
     [("        converted = ConvertedViews(\n", "        converted = None and ConvertedViews(\n")],
     [f"{SYS}::test_the_system_screen_counts_the_cases_made_views_in_the_administrators_unit"]),
    ("a case's highest read as its lowest", P,
     [("    return max(markings, key=list(classification).index)\n",
       "    return min(markings, key=list(classification).index)\n")],
     [f"{ROUTES}::test_a_cases_highest_is_the_highest_it_reads_or_the_schemes_for_none_or_unknown"]),
    ("System's count asked for another unit than the administrator's", APP,
     [("        converted = await people_store.converted_views(principal.org_unit)\n",
       "        converted = await people_store.converted_views(\"unit-other\")\n")],
     [f"{SYS}::test_the_system_screen_counts_the_cases_made_views_in_the_administrators_unit"]),
]

LIVE: list[Plant] = [
    ("L3.8's items left out of the plan", P,
     [("    l38 = await l38_owned_items(conn, person, admin_unit=admin_unit, cleared=cleared, top=top)\n",
       "    l38: list[OwnedItem] = []\n")],
     [f"{LIVE_T}::test_each_of_the_four_kinds_is_offered_moved_and_audited"]),
    ("a view's owner column left as it was", P,
     [('        "UPDATE case_views SET created_by = $2 WHERE id = $1 AND created_by = $3 AND NOT drawing"\n',
       '        "UPDATE case_views SET created_by = $3 WHERE id = $1 AND created_by = $3 AND NOT drawing"\n')],
     [f"{LIVE_T}::test_each_of_the_four_kinds_is_offered_moved_and_audited"]),
    ("a watch's owner column left as it was", P,
     [('        "UPDATE drawn_watches SET owner = $2 WHERE id = $1 AND owner = $3 AND ended_at IS NULL"\n',
       '        "UPDATE drawn_watches SET owner = $3 WHERE id = $1 AND owner = $3 AND ended_at IS NULL"\n')],
     [f"{LIVE_T}::test_each_of_the_four_kinds_is_offered_moved_and_audited"]),
    ("the plan read at every marking, not the administrator's clearance", P,
     [("        unit, cleared, top = reach(admin, scheme)\n",
       "        unit, _, top = reach(admin, scheme)\n        cleared = list(scheme.classification)\n")],
     [f"{LIVE_T}::test_an_item_above_the_administrator_is_never_offered_and_refuses_the_disable"]),
    ("the visible transfers rolled back when something is withheld (refused inside the transaction)", P,
     [("                done.append((item, to))\n        return done, plan.elsewhere\n",
       "                done.append((item, to))\n"
       "            from .person_ownership import WITHHELD_ERROR, withheld as _held\n"
       "            if await _held(conn, person, admin_unit=admin_unit, cleared=cleared, top=top):\n"
       "                raise DisableRefused(WITHHELD_ERROR, \"\")\n"
       "        return done, plan.elsewhere\n")],
     [f"{LIVE_T}::test_an_item_above_the_administrator_is_never_offered_and_refuses_the_disable"]),
    ("the transfer ending the covers itself", P,
     [("                done.append((item, to))\n        return done, plan.elsewhere\n",
       "                done.append((item, to))\n"
       "            await conn.execute(\"UPDATE teams SET cover = NULL WHERE cover = $1\", person)\n"
       "        return done, plan.elsewhere\n")],
     [f"{LIVE_T}::test_an_item_above_the_administrator_is_never_offered_and_refuses_the_disable"]),
    ("a watch on an unmarked dataset, or none, read as unmarked", P,
     [('"SELECT w.id, COALESCE(d.highest_marking, $2) AS marking FROM drawn_watches w "',
       '"SELECT w.id, d.highest_marking || CASE WHEN $2::text IS NULL THEN \'\' ELSE \'\' END '
       'AS marking FROM drawn_watches w "')],
     [f"{LIVE_T}::test_an_unmarked_dataset_or_none_is_read_at_the_schemes_highest_for_the_recipient"]),
    ("a view or board given to someone below its case's highest (Amendment 9)", P,
     [('        if item.kind in ("view", "board") and item.investigation_id is not None:\n',
       '        if False and item.investigation_id is not None:\n')],
     [f"{LIVE_T}::test_a_view_or_board_goes_only_to_someone_cleared_to_its_cases_highest"]),
    ("a case's composite members left out of its highest", P,
     [('WHERE c.investigation_id = $1\n"""\n', 'WHERE c.investigation_id = $1 AND FALSE\n"""\n')],
     [f"{LIVE_T}::test_a_view_or_board_goes_only_to_someone_cleared_to_its_cases_highest"]),
    ("the case's unit-wide level not counted", P,
     [('            "AND i.owning_unit = $3",\n', '            "AND i.owning_unit = $3 AND FALSE",\n')],
     [f"{LIVE_T}::test_a_recipient_holding_the_cases_unit_wide_level_may_take_a_view"]),
    ("a level on the case not asked of L3.8's items", P,
     [("        needed = LEVEL_NEEDED.get(key[0], AccessLevel.AUTHOR)\n",
       "        needed = LEVEL_NEEDED.get(key[0], AccessLevel.AUTHOR)\n"
       "        if key[0] in LEVEL_NEEDED:\n            continue\n")],
     [f"{LIVE_T}::test_a_recipient_without_the_case_level_or_the_marking_is_refused_and_nothing_moves"]),
    ("a proposal or watch given to someone not cleared to its marking", P,
     [("            markings_hold(plan.marking_of, items, chosen, who, scheme)\n", "")],
     [f"{LIVE_T}::test_a_recipient_without_the_case_level_or_the_marking_is_refused_and_nothing_moves"]),
    ("System's count across every unit", P,
     [('                "AND i.owning_unit = $1 WHERE v.converted_from_case IS NOT NULL",\n',
       '                "AND $1::text IS NOT NULL WHERE v.converted_from_case IS NOT NULL",\n')],
     [f"{CV}::test_the_count_is_of_the_administrators_unit_and_open_cases_only"]),
    ("System's count of a removed case's views", P,
     [('                "JOIN investigations i ON i.id = v.case_id AND i.removed_at IS NULL "\n',
       '                "JOIN investigations i ON i.id = v.case_id "\n')],
     [f"{CV}::test_the_count_is_of_the_administrators_unit_and_open_cases_only"]),
]

#: Run unplanted with the live plants, to show the suites they touch green first.
LIVE_ALSO = [STORE]


def _pytest(tests: list[str]) -> subprocess.CompletedProcess[str]:
    """Each run with a bytecode cache of its own (case-b's finding of 9 November 2026: two plants
    of one file can leave it the same size within a second, and a stale cache would run)."""
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


def run(plants: list[Plant], also: list[str]) -> int:
    every = sorted({t for _, _, _, tests in plants for t in tests} | set(also))
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
    live = "--live" in sys.argv
    still_green = run(LIVE if live else OFFLINE, LIVE_ALSO if live else [])
    sys.exit(1 if still_green else 0)
