"""The live half of CARRIES row 113's red and ADR-146 Amendment 7's plants (rule 15), run under the rules
lane's lease on its stack (`stack_lease.sh remote rules -- …`, from OspreyFlow_Core, the stack's ports
pinned by `remote`). Each plant removes one piece at its real call site in the remote copy, runs the live
tests that claim to catch it, expects them red, and puts the file back (in a `finally`).

- **L0** (row 113): `test_screening_refresh.py`'s teardown no longer removes its lists; that file then
  `test_kyc_rules.py`'s cross-file case, in one run in that order. **L0b**: the same for
  `test_screening_list_routes.py`'s `world`. The other two files' lists name none of `test_kyc_rules`'
  people, so no cross-file case sees them; their teardowns are the same call.
- **L1**: one finding per hit again (two Petrov alerts): `test_one_owner_on_two_lists_raises_one_alert_citing_both`.
- **L2**: the repoint not rewriting the citations: `test_a_true_positive_confirms_only_the_matches_the_closer_can_read`.
- **L3**: the `Alert` node marked by its citations too: `test_a_reader_not_cleared_for_a_list_is_shown_…`.
- **L4**: every list screened, the deployer cleared or not: `test_a_rule_screens_only_against_lists_…`.
- **L5** (the lane review's item 10): an update dropping a marked list's marking, in the store and in
  a refresh. **L6** (item 7): the re-screening screening every list, at its own call site.
- **L7** (item 8): a rename leaving the citations' nodes; **L2b** the same for the repoint, by the
  store's own case.

- **L20 to L23** (the lane review of the second pass): a hold's note, an unmarked list's reader, an
  approval's confirm, and the listed party's properties on the real ArcadeDB store.
- **L8 to L19** (the orchestrator's review of 12 November 2026 and the owner's ruling of ~15:30): the
  store's `WHERE` filters, a list's kept marking, a reload's refusal, the routes' hidden-list answer,
  the refresh's audit, a load's count, a close's confirm and its decisions, and the trends' groups.

Prints each plant's raw pytest summary line and RED, GREEN or BROKEN (a collection error, an error
in a set-up, or nothing run: never read as red); exits 1 if any was not RED or the built tree is
not green before and after.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

CORE = Path(__file__).resolve().parents[5] / "OspreyFlow_Core"
B = "../OspreyFlow_Build/tests"
KYC = f"{B}/ingest/test_kyc_rules.py"
CROSS = f"{KYC}::test_no_other_file_leaves_a_list_naming_this_files_people"
REFRESH = f"{B}/services/api/test_screening_refresh.py"
STORE = f"{B}/services/api/test_screening_list_store.py"
ALERTS = f"{B}/services/api/test_alerts.py::test_a_repoint_and_a_rename_rewrite_each_citation_with_the_alerts_own_lists"
REFRESH_MARKED = f"{REFRESH}::test_a_refresh_keeps_a_marked_lists_marking_and_screens_it_only_for_a_deployer_cleared_for_it"
AM7 = [f"{KYC}::{n}" for n in (
    "test_one_owner_on_two_lists_raises_one_alert_citing_both",
    "test_a_reader_not_cleared_for_a_list_is_shown_the_alert_with_the_other_list_alone",
    "test_a_true_positive_confirms_only_the_matches_the_closer_can_read",
    "test_a_rule_screens_only_against_lists_its_deployer_is_cleared_for",
)]  # fmt: skip
#: After the orchestrator's review of 12 November 2026 (items 1 to 10, the owner's ruling of ~15:30).
REVIEW = [f"{KYC}::{n}" for n in (
    "test_a_reader_not_cleared_for_a_list_is_given_a_risk_its_hidden_match_takes_no_part_in",
    "test_a_close_decides_only_the_matches_its_closer_may_read",
    "test_a_loads_report_counts_only_the_alerts_its_loader_may_read",
    "test_an_approval_by_a_reader_cleared_for_both_confirms_only_the_proposed_match",
    "test_each_proposal_confirms_by_its_own_disposition",
    "test_a_held_loads_note_counts_only_the_matches_its_loader_may_read",
)]  # fmt: skip
STORE_CASES = [f"{STORE}::{n}" for n in (
    "test_a_lists_entries_are_read_only_for_a_clearance_admitting_its_marking",
    "test_a_lists_subscription_and_refreshes_are_read_only_for_a_clearance_admitting_it",
    "test_an_emptied_list_keeps_its_marking",
    "test_a_reload_that_would_lower_a_lists_marking_is_refused_and_changes_nothing",
    "test_a_list_held_with_no_marking_is_hidden_from_a_reader_below_official",
)]  # fmt: skip
ROUTES = f"{B}/services/api/test_screening_list_routes.py"
ROUTE_CASES = [f"{ROUTES}::{n}" for n in (
    "test_a_list_is_shown_only_to_a_reader_cleared_for_its_marking",
    "test_a_list_a_reader_is_not_cleared_for_is_answered_as_one_never_subscribed",
    "test_a_reader_cleared_for_a_list_refreshes_and_schedules_it",
)]  # fmt: skip
REFRESH_SECRET = f"{REFRESH}::test_a_marked_lists_match_found_by_a_cleared_deployer_carries_the_lists_marking"
DISABLE = f"{B}/services/api/test_custom_roles_store.py"
OWNERSHIP = f"{B}/services/api/test_person_ownership_store.py"
AUDIT_CODES = (f"{B}/services/api/test_audit_section_store.py::"
               "test_an_entry_is_read_by_its_lists_marking_as_recorded_and_by_its_handling_code")
TRENDS = f"{B}/conformance/analytics_port/test_suite.py::test_an_alert_kept_per_set_of_its_citations_is_counted_once_for_each_reader"

#: (name, file under the worktree, built text, planted text, the tests, in order)
PLANTS: list[tuple[str, str, str, str, list[str]]] = [
    (
        "L0 test_screening_refresh leaves its lists",
        "OspreyFlow_Build/tests/services/api/test_screening_refresh.py",
        # The teardown removes its lists before closing the store (the orchestrator's review, a
        # note), so the plant takes the whole try out, not the one line (an empty try: broke
        # collection, the run after the rebase onto 4ecd322: BROKEN, recorded).
        "        try:\n"
        '            await remove_screening_lists(dsn, prefixes=["Synthetic list"])\n'
        "        finally:\n"
        "            await made.close()\n",
        "        await made.close()\n",
        [f"{B}/services/api/test_screening_refresh.py", CROSS],
    ),
    (
        "L0b test_screening_list_routes leaves its lists",
        "OspreyFlow_Build/tests/services/api/test_screening_list_routes.py",
        "                    client.portal.call(\n"
        "                        partial(remove_screening_lists, PostgresConfig.from_env().dsn,\n"
        '                                prefixes=["Synthetic list"])\n'
        "                    )  # fmt: skip\n",
        "",
        # The one case that refreshes and ends with the list held: a later case's set-up empties
        # "Synthetic list" without refreshing it, so the whole file leaves no entry with or without
        # its teardown (run 1: GREEN, recorded), and could not show this teardown red.
        [f"{B}/services/api/test_screening_list_routes.py::test_a_list_is_subscribed_refreshed_and_shown", CROSS],
    ),
    (
        "L1 one finding per hit (an owner on two lists, two alerts)",
        "OspreyFlow_Core/services/api/kyc_rules.py",
        "            if hits:\n                findings.append(\n",
        "            for hits in [[h] for h in hits]:\n                findings.append(\n",
        [AM7[0]],
    ),
    (
        "L2 a repoint leaves the citations on the superseded link",
        "OspreyFlow_Core/services/api/alerts.py",
        "f\"WITH ORDINALITY AS t(e, n)), citations = {_renamed_in_citations_sql('edge_ids', 2)} \"",
        "\"WITH ORDINALITY AS t(e, n)) \"",
        [AM7[2]],
    ),
    (
        "L3 the alert's node marked by its citations too",
        "OspreyFlow_Core/services/api/rule_evaluation.py",
        "await _referent_handlings(graph, scheme, core_of(finding), unseen, known or {})",
        "await _referent_handlings(graph, scheme, finding, unseen, known or {})",
        [AM7[1]],
    ),
    (
        # The judge asks the store with the deployer's clearance (item 1); `lists_cleared_for` is
        # no longer on its path (GREEN there, the run after the rebase onto 4ecd322, recorded), so
        # the plant is at the judge's own call: a clearance admitting every list.
        "L4 every list screened, the deployer cleared or not (the judge's call)",
        "OspreyFlow_Core/services/api/kyc_rules.py",
        "    cleared = ListClearance.of(deployer, ctx.scheme)\n",
        "    cleared = ListClearance(tuple(ctx.scheme.classification), tuple(ctx.scheme.handling_codes))\n",
        [AM7[3]],
    ),
    (
        "L5 an update drops a marked list's marking",
        "OspreyFlow_Core/services/api/screening.py",
        "            if marked is not None:\n",
        "            if False:\n",
        [f"{STORE}::test_an_update_keeps_a_marked_lists_marking", REFRESH_MARKED],
    ),
    (
        # The refresh now filters the changed entries once, before it screens or audits (the
        # review's item 2): the plant is there (not applied at its old text, the run after the
        # rebase onto 4ecd322, recorded).
        "L6 the re-screening screens every list (its own call site)",
        "OspreyFlow_Core/services/api/screening_refresh.py",
        "        cleared = lists_cleared_for(changed, deployer, self.scheme)\n",
        "        cleared = list(changed)\n",
        [REFRESH_MARKED],
    ),
    (
        "L7 a rename leaves the citations' nodes",
        "OspreyFlow_Core/services/api/alerts.py",
        "f\"citations = {_renamed_in_citations_sql('node_ids', 1)} \"",
        "\"citations = citations \"",
        [ALERTS],
    ),
    (
        "L2b a repoint leaves the citations' links (the store's own case)",
        "OspreyFlow_Core/services/api/alerts.py",
        "f\"WITH ORDINALITY AS t(e, n)), citations = {_renamed_in_citations_sql('edge_ids', 2)} \"",
        "\"WITH ORDINALITY AS t(e, n)) \"",
        [ALERTS],
    ),
    # --- after the orchestrator's review of 12 November 2026 ---------------------------------------
    (
        "L8 the store's entries read for every list (item 1, the query)",
        "OspreyFlow_Core/services/api/screening.py",
        "f\"WHERE e.entity_type = $1 AND {_admitted_sql('e', 2)} ORDER BY e.id\",",
        "\"WHERE e.entity_type = $1 AND $2::text[] = $2 AND $3::text[] = $3 ORDER BY e.id\",",
        [STORE_CASES[0], AM7[3]],
    ),
    (
        "L9 every subscription shown, the reader cleared or not (item 3)",
        "OspreyFlow_Core/services/api/screening.py",
        "            if cleared is None:\n",
        "            if True:\n",
        [STORE_CASES[1], ROUTE_CASES[0]],
    ),
    (
        "L10 every list's refreshes shown (item 3)",
        "OspreyFlow_Core/services/api/screening.py",
        "f\"{_UPDATE_SELECT}{_markings_join('u')} WHERE {_admitted_sql('l', 3)} \"",
        "f\"{_UPDATE_SELECT}{_markings_join('u')} WHERE $3::text[] = $3 AND $4::text[] = $4 \"",
        [STORE_CASES[1], ROUTE_CASES[0]],
    ),
    (
        "L11 no list held hidden from a route's reader (item 3)",
        "OspreyFlow_Core/services/api/screening.py",
        "        return kept is not None and not cleared.admits(*kept)",
        "        return False",
        [STORE_CASES[1], ROUTE_CASES[1]],
    ),
    (
        # The marking is kept in screening_list_markings and every read takes it from there, so
        # the old plant in apply_update left it held (GREEN, the run after the rebase onto 4ecd322,
        # recorded): the plant now has `_kept_marking` pass the table by, reading the entries alone.
        "L12 a list's marking read from its entries alone (item 3, an emptied list)",
        "OspreyFlow_Core/services/api/screening.py",
        '"SELECT classification, handling_code FROM screening_list_markings WHERE list_name = $1"\n',
        '"SELECT classification, handling_code FROM screening_list_markings WHERE list_name = $1 AND false"\n',
        [STORE_CASES[2]],
    ),
    (
        "L13 a reload lowering a list's marking taken (item 8, at its call site)",
        "OspreyFlow_Core/services/api/screening.py",
        "            if kept is not None and _lowers(scheme, kept, new):\n",
        "            if False:\n",
        [STORE_CASES[3]],
    ),
    (
        "L14 a hidden list refreshed by name (item 3, the refresh route)",
        "OspreyFlow_Core/services/api/app.py",
        "    if await screening_lists.hidden(list_name, cleared=cleared):\n",
        "    if False:\n",
        [ROUTE_CASES[1]],
    ),
    (
        "L15 a rule's re-screening recorded for a list its deployer is not cleared for (item 2)",
        "OspreyFlow_Core/services/api/screening_refresh.py",
        "        if not cleared:\n            return 0, 0\n",
        "        if not cleared:\n            await self.audit.record(\n"
        "                principal=self.runner, action=\"rule_evaluated\",\n"
        "                investigation_id=rule.investigation_id,\n"
        "                resolved_query={\"rule_id\": rule.id, \"trigger\": \"list_update\",\n"
        "                                \"list_name\": diff.list_name, \"entries\": len(changed)},\n"
        "                result_cardinality=0,\n            )\n            return 0, 0\n",
        [REFRESH_MARKED],
    ),
    (
        "L16 a load's report counts every fresh alert (item 7, at its call site)",
        "OspreyFlow_Core/services/api/rule_evaluation.py",
        "            told = [f for f in fresh if counted_for(f, self.loader, self.scheme)]\n"
        "            if told:\n                verdict.notes",
        "            told = fresh\n            if told:\n                verdict.notes",
        [REVIEW[2]],
    ),
    (
        "L17 a close confirms every match its approver may read (the ruling, rule 5)",
        "OspreyFlow_Core/services/api/alert_queue.py",
        "            and (not alert.citations or e.id in deciding)\n",
        "",
        [REVIEW[3]],
    ),
    (
        "L18 a close decides every citation (the owner's ruling)",
        "OspreyFlow_Core/services/api/alerts.py",
        "        if c.words in words:\n",
        "        if True:\n",
        [REVIEW[1]],
    ),
    (
        "L19 the trends' rows counted without their hidden groups (item 6, ClickHouse too)",
        "OspreyFlow_Core/packages/adapters/analytics_duckdb/alert_facts.py",
        "THEN 1 ELSE 0 END) = 1)\"",
        "THEN 1 ELSE 0 END) = 2)\"",
        [TRENDS],
    ),
    # --- after the lane review of the second pass ------------------------------------------------
    (
        "L20 a hold's note said of a match its loader may not read (defect 8)",
        "OspreyFlow_Core/services/api/rule_evaluation.py",
        "                    if counted_for(finding, self.loader, self.scheme):\n",
        "                    if True:\n",
        [REVIEW[5]],
    ),
    (
        "L21 a list with no marking visible to a reader below OFFICIAL (defect 9)",
        "OspreyFlow_Core/services/api/screening.py",
        "                kept = (DEFAULT_CLASSIFICATION, DEFAULT_HANDLING_CODE)\n",
        "                pass\n",
        [STORE_CASES[4]],
    ),
    (
        "L22 an approval's confirm read from the first proposal shown (defect 4)",
        "OspreyFlow_Core/services/api/alert_queue.py",
        '        or (c.status == "closing" and proposed_by is not None and c.disposition == "true_positive"\n',
        '        or (c.status == "closing" and proposed_by is not None and disposition == "true_positive"\n',
        [REVIEW[4]],
    ),
    (
        "L23 the listed party written with an undeclared property (defect 1, on ArcadeDB)",
        "OspreyFlow_Core/services/api/kyc_rules.py",
        '    properties.update({"listing": entry.listing, "list_name": entry.list_name})',
        '    properties.update({"listing": entry.listing, "list_name": entry.list_name,'
        ' "list_entry_id": entry.id})',
        [AM7[0]],
    ),
    # --- after the orchestrator's verification of e911b90 (item 2; item 5's live red) ---------------
    (
        "L24 a disable plan naming every list's schedule, its reader cleared or not (verification of e911b90, item 2)",
        "OspreyFlow_Core/services/api/admin_people.py",
        "        f\"WHERE l.schedule_owner = $1 AND {_admitted_sql('l', 2)} ORDER BY l.list_name\",\n",
        "        \"WHERE l.schedule_owner = $1 AND $2::text[] = $2 AND $3::text[] = $3 ORDER BY l.list_name\",\n",
        [f"{DISABLE}::test_a_list_schedule_an_administrator_is_not_cleared_for_is_withheld_with_no_trace"],
    ),
    (
        "L24b a hidden list's schedule left out of the withheld check (verification of 7a1c760)",
        "OspreyFlow_Core/services/api/person_ownership.py",
        "    WHERE l.schedule_owner = $1 AND NOT (\n",
        "    WHERE FALSE AND l.schedule_owner = $1 AND NOT (\n",
        [f"{DISABLE}::test_a_list_schedule_an_administrator_is_not_cleared_for_is_withheld_with_no_trace"],
    ),
    (
        "L24c the withheld check reading a list's classification alone (the re-check of 6bfc8d6, should 4)",
        "OspreyFlow_Core/services/api/person_ownership.py",
        "        AND COALESCE(m.handling_code, '{DEFAULT_HANDLING_CODE}') = ANY($5::text[]))",
        "        AND $5::text[] = $5)",
        [f"{OWNERSHIP}::test_each_item_left_out_is_said_to_be_withheld_and_never_named[list_schedule_of_a_restricted_code]"],
    ),
    (
        "L24d every list's schedule withheld, its administrator cleared or not (the re-check of 6bfc8d6, should 4)",
        "OspreyFlow_Core/services/api/person_ownership.py",
        "        AND COALESCE(m.handling_code, '{DEFAULT_HANDLING_CODE}') = ANY($5::text[]))",
        "        AND COALESCE(m.handling_code, '{DEFAULT_HANDLING_CODE}') = ANY($5::text[]) AND FALSE)",
        [f"{OWNERSHIP}::test_a_list_schedule_the_administrator_is_cleared_for_is_not_withheld",
         f"{OWNERSHIP}::test_a_restricted_code_list_is_not_withheld_from_an_administrator_who_receives_it",
         f"{DISABLE}::test_an_administrator_cleared_for_the_list_transfers_its_schedule"],
    ),
    (
        "L25 a list's schedule given whatever the recipient's clearance (verification of e911b90, item 2)",
        "OspreyFlow_Core/services/api/admin_people.py",
        '        if item.kind == "list_schedule" and list_markings is not None:\n',
        "        if False:\n",
        [f"{DISABLE}::test_a_lists_schedule_goes_only_to_someone_cleared_for_the_list"],
    ),
    (
        "L26 a scheduled refresh run as an owner not cleared for the list (verification item 2)",
        "OspreyFlow_Core/services/api/list_schedule.py",
        "        if await self.lists.hidden(\n",
        "        if False and await self.lists.hidden(\n",
        [f"{B}/services/api/test_list_refresh_schedule.py::test_an_owner_not_cleared_for_the_list_is_refused_in_words_and_nothing_is_read"],
    ),
    (
        "L27 a ClickHouse store made before the alert facts' sets left without them (verification item 5)",
        "OspreyFlow_Core/packages/adapters/analytics_clickhouse/schema.py",
        "        if not await _has_column(client, table, column):\n            await client.command(statement)",
        "        pass",
        [f"{B}/test_analytics_clickhouse.py::test_a_store_made_before_the_alert_facts_sets_is_brought_forward_and_keeps_its_rows"],
    ),
    (
        "L28 an audit entry naming a list read by a reader not cleared for it (the re-check of 6bfc8d6, must 3)",
        "OspreyFlow_Core/services/api/audit_section.py",
        '        f" AND ({_LIST_NAMED} IS NULL OR ("',
        '        " AND (TRUE OR ("',
        [f"{B}/services/api/test_audit_section_store.py::test_an_entry_naming_a_list_is_read_only_by_a_reader_cleared_for_the_list"],
    ),
    # --- the orchestrator's verification of lists at 5c862eb (CARRIES): each half of the audit's clause
    (
        "L28b an audit entry read by its list's marking now alone, not as recorded (5c862eb, CARRIES a)",
        "OspreyFlow_Core/services/api/audit_section.py",
        "        f\"AND COALESCE(a.resolved_query->>'list_classification', 'OFFICIAL') = ANY({cls}) \"\n"
        "        f\"AND COALESCE(a.resolved_query->>'list_handling_code', 'P') = ANY({codes})))\"",
        "        \"))\"",
        [AUDIT_CODES],
    ),
    (
        "L28e an audit entry's list classification as recorded unread, its code as recorded kept (the lane review of the audit follow-up, item 3)",
        "OspreyFlow_Core/services/api/audit_section.py",
        "        f\"AND COALESCE(a.resolved_query->>'list_classification', 'OFFICIAL') = ANY({cls}) \"",
        "        \"AND TRUE \"",
        [AUDIT_CODES],
    ),
    (
        "L28f an audit entry's list classification now unread, its code now kept (the lane review of the audit follow-up, item 3)",
        "OspreyFlow_Core/services/api/audit_section.py",
        "        f\"              WHERE m.list_name = {_LIST_NAMED}), 'OFFICIAL') = ANY({cls}) \"",
        "        f\"              WHERE m.list_name = {_LIST_NAMED}), 'OFFICIAL') IS NOT NULL \"",
        [f"{B}/services/api/test_audit_section_store.py::test_an_entry_naming_a_list_is_read_only_by_a_reader_cleared_for_the_list"],
    ),
    (
        "L28c an audit entry's list code now unread (5c862eb, CARRIES a)",
        "OspreyFlow_Core/services/api/audit_section.py",
        "        f\"              WHERE m.list_name = {_LIST_NAMED}), 'P') = ANY({codes}) \"",
        "        f\"              WHERE m.list_name = {_LIST_NAMED}), 'P') IS NOT NULL \"",
        [AUDIT_CODES],
    ),
    (
        "L28d an audit entry's list code as recorded unread (5c862eb, CARRIES a)",
        "OspreyFlow_Core/services/api/audit_section.py",
        "        f\"AND COALESCE(a.resolved_query->>'list_handling_code', 'P') = ANY({codes})))\"",
        "        \"AND TRUE))\"",
        [AUDIT_CODES],
    ),
    (
        "L29 a list's audit entries recording no marking (5c862eb, CARRIES b)",
        "OspreyFlow_Core/services/api/screening.py",
        '        return {"list_classification": classification, "list_handling_code": code}',
        "        return {}",
        [f"{ROUTES}::test_each_audit_entry_about_a_list_records_the_lists_marking",
         f"{ROUTES}::test_a_scheduled_refreshs_audit_entry_records_the_lists_marking"],
    ),
    (
        "L29b a scheduled refresh's audit entry recording no marking, at its own call site (the lane review of the audit follow-up, item 1)",
        "OspreyFlow_Core/services/api/app.py",
        '                            "trigger": "schedule", "slot": slot.isoformat(),\n'
        "                            **await state.screening_lists.audit_marking(list_name)},\n",
        '                            "trigger": "schedule", "slot": slot.isoformat()},\n',
        [f"{ROUTES}::test_a_scheduled_refreshs_audit_entry_records_the_lists_marking"],
    ),
    (
        "L29c a subscription's audit entry recording another list's marking, at its own call site (the lane review of the audit follow-up, item 4)",
        "OspreyFlow_Core/services/api/app.py",
        "**await screening_lists.audit_marking(body.list_name)},",
        '**await screening_lists.audit_marking("Synthetic list")},',
        [f"{ROUTES}::test_each_audit_entry_about_a_list_records_the_lists_marking"],
    ),
]


def _run(tests: list[str]) -> tuple[str, str]:
    """RED only where pytest ran the tests and some failed (exit 1, "failed" in its summary, no
    error); a collection error, an error in a set-up or nothing run is BROKEN, never read as red
    (the orchestrator's review, a note)."""
    done = subprocess.run(
        [".venv/bin/pytest", "-c", "../OspreyFlow_Build/pytest.ini", "-p", "no:cacheprovider",
         "-p", "no:randomly", "-q", *tests],
        cwd=CORE, capture_output=True, text=True, check=False,
    )  # fmt: skip
    lines = [line for line in done.stdout.splitlines() if line.strip()]
    failed = [line for line in lines if line.startswith(("FAILED", "ERROR"))]
    summary = lines[-1] if lines else done.stderr.strip()
    said = " | ".join([*failed, summary])
    if done.returncode == 0:
        return "GREEN", said
    if done.returncode == 1 and " failed" in summary and " error" not in summary:
        return "RED", said
    return "BROKEN", said


def main() -> int:
    every = [CROSS, *AM7, *REVIEW, STORE, ALERTS, ROUTES, TRENDS, DISABLE,
             f"{B}/services/api/test_list_refresh_schedule.py", f"{B}/test_analytics_clickhouse.py",
             f"{B}/services/api/test_custom_roles_store.py", OWNERSHIP,
             f"{B}/services/api/test_audit_section_store.py"]
    state, line = _run([REFRESH, *every])
    print(f"built: {state} - {line}")
    if state != "GREEN":
        return 1
    green_left = 0
    root = CORE.parent
    for name, rel, built, planted, tests in PLANTS:
        path = root / rel
        source = path.read_text(encoding="utf-8")
        if source.count(built) != 1:
            print(f"{name}: the built text is not in {rel} exactly once; plant not applied")
            green_left += 1
            continue
        try:
            path.write_text(source.replace(built, planted), encoding="utf-8")
            state, line = _run(tests)
        finally:
            path.write_text(source, encoding="utf-8")
        print(f"{name} [{rel}]: {state} - {line}")
        green_left += 0 if state == "RED" else 1
    state, line = _run([REFRESH, *every])
    print(f"restored: {state} - {line}")
    return 1 if green_left or state != "GREEN" else 0


if __name__ == "__main__":
    sys.exit(main())
