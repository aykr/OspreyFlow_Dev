"""A drift gate for the Apache-scoped spec's own route documentation, part of the
documentation-refresh work. Same shape as `scripts/demo_guide_check.py`/`scripts/
domain_model_coverage_check.py`: a real check against a real source (the live FastAPI app, not a
hand-maintained list) paired with an explicit allowlist of routes currently missing from the doc.

**Routes, not classes: `app.routes`, imported live, not parsed by hand.** `services/api/app.py`
registers every route directly on `app` (`grep -c "@app\\."` confirms no `APIRouter`/
`include_router` anywhere else in `services/api`), so importing `services.api.app.app` and reading
its own route table is the authoritative source — no separate list to fall out of sync with the
code the way the doc itself already has.

**Path parameters are normalised (`{anything}` → `{param}`) before comparing, on both sides.** The
doc's own placeholder names (`{id}`, `{cluster}`, `{step}`) don't match the code's own (
`{investigation_id}`, `{cluster_id}`, `{step_id}`) — a literal string match would flag every
parameterised route as missing even where the doc plainly does document it, drowning the real gap
in cosmetic noise. A route genuinely nested differently than the doc shows it (`03_CONDUIT_
MIDDLEWARE.md` illustrates `/v1/resolution/link` as a bare top-level route; `resolution.py`'s own
docstring already discloses it is actually nested under `/v1/investigations/{investigation_id}/`)
still does not normalise to a match — nesting is a real shape difference, not a placeholder-naming
one, so it correctly lands in the allowlist alongside the rest of the debt.

**Checks every Apache-scoped document, not only `spec/03_CONDUIT_MIDDLEWARE.md`'s table — the
gate's own original ELSEWHERE bug, found by the same triage that fixed the domain-model gate.**
`03_CONDUIT_MIDDLEWARE.md`'s own table is the natural home and, checked directly, the *only*
Apache-scoped document that documents a route in this shape — `09_INGEST_STUDIO.md` in particular
was expected to cover the Ingest Studio's own routes and, checked directly
(`grep -c "/v1/" spec/09_INGEST_STUDIO.md` → 0), does not mention a single one, even inline. That
finding did not shrink today's allowlist — every route this gate flags is `GAP`, not `ELSEWHERE`,
since none is documented in a second file today — but the search itself is real, across every
Apache-scoped doc, not hardcoded to one file, so a route documented elsewhere in the future is
recognised without this gate needing a second fix.

**`03_CONDUIT_MIDDLEWARE.md`'s own stale Ingest Studio rows were left in place, not pruned.** The
table's §3.4 still illustrates an abandoned design (`/v1/ingest/upload`, `/v1/ingest/connector/
{name}/run`, `/v1/documents/{id}`) matching no route this app has ever registered under that
shape — not merely undocumented-but-plausible, but describing a interface that was superseded by
the Ingest Studio's own recipe-based routes before this repository's current route surface existed.
Pruning was considered and rejected: the condition for pruning was "genuinely superseded by
`09_INGEST_STUDIO.md`," and the check above found that document carries no replacement route
content at all — removing the stale rows would trade a wrong row for a blank one, not a correct
one, in the one document whose job is exactly this inventory. Left for the Phase 8 refresh, which
writes real content; this gate enforces coverage, not prose quality.

**The allowlist (`tests/fixtures/route_coverage_allowlist.txt`) is the enumerated, countable form of
existing debt, not a permanent exemption list** — same discipline as the domain-model gate. Complete
for this axis when the allowlist is empty and this file is deleted.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ALLOWLIST_PATH = REPO_ROOT / "tests" / "fixtures" / "route_coverage_allowlist.txt"

#: The Apache-scoped document list, current (pre-Trigger-A) paths — the
#: same set `scripts/domain_model_coverage_check.py`'s own `APACHE_DOC_PATHS` uses.
#: **Round 14a (Trigger A):** `docs/` dissolved into `spec/` and the repository root — a physical
#: move only. `06_DECISIONS.md` moved to `spec/` too (it is product spec, not build-process,
#: `07_BUILD_PLAN.md` is the one numbered file that went the other way) but is **not** added to
#: this set here: hundreds of its own historical entries cite `CLAUDE.md` and process-tree paths
#: by rule number as part of the ADR record's own narrative, and rephrasing or allowlisting each
#: one is `process/07_BUILD_PLAN.md`'s own Stage 3b scoped work, not this restructure's. Bringing
#: `06_DECISIONS.md` into the scanned set is that later round's decision to make, not a side
#: effect of moving files.
APACHE_DOC_PATHS: tuple[Path, ...] = tuple(
    REPO_ROOT / "spec" / name
    for name in (
        "00_ARCHITECTURE.md",
        "01_DOMAIN_MODEL.md",
        "02_GLASS_FRONTEND.md",
        "03_CONDUIT_MIDDLEWARE.md",
        "04_VAULT_BACKEND.md",
        "05_DEPLOYMENT.md",
        "08_ACCEPTANCE_SCENARIOS.md",
        "09_INGEST_STUDIO.md",
    )
) + (REPO_ROOT / "DEMO_GUIDE.md", REPO_ROOT / "README.md")

#: `03_CONDUIT_MIDDLEWARE.md`'s own route table is the primary reference cited in messages below —
#: kept as a named constant since it is still, in practice, the only document this gate ever finds
#: a route in.
DOC_PATH = REPO_ROOT / "spec" / "03_CONDUIT_MIDDLEWARE.md"

# Run standalone via `python scripts/route_coverage_check.py` (as `make route-coverage-check`
# does), not only under pytest's own `pythonpath = ["packages"]` — both the repo root (for
# `services.*`) and `packages/` (for `services.api.app`'s own `from schemas...` imports) need to
# be on `sys.path` before the import inside `list_live_routes()` below runs.
for _path in (str(REPO_ROOT), str(REPO_ROOT / "packages")):
    if _path not in sys.path:
        sys.path.insert(0, _path)

_PARAM = re.compile(r"\{[^}]+\}")
_DOC_ROUTE_LINE = re.compile(r"^(GET|POST|PUT|PATCH|DELETE)\s+(\S+)", re.MULTILINE)


def normalize_path(path: str) -> str:
    return _PARAM.sub("{param}", path)


def list_live_routes() -> list[str]:
    """`METHOD path` strings for every route FastAPI has actually registered — imported live
    rather than statically parsed, so a route added through any future indirection (a router, a
    decorator factory) is still caught."""
    from fastapi.routing import APIRoute
    from services.api.app import app

    routes = []
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        for method in sorted((route.methods or set()) - {"HEAD", "OPTIONS"}):
            routes.append(f"{method} {route.path}")
    return sorted(set(routes))


def list_doc_routes(doc_text: str) -> set[str]:
    """Route lines from one document's text. `main()`/the tests concatenate every Apache-scoped
    doc's text before calling this, so a route documented in any of them is found."""
    return {f"{m} {p}" for m, p in _DOC_ROUTE_LINE.findall(doc_text)}


def _read_all_docs(doc_paths: tuple[Path, ...] = APACHE_DOC_PATHS) -> str:
    return "\n".join(p.read_text(encoding="utf-8") for p in doc_paths if p.exists())


def load_allowlist(path: Path = ALLOWLIST_PATH) -> set[str]:
    if not path.exists():
        return set()
    entries = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            entries.add(stripped)
    return entries


def _normalize_route(route: str) -> str:
    method, path = route.split(" ", 1)
    return f"{method} {normalize_path(path)}"


def find_undocumented(live_routes: list[str], doc_routes: set[str]) -> list[str]:
    """Every live route whose normalised `METHOD path` has no match among the doc route set's
    own normalised routes — the full undocumented set, before the allowlist is subtracted. Pass
    `list_doc_routes` of every Apache-scoped doc's text concatenated to check all of them at
    once."""
    doc_normalized = {_normalize_route(route) for route in doc_routes}
    return [route for route in live_routes if _normalize_route(route) not in doc_normalized]


def find_stale_entries(
    live_routes: list[str], doc_routes: set[str], allowlist: set[str]
) -> list[str]:
    """An allowlist entry is stale if the route it names no longer exists at all, or the docs have
    caught up to it — either way it must be removed by hand."""
    live_set = set(live_routes)
    undocumented = set(find_undocumented(live_routes, doc_routes))
    return sorted(
        entry for entry in allowlist if entry not in live_set or entry not in undocumented
    )


def main() -> int:
    live_routes = list_live_routes()
    doc_routes = list_doc_routes(_read_all_docs())
    allowlist = load_allowlist()
    undocumented = find_undocumented(live_routes, doc_routes)
    new_drift = sorted(set(undocumented) - allowlist)
    stale = find_stale_entries(live_routes, doc_routes, allowlist)

    ok = True
    if new_drift:
        ok = False
        print(
            "route-coverage-check: route(s) registered in services/api/app.py not documented in "
            f"any Apache-scoped doc and not in the allowlist: {', '.join(new_drift)}",
            file=sys.stderr,
        )
    if stale:
        ok = False
        print(
            f"route-coverage-check: stale allowlist entr(ies) in "
            f"{ALLOWLIST_PATH.relative_to(REPO_ROOT)} — remove: {', '.join(stale)}",
            file=sys.stderr,
        )
    if ok:
        print(
            f"route-coverage-check: {len(live_routes)} route(s), "
            f"{len(allowlist)} allowlisted, no new drift."
        )
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
