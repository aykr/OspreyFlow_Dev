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

**The ELSEWHERE bar, and why the search is single-document again after a first attempt got it
wrong.** A first version of this gate counted a class as `ELSEWHERE` if its name appeared *anywhere*
in *any* Apache-scoped document, and moved four classes there on that basis. Wrong bar: `ELSEWHERE`
requires the named document to **define** the entity — its fields, its identity, its lifecycle, its
access semantics — not merely mention its name. Re-examined against that bar, all four failed it:
`OntologySchema`/`SchemaReport` appeared only inside a `GraphPort` protocol *signature* in
`00_ARCHITECTURE.md` (`async def apply_schema(self, schema: OntologySchema) -> SchemaReport: ...`)
— a type reference, not a definition; `Hotlist`/`Alert` appeared only in
`08_ACCEPTANCE_SCENARIOS.md` rows describing an analyst's own action ("Add the endpoint to a
hotlist", "Alert workflow") — a scenario step, not a domain-model entry. **The tell that the
multi-document search itself was the defect, not the four classes:** `Monitor` — introduced by the
identical stage, against the identical specification, as `Hotlist`/`Alert` — never appeared in any
second document at all and so stayed correctly on `GAP`; a search that placed its two siblings in a
different bucket for having merely been *named* somewhere was measuring document-wide word
frequency, not documentation.

**The bar, written into the rule rather than left to judgement:** `find_undocumented` checks only
`01_DOMAIN_MODEL.md` — the one Apache-scoped document CLAUDE.md's own routing table assigns to
"anything touching entities, edges, provenance, handling, resolution," and, checked empirically
across this whole exercise, the *only* document that ever actually defines one. No class was found,
in this triage, genuinely defined in a second document; a future one that genuinely is would need a
deliberate, named exception here, not a blanket "any mention counts" search reinstated to catch a
one-off. (`scripts/route_coverage_check.py`'s own multi-document search is not this same mistake —
a route's own documented shape is a `METHOD /path` line, which cannot appear "incidentally" the way
a bare class name can; a match there is definitional by construction, not merely a name mention.)

**The allowlist (`tests/fixtures/domain_model_coverage_allowlist.txt`) now holds only `GAP`
entries** — ten, after this correction (six unchanged, plus `Hotlist`/`Alert`/`OntologySchema`/
`SchemaReport` moved back from the mistaken `ELSEWHERE` classification), down from the original 16
that mixed all three categories. Complete for this axis when it is empty and this file is deleted.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DOMAIN_MODULE_PATH = REPO_ROOT / "packages" / "schemas" / "domain.py"
DOC_PATH = REPO_ROOT / "docs" / "01_DOMAIN_MODEL.md"
ALLOWLIST_PATH = REPO_ROOT / "tests" / "fixtures" / "domain_model_coverage_allowlist.txt"

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


#: A bare protocol/interface stub line — `async def apply_schema(self, schema: OntologySchema) ->
#: SchemaReport: ...`, `00_ARCHITECTURE.md`'s own actual shape — carries a type *reference*, not a
#: *definition*. A class mentioned only on lines matching this is not documented; the same class
#: mentioned on any other line (prose, a table row, a full `class X(BaseModel): ...` field listing
#: such as `01_DOMAIN_MODEL.md` §8's own `ExpandRequest`/`PathRequest`) is.
_STUB_SIGNATURE_LINE = re.compile(r"^\s*(async\s+)?def\s+\w+\(.*\)\s*(->\s*\S+)?\s*:\s*\.\.\.\s*$")


def _mentioned_only_in_stub_signatures(name: str, doc_text: str) -> bool:
    lines_with_name = [line for line in doc_text.splitlines() if name in line]
    if not lines_with_name:
        return False
    return all(_STUB_SIGNATURE_LINE.match(line) for line in lines_with_name)


def find_undocumented(doc_text: str, classes: list[tuple[str, list[str]]]) -> list[str]:
    """Every in-scope (not `is_not_scoped`) class name absent from `doc_text`, or present only on
    bare protocol-stub lines (the ELSEWHERE bar's "a type in a protocol signature is not a
    domain-model entry", applied within this one document too, not only across documents) — the
    full undocumented set, before the allowlist is subtracted. `doc_text` is `01_DOMAIN_MODEL.md`'s
    own text — see this module's own docstring for why the search is single-document, not every
    Apache-scoped doc."""
    return [
        name
        for name, bases in classes
        if not is_not_scoped(name, bases)
        and (name not in doc_text or _mentioned_only_in_stub_signatures(name, doc_text))
    ]


def find_stale_entries(
    doc_text: str, classes: list[tuple[str, list[str]]], allowlist: set[str]
) -> list[str]:
    """An allowlist entry is stale if the class it names no longer exists, is now NOT_SCOPED under
    the rule above, or the doc has caught up to it — any of these must be removed by hand."""
    class_map = dict(classes)
    undocumented = set(find_undocumented(doc_text, classes))
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
    doc_text = DOC_PATH.read_text(encoding="utf-8")
    allowlist = load_allowlist()
    undocumented = find_undocumented(doc_text, classes)
    new_drift = sorted(set(undocumented) - allowlist)
    stale = find_stale_entries(doc_text, classes, allowlist)

    ok = True
    if new_drift:
        ok = False
        print(
            f"domain-model-coverage-check: in-scope class(es) in domain.py not documented in "
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
