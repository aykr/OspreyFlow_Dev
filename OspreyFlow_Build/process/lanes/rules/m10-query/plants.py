"""Red first (rule 15) for `scripts.client_size_leaks` (M10's hidden words: the query's own dropped, the record's others kept): each check planted out alone, its test red,
the file restored and the whole file green again. Run from the repository root:

    PYTHONPYCACHEPREFIX=$(mktemp -d) OspreyFlow_Core/.venv/bin/python \\
        OspreyFlow_Build/process/lanes/rules/m10-query/plants.py
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
        "Q1 a hidden word the case's own query holds kept (red at the build: the check refuses it)",
        "    return not seen(word, corpus) and word.lower() not in str(case[\"query\"]).lower()\n",
        "    return not seen(word, corpus)\n",
        "test_no_written_case_keeps_a_word_its_own_query_holds",
    ),
    (
        "Q2 a hidden word in the case's own query not refused by the check",
        "            if word.lower() in str(case[\"query\"]).lower():\n",
        "            if False:\n",
        "test_a_hidden_word_its_own_query_holds_is_refused",
    ),
    (
        "Q3 a leak case's hidden words its title alone (no words left once the query's are dropped)",
        "    words += sorted({v for v in _strings(dict(record.props)) if v and v != record.words})\n    words += sorted(set(_WORD.findall(text or \"\")) - set(words))\n",
        "",
        "test_a_case_asking_the_hidden_title_still_checks_its_hidden_document_s_own_words",
    ),
    (
        "Q4 a case's checked words miscounted",
        "    leaks = [{**c, \"words_checked\": len(c[\"never_text\"])} for c in leaks]\n",
        "    leaks = [{**c, \"words_checked\": 1} for c in leaks]\n",
        "test_each_leak_case_counts_its_checked_words_and_the_file_its_share",
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
