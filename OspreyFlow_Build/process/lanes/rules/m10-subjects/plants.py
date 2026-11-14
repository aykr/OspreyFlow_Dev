"""Red first (rule 15) for `scripts.client_size_leaks` (M10 subjects of their case's unit): each check planted out alone, its test red,
the file restored and the whole file green again. Run from the repository root:

    PYTHONPYCACHEPREFIX=$(mktemp -d) OspreyFlow_Core/.venv/bin/python \\
        OspreyFlow_Build/process/lanes/rules/m10-subjects/plants.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
CORE = ROOT / "OspreyFlow_Core"
SCRIPT = CORE / "scripts/client_size_leaks.py"
TESTS = "../OspreyFlow_Build/tests/test_client_size_leaks.py"

#: (name, the text planted out, what replaces it, the test that must go red)
PLANTS = [
    (
        "S1 the part-cleared's unit not checked against the measure case's (m10-part of unit-records let through)",
        '        _opens(people, PART, unit, case, "the part-cleared")\n',
        "",
        "test_a_part_cleared_subject_of_another_unit_than_the_case_is_refused",
    ),
    (
        "S2 a leak control's unit not checked against the case's (unit-fiu on the unit-intel case let through)",
        '        _opens(people, case["control"], unit, case, "its control")\n',
        "",
        "test_a_leak_control_of_another_unit_than_the_case_is_refused",
    ),
    (
        "S3 a never-join control's unit not checked against the partner case's",
        '        _opens(people, case["control"], units[partner.dataset], case, "its control")\n',
        "",
        "test_a_never_join_control_of_another_unit_than_the_partners_case_is_refused",
    ),
    (
        "S4 the control drawn as before: the first cleared subject who may read the record, of any unit (red at the build: the check refuses the case before anything is written)",
        "    return name if name in cleared and may_read(cleared[name], record) else None\n",
        "    return next((n for n, p in cleared.items() if may_read(p, record)), None)\n",
        "test_every_subject_is_of_the_unit_of_the_case_it_searches",
    ),
    (
        "S5 a record no one who opens the case reads given no count (kept out silently)",
        "            kept_out[_marking(record)] += 1  # nobody who opens the case reads it: no case\n",
        "",
        "test_a_restricted_record_of_another_unit_is_kept_out_and_counted",
    ),
    (
        "S6 m10-part of unit-records as before, not the measure case's unit (red at the build, as S4)",
        "        id=PART, clearance=\"OFFICIAL-SENSITIVE\", org_unit=units[dataset],\n",
        "        id=PART, clearance=\"OFFICIAL-SENSITIVE\", org_unit=\"unit-records\",\n",
        "test_every_subject_is_of_the_unit_of_the_case_it_searches",
    ),
]


def pytest(*select: str) -> tuple[bool, str]:
    args = [".venv/bin/pytest", "-c", "../OspreyFlow_Build/pytest.ini", "-p", "no:cacheprovider", "-q"]
    run = subprocess.run(
        [*args, *(f"{TESTS}::{s}" for s in select)] if select else [*args, TESTS],
        cwd=CORE, capture_output=True, text=True,
    )  # fmt: skip
    lines = run.stdout.strip().splitlines()
    failed = [x for x in lines if x.startswith("FAILED")]
    return run.returncode == 0, " | ".join([*failed, lines[-1] if lines else ""])


def main() -> int:
    original = SCRIPT.read_text(encoding="utf-8")
    ok, summary = pytest()
    print(f"built: {'GREEN' if ok else 'RED'} - {summary}")
    if not ok:
        return 1
    bad = 0
    try:
        for name, old, new, test in PLANTS:
            if original.count(old) != 1:
                print(f"{name}: NOT PLANTED - the text is not in the file once")
                bad += 1
                continue
            SCRIPT.write_text(original.replace(old, new), encoding="utf-8")
            ok, summary = pytest(test)
            print(f"{name}: {'GREEN (a plant its test does not see)' if ok else 'RED'} - {summary}")
            bad += ok
            SCRIPT.write_text(original, encoding="utf-8")
    finally:
        SCRIPT.write_text(original, encoding="utf-8")
    ok, summary = pytest()
    print(f"restored: {'GREEN' if ok else 'RED'} - {summary}")
    return 1 if bad or not ok else 0


if __name__ == "__main__":
    sys.exit(main())
