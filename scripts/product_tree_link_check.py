"""`make product-tree-link-check` — a link-integrity gate for the Apache-scoped documentation set.

**Scope, stated precisely because it is narrower than "every citation in this repository," on
purpose.** This checks documentation-to-documentation references only: does an Apache-scoped
document (`scripts/route_coverage_check.py`'s own `APACHE_DOC_PATHS` — the same set, imported
from there rather than redeclared, so the two gates cannot silently diverge on what "product tree"
means) cite, link to, or reference by path a file destined for the private build tree (`spec/`'s
own non-Apache-scoped members — `06_DECISIONS.md`, `07_BUILD_PLAN.md` — and everything destined
for `process/`, plus `CLAUDE.md` and `process/PRODUCT_DELIVERY.md`). It does **not** scan
`packages/`/`services/`/`apps/` source comments for the same pattern — those same files' own ADR
numbers are cited from source docstrings throughout this codebase (392 source files carry 1,150
such citations), and every one of those is a legitimate, currently-resolving
citation from inside the private repository to another file that also stays inside it after
Trigger A (both move into `spec/` together). Flagging those here would not be a bug this gate
exists to catch, and enumerating 1,150 lines into an allowlist would swamp the handful of real
violations this gate is actually for. That broader concern — every citation resolving to a file
that exists, after the physical move — is `scripts/doc_citations_check.py`'s own job, not this
one's; see this module's own docstring, below, for exactly how the two differ.

**Why these are different checks, not one check wearing two names.** `doc_citations_check.py`
asks "does this citation resolve to a file that exists" — true or false depending only on the
filesystem, the same question for every citing file regardless of where it itself lives. This gate
asks "does an Apache-scoped file cite a non-Apache-scoped one" — the answer depends on *which side*
the citing file is on. A `06_DECISIONS.md` docstring citing `07_BUILD_PLAN.md` must keep resolving
(`doc_citations_check.py` must pass it) precisely because both stay inside the private `spec/`
tree together; the identical citation, from `README.md` (Apache-scoped, becomes the published
root `README.md`), must not exist at all (this gate must fail it) precisely because one side of it
never publishes. The two checks have opposite verdicts on structurally identical citations,
depending only on the citing file's own destination — they cannot be merged into one mechanical
rule without either gate silently doing the other's job wrong. A single citation-*extraction*
utility could reasonably be shared between them (parsing "cites path X" out of prose); the
*judgement* applied to what is extracted cannot be.

**Non-vacuous, proven the same way `domain_model_coverage_check.py`/`route_coverage_check.py`
already are**: `tests/test_product_tree_link_check.py::test_the_checker_actually_flags_a_private_
tree_citation` constructs a small fixture file with a deliberate `06_DECISIONS.md` reference and
asserts this module's own `find_violations` reports it — proving the pattern can fail, not only
that it currently passes.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ALLOWLIST_PATH = REPO_ROOT / "tests" / "fixtures" / "product_tree_link_allowlist.txt"

sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "packages"))

from scripts.route_coverage_check import APACHE_DOC_PATHS  # noqa: E402

#: Filenames whose mere appearance in an Apache-scoped document's own prose is the violation —
#: a citation, a path reference, or a bare mention by name. Matched as a filename, not a full
#: path, since these are cited inconsistently (bare name, backtick-quoted, with or without a
#: leading `docs/`) across the existing corpus — checked directly against real examples found
#: while building this gate, not assumed to follow one citation style.
#: **Round 14a (Trigger A).** `docs/` dissolved into `spec/` (product, not private — `06_
#: DECISIONS.md` moved here and is no longer a marker: the ADR log is Apache-scoped spec
#: material, citable like any other numbered file) and `process/` (everything this list used to
#: name individually — `07_BUILD_PLAN.md`, `SESSION_HANDOVER.md`, `NEXT_STEPS_PHASE7.md`,
#: `DESIGN_PROVENANCE.md`, `PRODUCT_DELIVERY.md`, `archive/`, `demo/`, `upstream/` — now share one
#: directory prefix, so one marker replaces eight). `CLAUDE.md`, `.claude/` and `.graphifyignore`
#: are build-process too (owner instruction, 28 Sep: "segregation of the core product files...
#: from the claude based build instructions") and join the list for the same reason they already
#: sit in `.dockerignore`'s own private-tree block.
PRIVATE_TREE_MARKERS: tuple[str, ...] = (
    "process/",
    "CLAUDE.md",
    ".claude/",
    ".graphifyignore",
)

_MARKER_PATTERN = re.compile(
    "|".join(re.escape(m) for m in PRIVATE_TREE_MARKERS)
)


def find_violations(doc_paths: tuple[Path, ...] = APACHE_DOC_PATHS) -> list[tuple[str, int, str]]:
    """Returns `(relative_path, line_number, matched_marker)` for every private-tree reference
    found in every Apache-scoped document. A pure function over the given paths, so the fixture
    test below can call it against a throwaway file instead of this repository's own real docs."""
    violations: list[tuple[str, int, str]] = []
    for doc_path in doc_paths:
        if not doc_path.exists():
            continue
        rel = str(doc_path.relative_to(REPO_ROOT)) if doc_path.is_relative_to(REPO_ROOT) else str(
            doc_path
        )
        for lineno, line in enumerate(doc_path.read_text(encoding="utf-8").splitlines(), start=1):
            match = _MARKER_PATTERN.search(line)
            if match:
                violations.append((rel, lineno, match.group(0)))
    return violations


def _load_allowlist() -> set[tuple[str, str]]:
    """`(relative_path, marker)` pairs already known and accepted — not `(path, line)`, since a
    line number shifts on every unrelated edit and would make the allowlist itself high-churn
    noise, the same reasoning `route_coverage_check.py`'s own allowlist already applies at the
    route-name grain rather than the line-number grain."""
    if not ALLOWLIST_PATH.exists():
        return set()
    pairs: set[tuple[str, str]] = set()
    for line in ALLOWLIST_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        path, _, marker = line.partition("\t")
        pairs.add((path, marker))
    return pairs


def main() -> int:
    violations = find_violations()
    allowlisted = _load_allowlist()
    new_violations = [
        (path, lineno, marker)
        for path, lineno, marker in violations
        if (path, marker) not in allowlisted
    ]
    if new_violations:
        print("product-tree-link-check: new private-tree references found:")
        for path, lineno, marker in new_violations:
            print(f"  {path}:{lineno}: references {marker!r}")
        rel_allowlist = ALLOWLIST_PATH.relative_to(REPO_ROOT)
        print(
            f"\n{len(new_violations)} new violation(s). Either the reference is wrong (an "
            f"Apache-scoped document must not cite a private-tree file), or it is a known, "
            f"already-allowlisted case that needs adding to {rel_allowlist}."
        )
        return 1
    total = len(violations)
    print(
        f"product-tree-link-check: {total} known (allowlisted) reference(s), 0 new. "
        f"Allowlist shrinks to zero as part of Trigger A's own exit criterion."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
