"""Red first (rule 15) for `scripts.client_size_queries`: each check planted out alone, its test red,
the file restored and the whole file green again. Run from the repository root:

    PYTHONPYCACHEPREFIX=$(mktemp -d) OspreyFlow_Core/.venv/bin/python \\
        OspreyFlow_Build/process/lanes/rules/queries/plants.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
CORE = ROOT / "OspreyFlow_Core"
SCRIPT = CORE / "scripts/client_size_queries.py"
TESTS = "../OspreyFlow_Build/tests/test_client_size_queries.py"

#: (name, the text planted out, what replaces it, the test that must go red)
PLANTS = [
    (
        "Q1 a row from a record m10-measure cannot read let through",
        "        if not may_read(measure, record):\n            raise QuerySetRefused(",
        "        if False:\n            raise QuerySetRefused(",
        "test_a_row_from_a_secret_document_is_refused",
    ),
    (
        "Q2 an exact row's expect_first not compared with its record",
        "        if expected != record.id or query not in _numbers(record):",
        "        if query not in _numbers(record):",
        "test_an_exact_row_expecting_a_record_it_does_not_name_is_refused",
    ),
    (
        "Q3 a number two visible records hold let through",
        "        if held.get(query, set()) != {record.id}:",
        "        if record.id not in held.get(query, set()):",
        "test_an_exact_row_whose_number_two_visible_records_hold_is_refused",
    ),
    (
        "Q4 a fulltext row's date filter not checked",
        "            or not isinstance(low, str)\n            or not isinstance(high, str)\n"
        "            or not date.fromisoformat(low) <= day <= date.fromisoformat(high)\n",
        "",
        "test_a_fulltext_row_without_its_date_filter_is_refused",
    ),
    (
        "Q5 a class with too few rows let through",
        "    if short:\n        raise QuerySetRefused(",
        "    if False:\n        raise QuerySetRefused(",
        "test_a_class_with_too_few_rows_is_refused_in_words",
    ),
    (
        "Q6 rows drawn from every record of the case, not the visible ones",
        "    visible = {i: r for i, r in case_records.items() if may_read(measure, r)}\n"
        '    people = [i for i, r in visible.items() if r.type == "Person"]',
        "    visible = dict(case_records)\n"
        '    people = [i for i, r in visible.items() if r.type == "Person"]',
        "test_every_row_is_drawn_from_a_record_the_measured_principal_reads",
    ),
    (
        "Q7 the names changes not rotated (a hash picks each, the rows a change misses dropped)",
        "names_row(visible[i], seed, CHANGES[n % 3])",
        "names_row(visible[i], seed, CHANGES[int(hashlib.sha256(i.encode()).hexdigest(), 16) % 3])",
        "test_names_rows_change_the_name_each_of_three_ways",
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
