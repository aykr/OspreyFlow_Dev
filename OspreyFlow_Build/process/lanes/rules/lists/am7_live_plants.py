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

Prints each plant's raw pytest summary line and RED or GREEN; exits 1 if any stayed green or the built
tree is not green before and after.
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

#: (name, file under the worktree, built text, planted text, the tests, in order)
PLANTS: list[tuple[str, str, str, str, list[str]]] = [
    (
        "L0 test_screening_refresh leaves its lists",
        "OspreyFlow_Build/tests/services/api/test_screening_refresh.py",
        '        await remove_screening_lists(dsn, prefixes=["Synthetic list"])\n',
        "",
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
        "L4 every list screened, the deployer cleared or not",
        "OspreyFlow_Core/services/api/kyc_rules.py",
        "    return [e for e in entries if handling_readable(scheme, deployer, list_handling(e, deployer))]",
        "    return list(entries)",
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
        "L6 the re-screening screens every list (its own call site)",
        "OspreyFlow_Core/services/api/screening_refresh.py",
        "                entries = lists_cleared_for(\n"
        "                    [e for e in changed if e.entity_type == entity_type], deployer, self.scheme\n"
        "                )",
        "                entries = [e for e in changed if e.entity_type == entity_type]",
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
]


def _run(tests: list[str]) -> tuple[bool, str]:
    done = subprocess.run(
        [".venv/bin/pytest", "-c", "../OspreyFlow_Build/pytest.ini", "-p", "no:cacheprovider",
         "-p", "no:randomly", "-q", *tests],
        cwd=CORE, capture_output=True, text=True, check=False,
    )  # fmt: skip
    lines = [line for line in done.stdout.splitlines() if line.strip()]
    failed = [line for line in lines if line.startswith(("FAILED", "ERROR"))]
    return done.returncode != 0, " | ".join([*failed, lines[-1] if lines else done.stderr.strip()])


def main() -> int:
    every = [CROSS, *AM7, STORE, ALERTS]
    red, line = _run([REFRESH, *every])
    print(f"built: {'RED' if red else 'GREEN'} - {line}")
    if red:
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
            red, line = _run(tests)
        finally:
            path.write_text(source, encoding="utf-8")
        print(f"{name} [{rel}]: {'RED' if red else 'GREEN'} - {line}")
        green_left += 0 if red else 1
    red, line = _run([REFRESH, *every])
    print(f"restored: {'RED' if red else 'GREEN'} - {line}")
    return 1 if green_left or red else 0


if __name__ == "__main__":
    sys.exit(main())
