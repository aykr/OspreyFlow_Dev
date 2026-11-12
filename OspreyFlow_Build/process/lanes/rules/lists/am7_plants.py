"""ADR-146 Amendment 7's plants (rule 15): each removes one piece of the per-list reading at its real
call site, runs the tests that claim to catch it, expects them red, and puts the file back (in a
`finally`, so a failure never leaves a plant in the tree). Offline: the tests are
`tests/services/api/test_alert_citations_per_list.py`'s, against the adapter fakes; the live cases'
plants are run under a lease (`test_kyc_rules.py`, recorded beside this).

Run from OspreyFlow_Core with the closed ports pinned, OSPREY_LANE unset:
    .venv/bin/python ../OspreyFlow_Build/process/lanes/rules/lists/am7_plants.py
It prints each plant, the tests' raw summary line, and RED, GREEN or BROKEN (a collection error, an
error in a set-up, or no test selected: never read as red); it exits 1 if any plant was not RED.
The output, unfiltered, is AM7_RED_RECORD.txt, headed by the code's identity with the head.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

CORE = Path(__file__).resolve().parents[5] / "OspreyFlow_Core"
TESTS = "../OspreyFlow_Build/tests/services/api/test_alert_citations_per_list.py"
SCREENING = "../OspreyFlow_Build/tests/services/api/test_screening.py"
WRITTEN = "../OspreyFlow_Build/tests/services/api/test_alert_citations_written.py"
CLOSING = "../OspreyFlow_Build/tests/services/api/test_alert_citations_closing.py"
CLEARANCE = "../OspreyFlow_Build/tests/services/api/test_screening_clearance.py"
FILES = (TESTS, SCREENING, WRITTEN, CLOSING, CLEARANCE)

#: (name, file under Core, the text as built, the text planted, the tests that must go red[, file])
PLANTS: list[tuple[str, ...]] = [
    (
        "P1 the queue serves the alert as stored (no as_read)",
        "services/api/alert_queue.py",
        "        row.alert = as_read(row.alert, readable.citations_read(row.alert))\n",
        "",
        "test_the_queue_shows or test_what_the_queue_serves",
    ),
    (
        "P2 a single alert's read (explain, canvas, triage) serves it as stored",
        "services/api/alert_queue.py",
        "    row.alert = as_read(row.alert, readable.citations_read(row.alert))\n"
        "    return row, {i: readable.nodes[i] for i in evidence_node_ids(row.alert)}",
        "    return row, {i: readable.nodes[i] for i in evidence_node_ids(row.alert)}",
        "test_the_explanation or test_the_canvas or test_each_triage or test_a_pack_item_added",
    ),
    (
        "P3 a triage returns the stored row as the store gave it",
        "services/api/alert_queue.py",
        "    if not shown.citations:\n        return updated\n",
        "    return updated\n",
        "test_each_triage",
    ),
    (
        "P3b a suppression returns the stored row as the store gave it",
        "services/api/alert_queue.py",
        "    return _as_shown(\n"
        "        await store.set_suppression(alert_id, investigation_id, member, until=until, reason=reason),\n"
        "        row.alert,\n"
        "    )",
        "    return await store.set_suppression(\n"
        "        alert_id, investigation_id, member, until=until, reason=reason\n"
        "    )",
        "test_a_suppression_returns",
    ),
    (
        "P4 an alert with citations shown with none readable",
        "services/api/alerts.py",
        "            and (not alert.citations or bool(self.citations_read(alert)))\n",
        "",
        "test_a_reader_cleared_for_neither or test_each_path_refuses_a_reader_cleared_for_neither",
    ),
    (
        "P5 all or nothing over the citations too (the old check)",
        "services/api/alerts.py",
        "            all(i in self.nodes for i in evidence_node_ids(alert) if i not in nodes)\n"
        "            and {i for i in alert.edge_ids if i not in edges} <= self.edge_ids",
        "            all(i in self.nodes for i in evidence_node_ids(alert))\n"
        "            and set(alert.edge_ids) <= self.edge_ids",
        "test_the_queue_shows or test_the_explanation or test_each_triage or test_a_pack_item_is",
    ),
    (
        "P6 a citation read by its party alone, not its SAME_AS",
        "services/api/alerts.py",
        "            if all(i in self.nodes for i in c.node_ids) and set(c.edge_ids) <= self.edge_ids",
        "            if all(i in self.nodes for i in c.node_ids)",
        "test_a_citation_is_read_whole",
    ),
    (
        "P7 the served words name every list (the hidden list's name leaks)",
        "services/api/alerts.py",
        '            SCREENING_MATCH_WORDS, "matches " + "; and ".join(c.words for c in shown), 1',
        '            SCREENING_MATCH_WORDS, "matches " + "; and ".join(c.words for c in alert.citations), 1',
        "test_the_queue_shows or test_what_the_queue_serves or test_each_triage",
    ),
    (
        "P8 a hidden citation's ids kept in what is served (the count leaks)",
        "services/api/alerts.py",
        '            "edge_ids": [i for i in alert.edge_ids if i not in edges or i in shown_edges],',
        '            "edge_ids": list(alert.edge_ids),',
        "test_the_queue_shows or test_what_the_queue_serves or test_each_triage",
    ),
    (
        "P9 a pack item asks its reader for every citation (its own adder cannot read it back)",
        "services/api/packs.py",
        "                (), edges_shown_with(alert, item.alert.node_ids), alert.event_ids",
        "                (), alert.edge_ids, alert.event_ids",
        "test_a_pack_item_is_read",
    ),
    (
        "P10 a pack item asks only for what is outside the citations (B's match not asked)",
        "services/api/alerts.py",
        "    return [i for i in alert.edge_ids if i not in cited or i in shown]",
        "    return [i for i in alert.edge_ids if i not in cited]",
        "test_a_pack_item_asks",
    ),
    (
        "P11 a list's marking not read from its file",
        "scripts/load_screening_list.py",
        "    classification, handling_code = _marking(raw, scheme or load_uk_le_scheme(), ceiling)",
        "    classification, handling_code = None, None",
        "test_a_lists_marking",
        SCREENING,
    ),
    (
        "P12 a classification the scheme does not define taken",
        "scripts/load_screening_list.py",
        "    if classification not in scheme.classification:\n",
        "    if False:\n",
        "test_a_marking_the_scheme",
        SCREENING,
    ),
    (
        "P13 a re-marked entry read as unchanged",
        "services/api/screening.py",
        "                self.date_of_birth, self.country, self.classification,\n"
        "                self.handling_code)  # fmt: skip",
        "                self.date_of_birth, self.country)  # fmt: skip",
        "test_a_change_of_marking",
        SCREENING,
    ),
    (
        "P14 a rule screens against every list, its deployer cleared or not",
        "services/api/kyc_rules.py",
        "    return [e for e in entries if handling_readable(scheme, deployer, list_handling(e, deployer))]",
        "    return list(entries)",
        "test_a_rule_screens_only",
        SCREENING,
    ),
    # --- after the lane review (items 1, 3, 5, 6, 8, 9, 11) ---
    (
        "P15 the Alert node's sources name every list's entry (review item 1)",
        "services/api/rule_evaluation.py",
        "    return [r for r in finding.refs if r not in set(finding.cited_refs)]",
        "    return list(finding.refs)",
        "test_the_alert_node_names_no_list",
        WRITTEN,
    ),
    (
        "P16 every pending write dropped once one merges (review item 5)",
        "services/api/rule_evaluation.py",
        "                pending=tuple(w for w in finding.pending if w.id not in renamed),",
        "                pending=(),",
        "test_a_match_merged_on_one_list",
        WRITTEN,
    ),
    (
        "P17 each ALERTED_ON marked as the node, not by its citation",
        "services/api/rule_evaluation.py",
        "    targets = [(t, by_target.get(t, marking)) for t in finding.node_ids]",
        "    targets = [(t, marking) for t in finding.node_ids]",
        "test_each_cited_partys_alerted_on",
        WRITTEN,
    ),
    (
        "P18 an ALERTED_ON written where no single marking joins",
        "services/api/rule_evaluation.py",
        "    targets = [(t, by_target.get(t, marking)) for t in finding.node_ids]",
        "    targets = [(t, by_target.get(t) or marking) for t in finding.node_ids]",
        "test_a_cited_party_no_single_marking",
        WRITTEN,
    ),
    (
        "P19 a re-mark reads the citations too",
        "services/api/alerts.py",
        "        core_nodes = sorted(set(alert.referent_node_ids) - cited_nodes)",
        "        core_nodes = sorted(set(alert.referent_node_ids))",
        "test_a_re_mark_reads_only",
        WRITTEN,
    ),
    (
        "P20 an alert with citations saved without each citation's handlings (review 2, item 6)",
        "services/api/rule_evaluation.py",
        "                cited_handlings=await self._cited_handlings(finding, node_id),",
        "                cited_handlings=None,",
        "test_what_the_trends_count",
        WRITTEN,
    ),
    (
        "P21 the rule audit reads a cited firing all or nothing (review 2, item 4; flipped)",
        "services/api/rule_holds.py",
        "            return readable.whole(alert)",
        "            return readable.covers(*cited)",
        "test_the_rule_audit_reads_a_firing",
    ),
    (
        "P22 a unit-restricted code taken for a list (review item 11)",
        "scripts/load_screening_list.py",
        '    if scheme.handling_codes[code].dissemination == "restricted":\n',
        "    if False:\n",
        "test_a_marking_the_scheme",
        SCREENING,
    ),
    (
        "P23 a marking above the deployment's ceiling taken (review item 11)",
        "scripts/load_screening_list.py",
        "    if (ceiling or DeploymentCeiling.from_env(scheme)).above(classification):",
        "    if False:",
        "test_a_marking_above",
        SCREENING,
    ),
    (
        "P24 the listed party looked up by name and list again (review 2, item 9)",
        "services/api/kyc_rules.py",
        '        hit.entry.entity_type, "list_entry_id", hit.entry.id, deployer\n',
        '        hit.entry.entity_type, "family_name" if hit.entry.entity_type == "Person" else "name",\n'
        '        str(candidate.properties["family_name" if hit.entry.entity_type == "Person" else "name"]),\n'
        '        deployer, also={"list_name": hit.entry.list_name},\n',
        "test_a_match_reuses or test_a_match_on_a_name",
        WRITTEN,
    ),
    # --- after the orchestrator's review of 12 November 2026 (items 1, 2, 4, 6, 7, 10; the ruling) ---
    (
        "P25 the KYC gate asks the store for every list (item 1)",
        "services/api/kyc_rules.py",
        "    cleared = ListClearance.of(deployer, ctx.scheme)\n",
        "    cleared = ListClearance(tuple(ctx.scheme.classification), tuple(ctx.scheme.handling_codes))\n",
        "test_the_kyc_gate_screens_only",
        CLEARANCE,
    ),
    (
        "P26 a sentence rule asks the store for every list (item 1)",
        "services/api/sentence_rules.py",
        "                subject, cleared=ListClearance.of(deployer, gate.scheme)\n",
        "                subject, cleared=ListClearance(tuple(gate.scheme.classification),"
        " tuple(gate.scheme.handling_codes))\n",
        "test_a_sentence_rule_screens_only",
        CLEARANCE,
    ),
    (
        "P27 a sentence's preview asks the store for every list (item 1)",
        "services/api/app.py",
        "                    sentence.subject, cleared=ListClearance.of(principal, scheme)\n",
        "                    sentence.subject, cleared=ListClearance(tuple(scheme.classification),"
        " tuple(scheme.handling_codes))\n",
        "test_a_sentences_preview_screens_only",
        CLEARANCE,
    ),
    (
        "P28 a sentence's words name its list (item 1)",
        "services/api/rule_sentences.py",
        'match to an entry on a screening list"',
        'match to an entry on {hits[0].entry.list_name}"',
        "test_a_sentences_words_name_no_list",
        CLEARANCE,
    ),
    (
        "P29 a list clearance admits a restricted code the reader may not receive (item 1)",
        "services/api/screening.py",
        'if d.dissemination != "restricted" or k in principal.receivable_handling_codes',
        "if True",
        "test_a_list_clearance_admits_exactly",
        CLEARANCE,
    ),
    (
        "P30 the rule audit names a list's re-screening to every reader (item 2)",
        "services/api/rule_holds.py",
        "            return cleared.admits(\n",
        "            return True or cleared.admits(\n",
        "test_the_rule_audit_names_a_lists_re_screening",
    ),
    (
        "P31 a close decides every citation, not the closer's own (the owner's ruling)",
        "services/api/alerts.py",
        "        if c.words in words:\n",
        "        if True:\n",
        "test_an_a_only_false_positive or test_an_approver_cleared or test_a_proposer_cleared",
        CLOSING,
    ),
    (
        "P32 an alert with citations served with its stored status (the owner's ruling)",
        "services/api/alerts.py",
        "            **served_triage(alert, shown),\n",
        "",
        "test_an_a_only_false_positive or test_a_b_cleared or test_homes_counts or test_the_reports_figures"
        " or test_the_alerts_address",
        CLOSING,
    ),
    (
        "P33 the queue's status and assignee filters left to the stored row (the owner's ruling)",
        "services/api/alert_queue.py",
        "        if not _as_filtered(row.alert, reader, statuses=statuses, show=show):\n            continue\n",
        "",
        "test_the_queues_filters or test_homes_counts",
        CLOSING,
    ),
    (
        "P34 a claim by a reader shown the alert closed (the owner's ruling)",
        "services/api/alert_queue.py",
        '    if shown.status != "open":',
        "    if False:",
        "test_a_reader_shown_the_alert_closed",
        CLOSING,
    ),
    (
        "P35 an approval decides the approver's open citations too (the ruling, item 10's point 6)",
        "services/api/alerts.py",
        '            elif action == "approve" and c.status == "closing":',
        '            elif action == "approve" and c.status != "closed":',
        "test_a_proposer_cleared_for_one_list",
        CLOSING,
    ),
    (
        "P36 a trend's row counted for a reader who may read a citation outside it (item 6)",
        "services/api/alerts.py",
        '            "hidden_from": [groups[n] for n in range(len(citations)) if n not in inside],',
        '            "hidden_from": [],',
        "test_the_trends_count_a_cited_alert",
        CLOSING,
    ),
    (
        "P37 the adapters' predicate without its hidden groups (item 6)",
        "packages/adapters/analytics_duckdb/alert_facts.py",
        '        f"HAVING MIN(CASE WHEN COALESCE(({viewable.where}), FALSE) THEN 1 ELSE 0 END) = 1)"',
        '        f"HAVING MIN(CASE WHEN COALESCE(({viewable.where}), FALSE) THEN 1 ELSE 0 END) = 2)"',
        "test_the_trends_count_a_cited_alert",
        CLOSING,
    ),
    (
        "P38 a trend's marking read from a hidden citation's handlings too (item 6)",
        "packages/adapters/analytics_duckdb/alert_facts.py",
        'AND grp = 0"',
        '"',
        "test_the_trends_count_a_cited_alert",
        CLOSING,
    ),
    (
        "P39 a load's report counts an alert its loader may not read (item 7)",
        "services/api/rule_evaluation.py",
        "        return True\n    return any(handling_readable(scheme, reader, h) for h in finding.citation_handlings)",
        "        return True\n    return True",
        "test_a_loads_report_counts_only",
        CLEARANCE,
    ),
    (
        "P40 a reload lowering a list's marking taken (item 8)",
        "services/api/screening.py",
        "    return new_rank < old_rank or (new_rank == old_rank and new[1] != kept[1])",
        "    return False",
        "test_a_reload_that_would_lower",
        CLEARANCE,
    ),
]


def _run(selector: str, tests: str = TESTS) -> tuple[str, str]:
    """RED only where pytest ran the tests and some failed (exit 1, "failed" in its summary, no
    error); a collection error, an error in a set-up or no test selected is BROKEN, never read as
    red (the orchestrator's review, a note: a plant that breaks the import proves nothing)."""
    done = subprocess.run(
        [".venv/bin/pytest", "-c", "../OspreyFlow_Build/pytest.ini", "-p", "no:cacheprovider",
         "-q", tests, "-k", selector],
        cwd=CORE, capture_output=True, text=True, check=False,
    )  # fmt: skip
    lines = [line for line in done.stdout.splitlines() if line.strip()]
    summary = lines[-1] if lines else done.stderr.strip()
    if done.returncode == 0:
        return "GREEN", summary
    if done.returncode == 1 and " failed" in summary and " error" not in summary:
        return "RED", summary
    return "BROKEN", summary


def main() -> int:
    green_left = 0
    for tests in FILES:
        state, base_line = _run("", tests)
        print(f"built, {tests.rsplit('/', 1)[-1]}: {state} - {base_line}")
        if state != "GREEN":
            return 1
    for name, rel, built, planted, selector, *rest in PLANTS:
        tests = rest[0] if rest else TESTS
        path = (CORE / rel).resolve()
        source = path.read_text(encoding="utf-8")
        if source.count(built) != 1:
            print(f"{name}: the built text is not in {rel} exactly once; plant not applied")
            green_left += 1
            continue
        try:
            path.write_text(source.replace(built, planted), encoding="utf-8")
            state, line = _run(selector, tests)
        finally:
            path.write_text(source, encoding="utf-8")
        print(f"{name} [{rel}; -k {selector}]: {state} - {line}")
        green_left += 0 if state == "RED" else 1
    after = [_run("", tests) for tests in FILES]
    for (state, after_line), tests in zip(after, FILES, strict=True):
        print(f"restored, {tests.rsplit('/', 1)[-1]}: {state} - {after_line}")
    return 1 if green_left or any(state != "GREEN" for state, _ in after) else 0


if __name__ == "__main__":
    sys.exit(main())
