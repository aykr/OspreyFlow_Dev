"""A drift gate for the domain model's own documentation coverage — `07_BUILD_PLAN.md`'s Phase 8
documentation-refresh entry. Same weak, presence-based check `scripts/demo_guide_check.py` already
established (a class is "documented" if its own name appears somewhere in the text, not a
line-level cross-reference), paired with an explicit allowlist of currently-undocumented classes.

**Triaged, not just allowlisted — Part 1 of the session that added this triage.** Every class in
`packages/schemas/domain.py` was classified into exactly one of three buckets before this file's
current shape was written: `GAP` (genuinely undocumented anywhere — stays on the allowlist),
`ELSEWHERE` (correctly documented in a *different* Apache-scoped document — the gate's own search
scope was the bug, not the documentation; fixed below by `find_undocumented` checking every
Apache-scoped doc, not only `01_DOMAIN_MODEL.md`) and `NOT_SCOPED` (not a domain entity at all by
the rule below — never belongs on an allowlist, since no amount of future documentation would
remove it from `domain.py`'s own class list). Mixing the three in one allowlist was the original
defect: a list that can never shrink to its own genuine size teaches nobody to trust "empty" as
"done."

**The domain-entity rule (`is_not_scoped`), stated so it can be tested, not asserted by eye:**

1. A `StrEnum` is NOT_SCOPED. It is a closed vocabulary a field takes one value from
   (`PoleClass`, `PropertyType`, `ProvenanceState`, `AlertMode`) — its own *meaning* belongs in the
   prose of whichever entity's field it types (and, checked directly for all four current
   instances, already is documented there), but the enum itself is not a shaped record with its
   own identity the way `Node`/`Hotlist`/`Alert` are. A gate built to find undocumented *entities*
   should not flag a value type.
2. A class named `<X>Write` whose own docstring identifies it as the pre-persistence counterpart of
   an already-in-scope class `<X>` is NOT_SCOPED (`NodeWrite`/`EdgeWrite`, both confirmed by
   reading their own docstrings: "Pre-persistence `Node`"/"the same as `NodeWrite`"). The domain
   shape is `<X>` itself; the write variant is a request payload carrying the same fields shorn of
   what the Conduit assigns, not a second domain concept needing separate documentation.

Every class in `domain.py` that is neither is a domain entity in scope for this gate, full stop —
no third, judgement-based exclusion.

**Multi-document search — the ELSEWHERE fix.** `find_undocumented` checks every Apache-scoped
document (`06_DECISIONS.md` ADR-034 §B2's own list), not only `01_DOMAIN_MODEL.md` — a class
belonging to the domain model conceptually can be correctly documented in `00_ARCHITECTURE.md`
(the `GraphPort` protocol listing names `OntologySchema`/`SchemaReport` directly) or
`08_ACCEPTANCE_SCENARIOS.md` (`Hotlist`/`Alert` both appear by name in Scenario B's own rows).
**Disclosed, not silently accepted as precise:** this inherits the same weak, presence-only
imprecision as every gate in this family — a class name appearing anywhere in another doc's text
counts as "documented" even where the mention is a type reference in a signature rather than a
description of the class's own shape (`OntologySchema`/`SchemaReport` in `00_ARCHITECTURE.md` are
exactly this case). Narrower than that would need per-class judgement this mechanical gate does not
make.

**The allowlist (`tests/fixtures/domain_model_coverage_allowlist.txt`) now holds only `GAP`
entries** — six, at the time this triage ran, down from the original 16 that mixed all three
categories. Complete for this axis when it is empty and this file is deleted.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DOMAIN_MODULE_PATH = REPO_ROOT / "packages" / "schemas" / "domain.py"
ALLOWLIST_PATH = REPO_ROOT / "tests" / "fixtures" / "domain_model_coverage_allowlist.txt"

#: `06_DECISIONS.md` ADR-034 §B2's own Apache-scoped list, current (pre-Trigger-A) paths.
APACHE_DOC_PATHS: tuple[Path, ...] = tuple(
    REPO_ROOT / "docs" / name
    for name in (
        "00_ARCHITECTURE.md",
        "01_DOMAIN_MODEL.md",
        "02_GLASS_FRONTEND.md",
        "03_CONDUIT_MIDDLEWARE.md",
        "04_VAULT_BACKEND.md",
        "05_DEPLOYMENT.md",
        "08_ACCEPTANCE_SCENARIOS.md",
        "09_INGEST_STUDIO.md",
        "DEMO_GUIDE.md",
        "README.md",
    )
)

#: `<X>Write` classes confirmed, by reading their own docstrings, to be the pre-persistence
#: counterpart of an already-documented class — rule 2 above. Not derived automatically from a
#: naming pattern alone (a future `FooWrite` with no such docstring should not silently inherit
#: this exemption) — extend by hand, the same deliberate-not-automatic choice `find_stale_entries`
#: below depends on to keep this list itself honest.
_WRITE_COUNTERPARTS: frozenset[str] = frozenset({"NodeWrite", "EdgeWrite"})


class _ClassInfo(ast.ClassDef):
    """Type-only alias for readability; `ast.ClassDef` itself carries `.bases`."""


def list_domain_classes(source: str) -> list[tuple[str, list[str]]]:
    """Every module-level class in `domain.py`, paired with its own base-class names (as written
    in the source, e.g. `["StrEnum"]` or `["BaseModel"]`) — `is_not_scoped` needs the base to apply
    rule 1."""
    tree = ast.parse(source)
    classes = []
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.ClassDef):
            bases = [b.id for b in node.bases if isinstance(b, ast.Name)]
            classes.append((node.name, bases))
    return classes


def is_not_scoped(name: str, bases: list[str]) -> bool:
    """Rule 1 and rule 2 above, applied mechanically."""
    if "StrEnum" in bases:
        return True
    return name in _WRITE_COUNTERPARTS


def load_allowlist(path: Path = ALLOWLIST_PATH) -> set[str]:
    if not path.exists():
        return set()
    entries = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            entries.add(stripped)
    return entries


def _read_all_docs(doc_paths: tuple[Path, ...] = APACHE_DOC_PATHS) -> str:
    return "\n".join(p.read_text(encoding="utf-8") for p in doc_paths if p.exists())


def find_undocumented(all_docs_text: str, classes: list[tuple[str, list[str]]]) -> list[str]:
    """Every in-scope (not `is_not_scoped`) class name absent from `all_docs_text` — the full
    undocumented set, before the allowlist is subtracted."""
    return [
        name
        for name, bases in classes
        if not is_not_scoped(name, bases) and name not in all_docs_text
    ]


def find_stale_entries(
    all_docs_text: str, classes: list[tuple[str, list[str]]], allowlist: set[str]
) -> list[str]:
    """An allowlist entry is stale if the class it names no longer exists, is now NOT_SCOPED under
    the rule above, or the docs have caught up to it — any of these must be removed by hand."""
    class_map = dict(classes)
    undocumented = set(find_undocumented(all_docs_text, classes))
    stale = []
    for entry in allowlist:
        if entry not in class_map:
            stale.append(entry)
        elif is_not_scoped(entry, class_map[entry]):
            stale.append(entry)
        elif entry not in undocumented:
            stale.append(entry)
    return sorted(stale)


def main() -> int:
    classes = list_domain_classes(DOMAIN_MODULE_PATH.read_text(encoding="utf-8"))
    all_docs_text = _read_all_docs()
    allowlist = load_allowlist()
    undocumented = find_undocumented(all_docs_text, classes)
    new_drift = sorted(set(undocumented) - allowlist)
    stale = find_stale_entries(all_docs_text, classes, allowlist)

    ok = True
    if new_drift:
        ok = False
        print(
            "domain-model-coverage-check: in-scope class(es) in domain.py not documented in any "
            f"Apache-scoped doc and not in the allowlist: {', '.join(new_drift)}",
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
