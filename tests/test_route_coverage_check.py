"""The drift gate `07_BUILD_PLAN.md`'s Phase 8 documentation-refresh entry names:
`scripts/route_coverage_check.py`'s own docstring has the full reasoning, including why paths are
normalised before comparing.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from route_coverage_check import (  # noqa: E402
    DOC_PATH,
    find_stale_entries,
    find_undocumented,
    list_doc_routes,
    list_live_routes,
    load_allowlist,
)


def test_no_new_drift_beyond_the_allowlist() -> None:
    live_routes = list_live_routes()
    doc_routes = list_doc_routes(DOC_PATH.read_text(encoding="utf-8"))
    allowlist = load_allowlist()

    undocumented = find_undocumented(live_routes, doc_routes)
    new_drift = sorted(set(undocumented) - allowlist)

    assert new_drift == [], (
        f"{DOC_PATH.name}'s route table is missing route(s) not in the allowlist: {new_drift} — "
        "a route was registered in services/api/app.py with no matching documentation, and no "
        "allowlist entry recording it as known debt either."
    )


def test_no_stale_allowlist_entries() -> None:
    live_routes = list_live_routes()
    doc_routes = list_doc_routes(DOC_PATH.read_text(encoding="utf-8"))
    allowlist = load_allowlist()

    stale = find_stale_entries(live_routes, doc_routes, allowlist)

    assert stale == [], (
        f"stale allowlist entr(ies): {stale} — the route no longer exists, or the doc has caught "
        "up to it; remove them so the allowlist reflects only real, current debt."
    )


def test_the_check_fails_for_a_route_the_doc_does_not_document() -> None:
    """Proves the gate is not vacuous — `CLAUDE.md` rule 12: name the test that would fail."""
    doc_routes: set[str] = set()

    undocumented = find_undocumented(["GET /v1/totally-fictional-route"], doc_routes)

    assert undocumented == ["GET /v1/totally-fictional-route"]


def test_path_parameter_names_are_normalised_before_comparing() -> None:
    """The doc's own `{id}` and the code's own `{investigation_id}` must match — this is the one
    behaviour the whole gate depends on to avoid drowning in placeholder-naming noise."""
    doc_routes = {"GET /v1/investigations/{id}"}

    undocumented = find_undocumented(["GET /v1/investigations/{investigation_id}"], doc_routes)

    assert undocumented == []


def test_a_route_nested_differently_than_the_doc_shows_it_still_counts_as_undocumented() -> None:
    """Normalisation fixes placeholder *names*, not path *shape* — a route genuinely nested under
    a different prefix than the doc illustrates is real debt, not noise."""
    doc_routes = {"POST /v1/resolution/link"}

    undocumented = find_undocumented(
        ["POST /v1/investigations/{investigation_id}/resolution/link"], doc_routes
    )

    assert undocumented == ["POST /v1/investigations/{investigation_id}/resolution/link"]


def test_an_allowlist_entry_already_documented_is_reported_stale() -> None:
    doc_routes = {"GET /v1/now-documented"}
    live_routes = ["GET /v1/now-documented"]
    allowlist = {"GET /v1/now-documented"}

    stale = find_stale_entries(live_routes, doc_routes, allowlist)

    assert stale == ["GET /v1/now-documented"]
