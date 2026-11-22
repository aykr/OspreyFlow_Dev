"""The ADR reservation check (`spec/06_DECISIONS.md` ADR-142 decision 5; P5).

Lanes work in parallel, but ADR and amendment numbers are handed out in order, so the orchestrator
reserves each number in `spec/ADR_RESERVATIONS.md`, committed to `main`, before a lane writes the
record. This check reports a heading in `06_DECISIONS.md` that has no reservation row:

- an ADR heading, `## ADR-n …`, numbered above the baseline's last ADR;
- an amendment heading, `### ADR-n, Amendment m …`, numbered above that ADR's last amendment at the
  baseline (an ADR not in the baseline table had none);
- an amendment heading in any other form (`### Amendment 2 (…)`, `### ADR-n Amendment m`), beyond the
  number of such headings the baseline counted: a new amendment must use the form the check can read;
- a number reserved twice;
- a heading written twice (`## ADR-n …` or `### ADR-n, Amendment m …`: a union merge or a repeated
  commit leaves the block twice, and `decision_log_publication_check._sections` would join the two
  silently);
- a doubled line in the reservations file (the same line twice: what a union merge leaves when both
  sides wrote it, or a row copied by hand).

**The merge-base comparison** (`--against`, `find_ledger_edits`): `spec/ADR_RESERVATIONS.md` takes
git's union merge (`.gitattributes`), which is safe only while the file changes by added rows and by
a status flip of a row from `reserved` to `written`. The comparison reads the file as it stood at
the merge-base with `main`. **An added line is allowed if it is a full reservation row** (five cells
ending `reserved` or `written`) **placed anywhere in the Reservations table, above `## Baseline`**
(the end of the table, where slice GG6 put its row, or the middle); and a base row may change from
`reserved` to `written`. Everything else is reported: a title, number, lane, date or status
edited, a row or line removed, an added line that is not a full reservation row (prose, a two-cell
Baseline-shaped row that would quietly move the baseline, a malformed `| ADR-` line), any added
line below `## Baseline`, and an added row whose number the base already holds (what a union merge
leaves of a row flipped on one side while the other side appends straight after it: the row twice,
measured in `tests/test_ledger_union_merge.py`). It needs a base, so on a checkout with none (no
`main`, no git, a file new since) it says so and passes; the merge's gate has the base.

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
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass, field

from tools.layout import REPO as REPO_ROOT
from tools.layout import ROOT, logical

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


#: Headings known to stand twice in `06_DECISIONS.md` today, with how many times and why they are
#: allowed.
#: The second copy of ADR-148 Amendment 10 is a byte-for-byte repeat of the first (found 20
#: November 2026,
#: slice BL1b: the same commit message was committed twice, f9f0f8b after 986440e). It is not
#: repaired
#: here, because deleting a 78-line block from a file other lanes append to would bounce their
#: merges; the
#: owner can delete the second copy and then this entry, and the check reports a stale entry until
#: they do.
KNOWN_DUPLICATE_HEADINGS: dict[str, int] = {"ADR-148 Amendment 10": 2}

BASELINE_HEADING = "## Baseline"
_SEPARATOR_LINE = re.compile(r"^[\s|:-]*$")
_STATUS_TAIL = re.compile(r"\| *reserved *\|\s*$")
_ROW_START = re.compile(r"^\| ADR-\d{3}\b")


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
        f"{number} is reserved {count} times"
        for number, count in Counter(numbers).items()
        if count > 1
    ]
    problems += find_doubled_lines(reservations)
    problems += find_duplicate_headings(decisions)
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


def _heading_counts(decisions: str) -> Counter[str]:
    adrs, amendments, _irregular = headings(decisions)
    counts: Counter[str] = Counter({f"ADR-{n:03d}": c for n, c in Counter(adrs).items()})
    counts.update({f"ADR-{a:03d} Amendment {m}": c for (a, m), c in Counter(amendments).items()})
    return counts


def find_duplicate_headings(decisions: str) -> list[str]:
    """Every ADR or amendment heading written more often than allowed (KNOWN_DUPLICATE_HEADINGS)."""
    return [
        f"{name} has {count} headings in 06_DECISIONS.md (a block written twice)"
        for name, count in sorted(_heading_counts(decisions).items())
        if count > KNOWN_DUPLICATE_HEADINGS.get(name, 1)
    ]


def find_stale_known_duplicates(decisions: str) -> list[str]:
    """A KNOWN_DUPLICATE_HEADINGS entry the log no longer needs: left in, it would hide a new
    repeat."""
    counts = _heading_counts(decisions)
    return [
        f"{name} is in KNOWN_DUPLICATE_HEADINGS but has {counts[name]} heading(s): remove the entry"
        for name, allowed in KNOWN_DUPLICATE_HEADINGS.items()
        if counts[name] < allowed
    ]


def find_doubled_lines(reservations: str) -> list[str]:
    """Every non-blank line of the reservations file that appears more than once."""
    lines = [ln.rstrip() for ln in reservations.splitlines() if not _SEPARATOR_LINE.match(ln)]
    return [
        f"a line appears {count} times in ADR_RESERVATIONS.md: {line[:90]!r}"
        for line, count in Counter(lines).items()
        if count > 1
    ]


def _flipped(line: str) -> str | None:
    """The row with its status changed from `reserved` to `written`, or None if it is not
    reserved."""
    match = _STATUS_TAIL.search(line)
    return None if match is None else line[: match.start()] + "| written |"


def find_ledger_edits(base: str, current: str) -> list[str]:
    """What changed in the reservations file other than rows added in the Reservations table and a
    reserved-to-written flip.

    Every non-blank line of `base` must still be in `current`, in order, unchanged or flipped. Any
    other line of `current` must be a full reservation row (`_RESERVATION_ROW`) above the
    `## Baseline` heading whose number the base does not already hold; the rest are reported.
    """
    kept = [ln.rstrip() for ln in current.splitlines() if ln.strip()]
    used = [False] * len(kept)
    problems: list[str] = []
    edited_numbers: set[str] = set()
    base_numbers: set[str] = set()
    position = 0
    for raw in base.splitlines():
        line = raw.rstrip()
        if not line.strip():
            continue
        if _RESERVATION_ROW.match(line) is not None:
            base_numbers.add(line.split("|")[1].strip())
        flipped = _flipped(line)
        for j in range(position, len(kept)):
            if kept[j] == line or (flipped is not None and kept[j].rstrip() == flipped):
                used[j] = True
                position = j + 1
                break
        else:
            number = line.split("|")[1].strip() if _ROW_START.match(line) else None
            if number is not None and any(k.startswith(f"| {number} |") for k in kept):
                edited_numbers.add(number)
                problems.append(f"the row for {number} was edited, not appended to: {line[:100]!r}")
            else:
                problems.append(f"a line was removed or edited: {line[:100]!r}")
    boundary = next((j for j, line in enumerate(kept) if line == BASELINE_HEADING), len(kept))
    for j, line in enumerate(kept):
        if used[j]:
            continue
        number = line.split("|")[1].strip() if _ROW_START.match(line) else None
        if number in edited_numbers:
            continue  # the replacement of an edited row: reported once, as the edit
        if _RESERVATION_ROW.match(line) is None:
            problems.append(f"a line that is not a reservation row was added: {line[:100]!r}")
        elif number in base_numbers:
            problems.append(f"an added row duplicates a row of the base: {line[:100]!r}")
        elif j > boundary:
            problems.append(f"a row was added below '{BASELINE_HEADING}': {line[:100]!r}")
    return problems


def merge_base_text(ref: str | None = None) -> tuple[str | None, str]:
    """The reservations file at the merge-base of HEAD with `ref` (default `main`, then
    `origin/main`),
    or `(None, why)` when there is no base to compare with."""
    name = logical(RESERVATIONS_PATH)

    def git(*args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", "-C", str(ROOT), *args], capture_output=True, text=True, check=False
        )

    try:
        git("--version")
    except OSError:
        return None, "git is not available"
    for candidate in [ref] if ref else ["main", "origin/main"]:
        base = git("merge-base", "HEAD", candidate)
        if base.returncode != 0:
            continue
        path = RESERVATIONS_PATH.relative_to(ROOT).as_posix()
        shown = git("show", f"{base.stdout.strip()}:{path}")
        if shown.returncode != 0:
            return None, f"{name} did not exist at the merge-base with {candidate}"
        return shown.stdout, candidate
    return None, "there is no main to take a merge-base with"


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


def against(ref: str | None = None) -> int:
    base, why = merge_base_text(ref)
    if base is None:
        print(f"adr-reservations-check --against: skipped, {why}.")
        return 0
    problems = find_ledger_edits(base, RESERVATIONS_PATH.read_text(encoding="utf-8"))
    if problems:
        print(
            "adr-reservations-check --against: ADR_RESERVATIONS.md changed beyond "
            f"added rows ({why}):"
        )
        for p in problems:
            print(f"  - {p}")
        print(
            "Only rows added in the Reservations table (above '## Baseline') and a "
            "reserved-to-written flip are allowed; the file takes a union merge."
        )
        return 1
    print(
        f"adr-reservations-check --against: only rows added in the table and status flips since {why}."
    )
    return 0


def main(argv: list[str]) -> int:
    if argv[1:2] == ["--against"]:
        return against(argv[2] if len(argv) > 2 else None)
    decisions = DECISIONS_PATH.read_text(encoding="utf-8")
    if argv[1:] == ["--baseline"]:
        print(baseline_table(decisions), end="")
        return 0
    problems = find_unreserved(decisions, RESERVATIONS_PATH.read_text(encoding="utf-8"))
    problems += find_stale_known_duplicates(decisions)
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
