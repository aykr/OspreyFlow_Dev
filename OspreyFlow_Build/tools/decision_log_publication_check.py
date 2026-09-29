"""`make decision-log-publication-check` — a link-integrity gate over `06_DECISIONS.md` itself,
one level down from `tools/product_tree_link_check.py`.

**Scope, stated precisely.** `06_DECISIONS.md` ADR-034 §B10 accepts a filtered decision log: the
PRODUCT-classified ADRs publish with the product tree; the PROCESS-classified ones
(`PROCESS_ADR_NUMBERS` below) stay private. That filter is only sound if it holds together — a
published, PRODUCT ADR must never depend on a private, PROCESS one, the same "an Apache-scoped
thing must not cite a non-Apache-scoped one" shape `product_tree_link_check.py` already enforces
for documents, applied here at the ADR grain inside a single document. This gate checks exactly
that: for every ADR section in `06_DECISIONS.md` not in `PROCESS_ADR_NUMBERS`, does its own text
cite an ADR number that *is* in that set.

**Why a new script rather than an extension of `product_tree_link_check.py`.** That gate's own
unit is "does file X cite marker Y"; this gate's unit is "does ADR section X, within one file,
cite ADR number Y" — a different extraction (splitting one document into sections) over a
different population (ADR numbers, not filenames). The two scripts share no logic today (matching
this repository's own precedent: `schemas_check.py` and `licence_check.py` share a *shape* — a
small, standalone, `make`-invoked gate — not an implementation), so this one is not built as an
extension of either.

**Zero violations today** (checked directly when this gate was written) — cost stated in
`06_DECISIONS.md` ADR-034 §B10: nothing enforced that until this gate existed.

**Non-vacuous, proven the same way**: `tests/test_decision_log_publication_check.py::
test_the_checker_actually_flags_a_product_adr_citing_a_process_adr` builds a small fixture
decision log with a deliberate PRODUCT-cites-PROCESS reference and asserts this module's own
`find_violations` reports it.
"""

from __future__ import annotations

import re
from pathlib import Path

from tools.layout import REPO as REPO_ROOT
from tools.layout import rel

DECISIONS_PATH = REPO_ROOT / "spec" / "06_DECISIONS.md"
ALLOWLIST_PATH = REPO_ROOT / "tests" / "fixtures" / "decision_log_publication_allowlist.txt"

#: `06_DECISIONS.md` ADR-034 §B10's own classification rule: PROCESS is a decision about how this
#: build was scoped, phased, released or published — the project's own management, not the
#: product's behaviour. Every other accepted ADR is PRODUCT. A new ADR is classified the same way,
#: not defaulted to either bucket — the rule travels with the ADR, not a number range.
#:
#: **This set is hand-maintained, and that is the one step writing a new PROCESS ADR requires.**
#: Its failure mode on omission is the safe direction — the gate fires, naming the new record's own
#: citations as violations — which is how `049` was caught the moment it was written (24 September
#: 2026) rather than published misclassified. Recorded here so the next author reads that failure as
#: "add my number" rather than as a defect in their own citations.
PROCESS_ADR_NUMBERS: frozenset[str] = frozenset(
    {
        "012",
        "019",
        "022",
        "026",
        "027",
        "031",
        "034",
        "042",
        # ADR-049 (the harness/packaging pipeline; Phase 8 stage 2's sub-stages 2b-2h) divides a
        # phase into sub-stages, sets their exit tests and concerns release packaging — "a decision
        # about how this build was scoped, phased, released or published," ADR-034 §B10's own rule,
        # not the product's behaviour. Added 24 September 2026, the day the record was written.
        "049",
    }
)

_HEADING_PATTERN = re.compile(r"^## ADR-(\d{3})", re.MULTILINE)
_ADR_REF_PATTERN = re.compile(r"ADR-(\d{3})")


def _sections(text: str) -> dict[str, str]:
    """Splits `06_DECISIONS.md` into `{adr_number: section_body}` by its own `## ADR-NNN`
    headings — a pure string operation so the fixture test below can call it against a throwaway
    document instead of this repository's own real decision log."""
    headings = list(_HEADING_PATTERN.finditer(text))
    sections: dict[str, str] = {}
    for i, m in enumerate(headings):
        start = m.end()
        end = headings[i + 1].start() if i + 1 < len(headings) else len(text)
        sections[m.group(1)] = text[start:end]
    return sections


def find_violations(decisions_path: Path = DECISIONS_PATH) -> list[tuple[str, str]]:
    """Returns `(product_adr, process_adr)` pairs for every PRODUCT-classified ADR section that
    cites a PROCESS-classified one by number."""
    if not decisions_path.exists():
        return []
    text = decisions_path.read_text(encoding="utf-8")
    violations: list[tuple[str, str]] = []
    for number, body in _sections(text).items():
        if number in PROCESS_ADR_NUMBERS:
            continue
        refs = {m.group(1) for m in _ADR_REF_PATTERN.finditer(body)}
        for ref in sorted(refs):
            if ref in PROCESS_ADR_NUMBERS and ref != number:
                violations.append((number, ref))
    return violations


def _load_allowlist() -> set[tuple[str, str]]:
    """`(product_adr, process_adr)` pairs already known and accepted, the same "known debt
    enumerated, new debt fails immediately" shape `product_tree_link_check.py`'s own allowlist
    already applies."""
    if not ALLOWLIST_PATH.exists():
        return set()
    pairs: set[tuple[str, str]] = set()
    for line in ALLOWLIST_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        a, _, b = line.partition("\t")
        pairs.add((a, b))
    return pairs


def main() -> int:
    violations = find_violations()
    allowlisted = _load_allowlist()
    new_violations = [v for v in violations if v not in allowlisted]
    if new_violations:
        print("decision-log-publication-check: new PRODUCT ADRs citing a PROCESS ADR:")
        for product_adr, process_adr in new_violations:
            print(f"  ADR-{product_adr} cites ADR-{process_adr} (private, not published)")
        allowlist_name = rel(ALLOWLIST_PATH, REPO_ROOT)
        print(
            f"\n{len(new_violations)} new violation(s). Either the citation is wrong (a published "
            f"ADR must not depend on a private one), or it is a known, already-allowlisted case "
            f"that needs adding to {allowlist_name}."
        )
        return 1
    total = len(violations)
    print(
        f"decision-log-publication-check: {total} known (allowlisted) reference(s), 0 new. "
        f"Allowlist shrinks to zero as the decision log's own prose is edited to state each "
        f"constraint without the private pointer."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
