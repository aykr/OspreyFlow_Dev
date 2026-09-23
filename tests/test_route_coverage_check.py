"""The drift gate the documentation-refresh work names:
`scripts/route_coverage_check.py`'s own docstring has the full reasoning, including why paths are
normalised before comparing and why every Apache-scoped doc is checked, not only
`03_CONDUIT_MIDDLEWARE.md`'s table.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from route_coverage_check import (  # noqa: E402
    _read_all_docs,
    find_stale_entries,
    find_undocumented,
    list_doc_routes,
    list_live_routes,
    load_allowlist,
)


def test_no_new_drift_beyond_the_allowlist() -> None:
    live_routes = list_live_routes()
    doc_routes = list_doc_routes(_read_all_docs())
    allowlist = load_allowlist()

    undocumented = find_undocumented(live_routes, doc_routes)
    new_drift = sorted(set(undocumented) - allowlist)

    assert new_drift == [], (
        f"route(s) not documented in any Apache-scoped doc and not in the allowlist: "
        f"{new_drift} — a route was registered in services/api/app.py with no matching "
        "documentation, and no allowlist entry recording it as known debt either."
    )


def test_no_stale_allowlist_entries() -> None:
    live_routes = list_live_routes()
    doc_routes = list_doc_routes(_read_all_docs())
    allowlist = load_allowlist()

    stale = find_stale_entries(live_routes, doc_routes, allowlist)

    assert stale == [], (
        f"stale allowlist entr(ies): {stale} — the route no longer exists, or the docs have "
        "caught up to it; remove them so the allowlist reflects only real, current debt."
    )


def test_the_check_fails_for_a_route_the_doc_does_not_document() -> None:
    """Proves the gate is not vacuous by naming the test that would fail."""
    doc_routes: set[str] = set()

    undocumented = find_undocumented(["GET /v1/totally-fictional-route"], doc_routes)

    assert undocumented == ["GET /v1/totally-fictional-route"]


def test_a_route_documented_in_a_different_apache_doc_does_not_count_as_drift() -> None:
    """The ELSEWHERE fix: `main()` concatenates every Apache-scoped doc's text before calling
    `list_doc_routes`, so a route documented outside `03_CONDUIT_MIDDLEWARE.md`'s table — none
    exists today (`scripts/route_coverage_check.py`'s own docstring found `09_INGEST_STUDIO.md`
    carries zero route mentions), but the mechanism must still work when one does."""
    all_docs_text = "03_CONDUIT_MIDDLEWARE.md has nothing.\nGET /v1/some-route  found elsewhere"

    doc_routes = list_doc_routes(all_docs_text)
    undocumented = find_undocumented(["GET /v1/some-route"], doc_routes)

    assert undocumented == []


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
