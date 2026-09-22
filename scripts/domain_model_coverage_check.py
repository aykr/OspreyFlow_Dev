"""A drift gate for `docs/01_DOMAIN_MODEL.md` — `07_BUILD_PLAN.md`'s Phase 8 documentation-refresh
entry. Same shape as `scripts/demo_guide_check.py`: a weak, presence-based check (a class is
"documented" if its own name appears anywhere in the doc's text, not a line-level cross-reference),
paired with an explicit allowlist of currently-undocumented classes rather than a silent pass.

**The allowlist (`tests/fixtures/domain_model_coverage_allowlist.txt`) is the enumerated, countable
form of existing debt, not a permanent exemption list.** A class already in the allowlist stays
silent; a class that drops out of the doc with no allowlist entry — a new class added with no
matching doc update — fails the build immediately. The Phase 8 documentation-refresh step
(`07_BUILD_PLAN.md`) is complete for this axis when the allowlist is empty and this file is
deleted, not when someone judges the doc close enough.

**A stale allowlist entry (a class now documented, or a class no longer in `domain.py` at all)
fails too** — `find_stale_entries` below — so the allowlist can only shrink honestly as the refresh
closes each item, never silently keep an entry the doc has already caught up to.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DOMAIN_MODULE_PATH = REPO_ROOT / "packages" / "schemas" / "domain.py"
DOC_PATH = REPO_ROOT / "docs" / "01_DOMAIN_MODEL.md"
ALLOWLIST_PATH = REPO_ROOT / "tests" / "fixtures" / "domain_model_coverage_allowlist.txt"


def list_domain_classes(source: str) -> list[str]:
    """Every module-level class in `domain.py` — `BaseModel`s and `StrEnum`s alike, since both
    are domain-model concepts `01_DOMAIN_MODEL.md`'s own job is to describe, not only the request/
    response shapes."""
    tree = ast.parse(source)
    return [node.name for node in ast.iter_child_nodes(tree) if isinstance(node, ast.ClassDef)]


def load_allowlist(path: Path = ALLOWLIST_PATH) -> set[str]:
    if not path.exists():
        return set()
    entries = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            entries.add(stripped)
    return entries


def find_undocumented(doc_text: str, classes: list[str]) -> list[str]:
    """Every class name absent from `doc_text` — the full undocumented set, before the allowlist
    is subtracted. `main()`/the tests subtract `load_allowlist()` from this to find new drift."""
    return [c for c in classes if c not in doc_text]


def find_stale_entries(doc_text: str, classes: list[str], allowlist: set[str]) -> list[str]:
    """An allowlist entry is stale if the doc has caught up to it (now documented) or if the class
    it names no longer exists in `domain.py` (renamed or removed) — either way it must be removed
    by hand, not left to silently keep exempting nothing."""
    class_set = set(classes)
    undocumented = set(find_undocumented(doc_text, classes))
    return sorted(
        entry for entry in allowlist if entry not in class_set or entry not in undocumented
    )


def main() -> int:
    classes = list_domain_classes(DOMAIN_MODULE_PATH.read_text(encoding="utf-8"))
    doc_text = DOC_PATH.read_text(encoding="utf-8")
    allowlist = load_allowlist()
    undocumented = find_undocumented(doc_text, classes)
    new_drift = sorted(set(undocumented) - allowlist)
    stale = find_stale_entries(doc_text, classes, allowlist)

    ok = True
    if new_drift:
        ok = False
        print(
            "domain-model-coverage-check: class(es) in domain.py not documented in "
            f"{DOC_PATH.relative_to(REPO_ROOT)} and not in the allowlist: {', '.join(new_drift)}",
            file=sys.stderr,
        )
    if stale:
        ok = False
        print(
            f"domain-model-coverage-check: stale allowlist entr(ies) in "
            f"{ALLOWLIST_PATH.relative_to(REPO_ROOT)} — remove: {', '.join(stale)}",
            file=sys.stderr,
        )
    if ok:
        print(
            f"domain-model-coverage-check: {len(classes)} class(es), "
            f"{len(allowlist)} allowlisted, no new drift."
        )
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
