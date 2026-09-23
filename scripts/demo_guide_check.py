"""A drift gate for `docs/DEMO_GUIDE.md` §1's own "What you can demo today" table —
`06_DECISIONS.md` ADR-035, part of the documentation-refresh work.

**`DEMO_REGISTRY` below is a stand-in, not the real thing, and says so rather than pretending
otherwise.** ADR-035's own fail-closed `shipped`/`internal` registry — the packaging-time gate that
mechanically enforces which demo ships in a built artefact — is still unbuilt, a disclosed
gap. `DEMO_GUIDE.md` §1 already says as much: "Until that
registry exists, treat the column below as the same binding statement in prose that the registry
will enforce mechanically." This module is that same idea taken one small step further — a real,
checkable list, not only prose — so "a new demo was added and the guide wasn't updated" fails a
test today instead of waiting for Phase 8's own registry to exist. When that registry lands, this
list is replaced by a real query against it; the check below (`find_undocumented`) does not need to
change shape, only its data source.

Deliberately weak, not a line-level cross-reference: a registry entry is "documented" if both its
own name and its own distribution class appear anywhere in the guide's text. Strong enough to catch
the failure this gate exists for (a demo entirely missing from the guide, or documented with no
distribution class at all); not strong enough to catch a distribution class attached to the wrong
demo — the same class of gap `authorized_query_check.py`'s own docstring discloses for its own
heuristic, not silently assumed away here either.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEMO_GUIDE_PATH = REPO_ROOT / "docs" / "DEMO_GUIDE.md"

#: (name substring as it appears in the guide, distribution class). Sourced from `DEMO_GUIDE.md`
#: §1's own table at the time this module was written — update both together when either changes.
DEMO_REGISTRY: tuple[tuple[str, str], ...] = (
    ("Scenario A, steps A1", "shipped"),
    ("The Ingest Studio", "shipped"),
    ("Scenario B (comms and identity pivot)", "shipped"),
    ("Extraction and entity resolution", "shipped"),
    ('Scenario C — "Fixture Corp"', "shipped"),
    ("The real Enron email corpus", "internal"),
    ("VAST Challenge dataset", "internal"),
)


def find_undocumented(
    guide_text: str, registry: tuple[tuple[str, str], ...] = DEMO_REGISTRY
) -> list[str]:
    """Returns a name for every registry entry missing its own name, or its own distribution
    class marker (`` `shipped` ``/`` `internal` ``), anywhere in `guide_text` — empty when the
    guide is in sync."""
    missing = []
    for name, distribution_class in registry:
        marker = f"`{distribution_class}`"
        if name not in guide_text or marker not in guide_text:
            missing.append(name)
    return missing


def main() -> int:
    guide_text = DEMO_GUIDE_PATH.read_text(encoding="utf-8")
    missing = find_undocumented(guide_text)
    if missing:
        print(
            "demo-guide-check: demo(s) registered but not documented with a distribution class "
            f"in {DEMO_GUIDE_PATH.relative_to(REPO_ROOT)}: {', '.join(missing)}",
            file=sys.stderr,
        )
        return 1
    print(f"demo-guide-check: {len(DEMO_REGISTRY)} registered demo(s), all documented.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
