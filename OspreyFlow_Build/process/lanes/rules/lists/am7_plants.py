"""ADR-146 Amendment 7's plants (rule 15): each removes one piece of the per-list reading at its real
call site, runs the tests that claim to catch it, expects them red, and puts the file back (in a
`finally`, so a failure never leaves a plant in the tree). Offline: the tests are
`tests/services/api/test_alert_citations_per_list.py`'s, against the adapter fakes; the live cases'
plants are run under a lease (`test_kyc_rules.py`, recorded beside this).

Run from OspreyFlow_Core with the closed ports pinned, OSPREY_LANE unset:
    .venv/bin/python ../OspreyFlow_Build/process/lanes/rules/lists/am7_plants.py
It prints each plant, the tests' raw summary line, and RED or GREEN; it exits 1 if any plant
stayed green. The output, unfiltered, is AM7_RED_RECORD.txt.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

CORE = Path(__file__).resolve().parents[5] / "OspreyFlow_Core"
TESTS = "../OspreyFlow_Build/tests/services/api/test_alert_citations_per_list.py"
SCREENING = "../OspreyFlow_Build/tests/services/api/test_screening.py"

#: (name, file under Core, the text as built, the text planted, the tests that must go red[, file])
PLANTS: list[tuple[str, ...]] = [
    (
        "P1 the queue serves the alert as stored (no as_read)",
        "services/api/alert_queue.py",
        "        row.alert = as_read(row.alert, readable.citations_read(row.alert))\n"
        "        ids = evidence_node_ids(row.alert)",
        "        ids = evidence_node_ids(row.alert)",
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
        "    classification, handling_code = _marking(raw, scheme or load_uk_le_scheme())",
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
]


def _run(selector: str, tests: str = TESTS) -> tuple[bool, str]:
    done = subprocess.run(
        [".venv/bin/pytest", "-c", "../OspreyFlow_Build/pytest.ini", "-p", "no:cacheprovider",
         "-q", tests, "-k", selector],
        cwd=CORE, capture_output=True, text=True, check=False,
    )  # fmt: skip
    lines = [line for line in done.stdout.splitlines() if line.strip()]
    return done.returncode != 0, lines[-1] if lines else done.stderr.strip()


def main() -> int:
    green_left = 0
    for tests in (TESTS, SCREENING):
        base_red, base_line = _run("", tests)
        print(f"built, {tests.rsplit('/', 1)[-1]}: {'RED' if base_red else 'GREEN'} - {base_line}")
        if base_red:
            return 1
    for name, rel, built, planted, selector, *rest in PLANTS:
        tests = rest[0] if rest else TESTS
        path = CORE / rel
        source = path.read_text(encoding="utf-8")
        if source.count(built) != 1:
            print(f"{name}: the built text is not in {rel} exactly once; plant not applied")
            green_left += 1
            continue
        try:
            path.write_text(source.replace(built, planted), encoding="utf-8")
            red, line = _run(selector, tests)
        finally:
            path.write_text(source, encoding="utf-8")
        print(f"{name} [{rel}; -k {selector}]: {'RED' if red else 'GREEN'} - {line}")
        green_left += 0 if red else 1
    after = [_run("", tests) for tests in (TESTS, SCREENING)]
    for (after_red, after_line), tests in zip(after, (TESTS, SCREENING), strict=True):
        print(f"restored, {tests.rsplit('/', 1)[-1]}: {'RED' if after_red else 'GREEN'} - {after_line}")
    return 1 if green_left or any(red for red, _ in after) else 0


if __name__ == "__main__":
    sys.exit(main())
