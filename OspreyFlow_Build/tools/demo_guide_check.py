"""A drift gate for `DEMO_GUIDE.md` §1's own "What you can demo today" table —
`06_DECISIONS.md` ADR-035, part of the documentation-refresh work.

**`DEMO_REGISTRY` below is the guide's feature-level list, kept beside the packaging registry.**
ADR-035's fail-closed `shipped`/`internal` registry now exists (`scripts/demo_registry.py`, with the
demo packs of ADR-114 Amendment 1), but it keys off the packaging grain — which files may leave —
while this list keys off the guide's own rows ("Scenario A", "the Ingest Studio"). Both name the
same demos and are kept in sync by hand; this check fails when a demo is missing from the guide or
carries no distribution class there.

Deliberately weak, not a line-level cross-reference: a registry entry is "documented" if both its
own name and its own distribution class appear anywhere in the guide's text (an entry in
`TABLE_ROW_ENTRIES` must have a table row of its own holding both). Strong enough to catch
the failure this gate exists for (a demo entirely missing from the guide, or documented with no
distribution class at all); not strong enough to catch a distribution class attached to the wrong
demo — the same class of gap `authorized_query_check.py`'s own docstring discloses for its own
heuristic, not silently assumed away here either.
"""

from __future__ import annotations

import sys

from tools.layout import REPO as REPO_ROOT
from tools.layout import rel

DEMO_GUIDE_PATH = REPO_ROOT / "DEMO_GUIDE.md"

#: (name substring as it appears in the guide, distribution class). Sourced from `DEMO_GUIDE.md`
#: §1's own table at the time this module was written — update both together when either changes.
DEMO_REGISTRY: tuple[tuple[str, str], ...] = (
    ("Scenario A, steps A1", "shipped"),
    ("The Ingest Studio", "shipped"),
    ("Scenario B (comms and identity pivot)", "shipped"),
    ("Extraction and entity resolution", "shipped"),
    ('Scenario C — "Fixture Corp"', "shipped"),
    ("Operation Ledger", "shipped"),
    ("Prison Intelligence Dataset", "shipped"),
    ("PaySim", "shipped"),
    ("The real Enron email corpus", "internal"),
    ("VAST Challenge dataset", "internal"),
)

#: Entries held to the stronger rule: the guide must have a table row of its own naming the demo and
#: carrying its class (ADR-127 Amendment 30). The looser rule below passes a demo named in a
#: sentence while some other row holds the class marker, which is how the Prison Intelligence
#: Dataset could have lost its row and still passed.
TABLE_ROW_ENTRIES: frozenset[str] = frozenset({"Prison Intelligence Dataset"})


def _has_table_row(guide_text: str, name: str, marker: str) -> bool:
    """Whether one line of the guide's table (it starts with `|`) holds the name and the marker."""
    return any(
        line.lstrip().startswith("|") and name in line and marker in line
        for line in guide_text.splitlines()
    )


def find_undocumented(
    guide_text: str,
    registry: tuple[tuple[str, str], ...] = DEMO_REGISTRY,
    table_rows: frozenset[str] = TABLE_ROW_ENTRIES,
) -> list[str]:
    """Returns a name for every registry entry missing its own name, or its own distribution
    class marker (`` `shipped` ``/`` `internal` ``), anywhere in `guide_text` — empty when the
    guide is in sync. An entry in `table_rows` must have both in one table row of its own."""
    missing = []
    for name, distribution_class in registry:
        marker = f"`{distribution_class}`"
        if name in table_rows:
            if not _has_table_row(guide_text, name, marker):
                missing.append(name)
        elif name not in guide_text or marker not in guide_text:
            missing.append(name)
    return missing


def main() -> int:
    guide_text = DEMO_GUIDE_PATH.read_text(encoding="utf-8")
    missing = find_undocumented(guide_text)
    if missing:
        print(
            "demo-guide-check: demo(s) registered but not documented with a distribution class "
            f"in {rel(DEMO_GUIDE_PATH, REPO_ROOT)}: {', '.join(missing)}",
            file=sys.stderr,
        )
        return 1
    print(f"demo-guide-check: {len(DEMO_REGISTRY)} registered demo(s), all documented.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
