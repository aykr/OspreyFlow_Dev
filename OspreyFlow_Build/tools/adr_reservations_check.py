"""The ADR reservation check (`spec/06_DECISIONS.md` ADR-142 decision 5; P5).

Lanes work in parallel, but ADR and amendment numbers are handed out in order, so the orchestrator
reserves each number in `spec/ADR_RESERVATIONS.md`, committed to `main`, before a lane writes the
record. This check reports a heading in `06_DECISIONS.md` that has no reservation row:

- an ADR heading, `## ADR-n …`, numbered above the baseline's last ADR;
- an amendment heading, `### ADR-n, Amendment m …`, numbered above that ADR's last amendment at the
  baseline (an ADR not in the baseline table had none);
- an amendment heading in any other form (`### Amendment 2 (…)`, `### ADR-n Amendment m`), beyond the
  number of such headings the baseline counted: a new amendment must use the form the check can read;
- a number reserved twice.

**The baseline** (the owner's step 0 ruling, 6 November 2026, "Baseline table"): the decision log held
some nine hundred headings before reservations existed, some in irregular forms, so the reservations
file records, once, the last ADR, each ADR's last amendment and the count of irregular amendment
headings as they stood. Only what comes after needs a row. `python -m tools.adr_reservations_check
--baseline` prints that table from the document as it stands; it was run once, at step 0.

Its red-then-green proof is `tests/test_adr_reservations.py` (rule 15): headings of the shape a lane
actually writes, planted into the real decision log, are each reported.
"""

from __future__ import annotations

import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from tools.layout import REPO as REPO_ROOT

DECISIONS_PATH = REPO_ROOT / "spec" / "06_DECISIONS.md"
RESERVATIONS_PATH = REPO_ROOT / "spec" / "ADR_RESERVATIONS.md"

_ADR_HEADING = re.compile(r"^## ADR-(\d{3})\b", re.MULTILINE)
_AMENDMENT_HEADING = re.compile(r"^### ADR-(\d{3}), Amendment (\d+)\b", re.MULTILINE)
# Any heading naming an amendment; those not matching `_AMENDMENT_HEADING` are the irregular ones.
_ANY_AMENDMENT_HEADING = re.compile(r"^#{2,5} .*\bAmendment\b.*$", re.MULTILINE)

_BASELINE_LAST_ADR = re.compile(r"^Last ADR at the baseline: ADR-(\d{3})\b", re.MULTILINE)
_BASELINE_IRREGULAR = re.compile(
    r"^Amendment headings in another form at the baseline: (\d+)\b", re.MULTILINE
)
_BASELINE_ROW = re.compile(r"^\| ADR-(\d{3}) \| (\d+) \|", re.MULTILINE)
_RESERVATION_ROW = re.compile(
    r"^\| (ADR-\d{3}(?: Amendment \d+)?) \|(?:[^|\n]*\|){3} *(reserved|written) *\|", re.MULTILINE
)


@dataclass
class Baseline:
    last_adr: int
    irregular: int
    last_amendment: dict[int, int] = field(default_factory=dict)


def headings(decisions: str) -> tuple[list[int], list[tuple[int, int]], list[str]]:
    """The ADR numbers, the (ADR, amendment) pairs and the irregular amendment headings, in order."""
    adrs = [int(n) for n in _ADR_HEADING.findall(decisions)]
    amendments = [(int(a), int(m)) for a, m in _AMENDMENT_HEADING.findall(decisions)]
    irregular = [
        h for h in _ANY_AMENDMENT_HEADING.findall(decisions) if not _AMENDMENT_HEADING.match(h)
    ]
    return adrs, amendments, irregular


def parse_baseline(reservations: str) -> Baseline:
    last = _BASELINE_LAST_ADR.search(reservations)
    irregular = _BASELINE_IRREGULAR.search(reservations)
    if last is None or irregular is None:
        raise ValueError("ADR_RESERVATIONS.md has no baseline (its last ADR and irregular count)")
    rows = {int(a): int(m) for a, m in _BASELINE_ROW.findall(reservations)}
    return Baseline(int(last.group(1)), int(irregular.group(1)), rows)


def reserved_numbers(reservations: str) -> list[str]:
    return [number for number, _status in _RESERVATION_ROW.findall(reservations)]


def find_unreserved(decisions: str, reservations: str) -> list[str]:
    """Every heading above the baseline with no reservation row, and every number reserved twice."""
    baseline = parse_baseline(reservations)
    numbers = reserved_numbers(reservations)
    reserved = set(numbers)
    problems = [
        f"{number} is reserved {count} times" for number, count in Counter(numbers).items()
        if count > 1
    ]
    adrs, amendments, irregular = headings(decisions)
    for n in adrs:
        if n > baseline.last_adr and f"ADR-{n:03d}" not in reserved:
            problems.append(f"ADR-{n:03d} has a heading but no reservation row")
    for a, m in amendments:
        if m > baseline.last_amendment.get(a, 0) and f"ADR-{a:03d} Amendment {m}" not in reserved:
            problems.append(f"ADR-{a:03d} Amendment {m} has a heading but no reservation row")
    if len(irregular) > baseline.irregular:
        problems.append(
            f"{len(irregular)} amendment headings are not in the form '### ADR-n, Amendment m' "
            f"(the baseline had {baseline.irregular}); write a new one in that form. The last: "
            f"{irregular[-1]!r}"
        )
    return problems


def baseline_table(decisions: str) -> str:
    adrs, amendments, irregular = headings(decisions)
    last: dict[int, int] = {}
    for a, m in amendments:
        last[a] = max(last.get(a, 0), m)
    lines = [
        f"Last ADR at the baseline: ADR-{max(adrs):03d}",
        f"Amendment headings in another form at the baseline: {len(irregular)}",
        "",
        "| ADR | Last amendment at the baseline |",
        "| --- | --- |",
    ]
    lines += [f"| ADR-{a:03d} | {m} |" for a, m in sorted(last.items())]
    return "\n".join(lines) + "\n"


def main(argv: list[str]) -> int:
    decisions = DECISIONS_PATH.read_text(encoding="utf-8")
    if argv[1:] == ["--baseline"]:
        print(baseline_table(decisions), end="")
        return 0
    problems = find_unreserved(decisions, RESERVATIONS_PATH.read_text(encoding="utf-8"))
    if problems:
        print("adr-reservations-check: headings in spec/06_DECISIONS.md with no reservation:")
        for p in problems:
            print(f"  - {p}")
        print("Reserve the number in spec/ADR_RESERVATIONS.md on main first (ADR-142 decision 5).")
        return 1
    print("adr-reservations-check: every heading above the baseline is reserved.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
