"""A drift gate for `docs/03_CONDUIT_MIDDLEWARE.md`'s own route table — `07_BUILD_PLAN.md`'s
Phase 8 documentation-refresh entry. Same shape as `scripts/demo_guide_check.py`/`scripts/
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

**The allowlist (`tests/fixtures/route_coverage_allowlist.txt`) is the enumerated, countable form of
existing debt, not a permanent exemption list** — same discipline as the domain-model gate. Complete
for this axis when the allowlist is empty and this file is deleted.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DOC_PATH = REPO_ROOT / "docs" / "03_CONDUIT_MIDDLEWARE.md"
ALLOWLIST_PATH = REPO_ROOT / "tests" / "fixtures" / "route_coverage_allowlist.txt"

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
    return {f"{m} {p}" for m, p in _DOC_ROUTE_LINE.findall(doc_text)}


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
    """Every live route whose normalised `METHOD path` has no match among the doc's own
    normalised routes — the full undocumented set, before the allowlist is subtracted."""
    doc_normalized = {_normalize_route(route) for route in doc_routes}
    return [route for route in live_routes if _normalize_route(route) not in doc_normalized]


def find_stale_entries(
    live_routes: list[str], doc_routes: set[str], allowlist: set[str]
) -> list[str]:
    """An allowlist entry is stale if the route it names no longer exists at all, or the doc has
    caught up to it — either way it must be removed by hand."""
    live_set = set(live_routes)
    undocumented = set(find_undocumented(live_routes, doc_routes))
    return sorted(
        entry for entry in allowlist if entry not in live_set or entry not in undocumented
    )


def main() -> int:
    live_routes = list_live_routes()
    doc_text = DOC_PATH.read_text(encoding="utf-8")
    doc_routes = list_doc_routes(doc_text)
    allowlist = load_allowlist()
    undocumented = find_undocumented(live_routes, doc_routes)
    new_drift = sorted(set(undocumented) - allowlist)
    stale = find_stale_entries(live_routes, doc_routes, allowlist)

    ok = True
    if new_drift:
        ok = False
        print(
            "route-coverage-check: route(s) registered in services/api/app.py not documented in "
            f"{DOC_PATH.relative_to(REPO_ROOT)} and not in the allowlist: {', '.join(new_drift)}",
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
