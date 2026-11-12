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
        [f"{B}/services/api/test_screening_list_routes.py", CROSS],
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
    every = [CROSS, *AM7]
    red, line = _run([f"{B}/services/api/test_screening_refresh.py", *every])
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
    red, line = _run([f"{B}/services/api/test_screening_refresh.py", *every])
    print(f"restored: {'RED' if red else 'GREEN'} - {line}")
    return 1 if green_left or red else 0


if __name__ == "__main__":
    sys.exit(main())
