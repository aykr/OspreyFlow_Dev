"""`make provenance-annotation-check` — no build-calendar coordinate in a published document.

`06_DECISIONS.md` ADR-034 §B9 / `07_BUILD_PLAN.md` Stage 3b: the Apache-scoped specification
(`scripts/route_coverage_check.py`'s own `APACHE_DOC_PATHS` — the same set, imported rather than
redeclared, the same reasoning `product_tree_link_check.py` already gives for sharing it) carries
102 "Phase N"/"Stage N"/"found during"/"found while"/"round N" annotations tying a rule or a
measured fact to this build's own calendar. A rule published without its own reason is a rule the
next reader who finds it inconvenient can repeal — the method is to rewrite each annotation,
keeping the reasoning and dropping only the coordinate, never to delete the sentence outright.
This gate is what confirms that rewrite actually landed everywhere and stays landed: a coordinate
reintroduced later (a fresh "fixed in Phase 9" slipped into a future edit) fails here immediately.

**Scope, matching item 1 exactly, not item 2's.** `06_DECISIONS.md` is deliberately excluded —
its own "Accepted, DATE" status line is the decision log's own record-keeping format, not the
build-history narrative this gate targets, and rewriting an ADR's acceptance date out of its own
status line would be a different, wrong edit. `product_tree_link_check.py` is the gate for
`06_DECISIONS.md`'s own separate problem (citing a private-tree file by name).

**Imprecise on purpose, the same trade-off `product_tree_link_check.py` documents for itself.** A
bare `Phase \\d+`/`Stage \\d+`/`round \\d+` match can be a false positive (a deployment "stage" or a
gameplay "round" unrelated to this build's own phases) — checked directly against this
repository's real prose while this gate was built, not assumed. Real false positives are
allowlisted by `(path, matched_text)` pair, the same grain `product_tree_link_check.py` already
uses, rather than tuning the regex into something more fragile chasing 100% precision.

**Non-vacuous, proven the same way the other allowlist-based gates already are**:
`tests/test_provenance_annotation_check.py::test_the_checker_actually_flags_a_planted_annotation`
plants a real "Phase 3" annotation in a throwaway fixture file and asserts `find_violations`
reports it — proving the pattern can fail, not only that it currently passes.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ALLOWLIST_PATH = REPO_ROOT / "tests" / "fixtures" / "provenance_annotation_allowlist.txt"

sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "packages"))

from scripts.route_coverage_check import APACHE_DOC_PATHS  # noqa: E402

#: The build-calendar vocabulary a provenance annotation is built from, found by reading the real
#: annotations this gate was built to catch, not guessed. Word-bounded so "Stage" inside an
#: unrelated word never matches, and so a real false positive (a UI or protocol "stage"/"round"
#: with a number attached, unrelated to this build's own phases) is rare enough to allowlist by
#: exception rather than a sign the pattern itself is wrong.
#: **Case-insensitive (round 14c)** — a real instance ("Round 09: the two Geospatial-screen
#: actions...") opened a sentence with a capital letter, which the pattern's own then-literal
#: casing missed entirely; checked, not assumed, that `Phase`/`Stage`/`Checkpoint` had the
#: identical gap in the other direction (a lowercase "phase 3 work is not yet scheduled" mid-
#: sentence), so all four use one shared flag rather than a fix scoped to the one instance found.
_PATTERN = re.compile(
    r"\bPhase \d+\w*\b"
    r"|\bStage \d+\w*\b"
    r"|\bCheckpoint \d+\w*\b"
    r"|\bfound during\b"
    r"|\bfound while\b"
    r"|\bround \d+\w*\b",
    re.IGNORECASE,
)


def find_violations(doc_paths: tuple[Path, ...] = APACHE_DOC_PATHS) -> list[tuple[str, int, str]]:
    """Returns `(relative_path, line_number, matched_text)` for every provenance annotation found
    in every Apache-scoped document. A pure function over the given paths, so the fixture test can
    call it against a throwaway file instead of this repository's own real docs."""
    violations: list[tuple[str, int, str]] = []
    for doc_path in doc_paths:
        if not doc_path.exists():
            continue
        rel = str(doc_path.relative_to(REPO_ROOT)) if doc_path.is_relative_to(REPO_ROOT) else str(
            doc_path
        )
        for lineno, line in enumerate(doc_path.read_text(encoding="utf-8").splitlines(), start=1):
            for match in _PATTERN.finditer(line):
                violations.append((rel, lineno, match.group(0)))
    return violations


def _load_allowlist() -> set[tuple[str, str]]:
    """`(relative_path, matched_text)` pairs already known and accepted as false positives — not
    `(path, line)`, since a line number shifts on every unrelated edit, the same reasoning
    `product_tree_link_check.py`'s own allowlist already applies."""
    if not ALLOWLIST_PATH.exists():
        return set()
    pairs: set[tuple[str, str]] = set()
    for line in ALLOWLIST_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        path, _, matched = line.partition("\t")
        pairs.add((path, matched))
    return pairs


def main() -> int:
    violations = find_violations()
    allowlisted = _load_allowlist()
    new_violations = [
        (path, lineno, matched)
        for path, lineno, matched in violations
        if (path, matched) not in allowlisted
    ]
    if new_violations:
        print("provenance-annotation-check: new build-calendar annotation(s) found:")
        for path, lineno, matched in new_violations:
            print(f"  {path}:{lineno}: {matched!r}")
        rel_allowlist = ALLOWLIST_PATH.relative_to(REPO_ROOT)
        print(
            f"\n{len(new_violations)} new annotation(s). Rewrite it (keep the reasoning, drop the "
            f"build-calendar coordinate), or, if it is a real false positive, add it to "
            f"{rel_allowlist}."
        )
        return 1
    total = len(violations)
    print(
        f"provenance-annotation-check: {total} known (allowlisted) false positive(s), 0 new "
        f"build-calendar annotation(s)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
