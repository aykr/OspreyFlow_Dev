"""Red first (rule 15) for `scripts.client_size_leaks` (M10's hidden words, only where unseen): each check planted out alone, its test red,
the file restored and the whole file green again. Run from the repository root:

    PYTHONPYCACHEPREFIX=$(mktemp -d) OspreyFlow_Core/.venv/bin/python \\
        OspreyFlow_Build/process/lanes/rules/m10-words/plants.py
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
        "W1 the hidden words not cut to the unseen (red at the build: the check refuses before writing)",
        "    leaks, leaks_dropped = withhold_seen_words(leaks, corpus)\n    joins, joins_dropped = withhold_seen_words(joins, corpus)\n",
        "    leaks_dropped = joins_dropped = 0\n",
        "test_no_written_case_s_hidden_word_is_in_what_the_part_cleared_may_read",
    ),
    (
        "W2 a never-join case's hidden word not checked against what is visible",
        "                     corpus: str | None = None) -> None:  # fmt: skip\n    cases = list(cases)\n    if corpus is not None:\n        _check_words(cases, corpus)\n",
        "                     corpus: str | None = None) -> None:  # fmt: skip\n    cases = list(cases)\n",
        "test_a_hidden_word_inside_a_visible_number_is_refused",
    ),
    (
        "W3 a leak case's hidden word not checked against what is visible",
        "unit: str,\n                corpus: str | None = None) -> None:  # fmt: skip\n    cases = list(cases)\n    if corpus is not None:\n        _check_words(cases, corpus)\n",
        "unit: str,\n                corpus: str | None = None) -> None:  # fmt: skip\n    cases = list(cases)\n",
        "test_a_hidden_word_in_a_visible_document_s_text_is_refused",
    ),
    (
        "W4 the comparison not case folded, as measure_leaks' is",
        "    return word.lower() in corpus\n",
        "    return word in corpus\n",
        "test_a_hidden_word_in_a_visible_document_s_text_is_refused",
    ),
    (
        "W5 the visible documents' texts left out of what is visible",
        "    parts += _document_texts(folder, source_key, documents)\n",
        "",
        "test_a_hidden_word_in_a_visible_document_s_text_is_refused",
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
