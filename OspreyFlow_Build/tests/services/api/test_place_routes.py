"""The three places (`06_DECISIONS.md` ADR-145 decisions 1 and N6): the switcher shows a person
only the places their rights open, and **each hidden place's routes refuse that person** (rule 3:
hiding a place is never the control).

The places and the rights that open each are one table, `apps/workspace/src/shell/places.json`,
which the Glass's switcher and Home read. This file assigns every Conduit route to the place whose
screens call it (`PLACE_RULES`, written here as the test's own data, as `test_route_rights.py` keeps
its table), and proves three things:

1. each place's rights in `places.json` are exactly the rights its own routes need, so a place is
   offered to whoever some route of it would answer, and to nobody else;
2. a route of the Studio or Admin with no right is a named reference catalogue, never an omission;
3. for each built-in role and the *Super user* preset, every route of each place hidden from it
   refuses it over HTTP with `403 right_required` (red with any one route's `require_right`
   removed: shown red on 7 November 2026 for `invite_person_route` and
   `list_studio_recipe_drafts`).

Routes two places call are named with both. The owner's ruling of 7 November 2026 (L2.2, "narrow
those rights") moves three crossings out of the role bundles and one route's right; until the
owning lanes land them they are strict `xfail`s below (`AWAITING_*`), which turn red the day the
change lands, so this file is updated with it.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from schemas.domain import Principal
from schemas.rights import ROLE_RIGHTS, Right, rights_for

PLACES_JSON = (
    Path(__file__).resolve().parents[4] / "OspreyFlow_Core/apps/workspace/src/shell/places.json"
)

# (path pattern, the places whose screens call it, which screen). First match wins.
PLACE_RULES: list[tuple[str, frozenset[str], str]] = [
    (r"^/v1/admin/screening-lists", frozenset({"glass"}), "Monitoring › Lists (alerts/api.ts)"),
    (r"^/v1/admin/", frozenset({"admin"}), "the Admin place"),
    (r"^/v1/ingest/schedule-preview$", frozenset({"ingest", "admin"}),
     "the Studio's schedule editor, and Admin › Schedules through the same editor"),
    (r"/ingest/recipes/\{recipe_id\}/held-rows/release$", frozenset({"glass"}),
     "Monitoring's held rows (alerts/api.ts)"),
    (r"/ingest/(extract|candidates)", frozenset({"glass"}),
     "extraction of a case's files, an investigation right (ADR-112 I4)"),
    (r"/ingest/|^/v1/ingest/|^/v1/datasets/\{dataset_id\}/(sources|source-files)",
     frozenset({"ingest"}), "the Ingest Studio"),
    (r"", frozenset({"glass"}), "the Glass"),
]  # fmt: skip

#: Routes of the Studio or Admin that any signed-in person may call: reference catalogues, the same
#: decision `test_route_rights.py` records as `None`.
ANY_SIGNED_IN = frozenset({"list_connectors", "list_domain_packs", "list_transforms"})

#: The owner's ruling of 7 November 2026, not yet landed by the lanes that own it.
AWAITING_ROUTE = {
    # Lane 1: the pipeline-run history is the Studio's alone, so it needs a pipeline right.
    "recipe_runs_route": (
        "Lane 1: GET .../ingest/recipes/{id}/runs needs a pipeline right, not read_data_feeds"
    ),
}
AWAITING_ROLE = {
    # ADR-112 amendment (packages/schemas/rights.py, the orchestrator): adding files to the ingest
    # folder is the Studio's, and the canvas's Add files is `extract_files`.
    "analyst": "ADR-112 amendment: the Analyst loses add_ingest_files (D6)",
    # Admin › Schedules uses operate_schedules; the Studio's schedule routes are the Studio's.
    "osprey-admin": "ADR-112 amendment: the Admin loses schedule_pipelines (D5)",
}

#: What each role is offered once the ruling has landed (ADR-145 decision 7 lists the places).
EXPECTED_PLACES = {
    "analyst": ["glass"],
    "data_engineer": ["glass", "ingest", "admin"],
    "osprey-admin": ["glass", "admin"],
    "reports_viewer": ["glass"],
    "super": ["glass", "ingest", "admin"],
}
ROLES = {**ROLE_RIGHTS, "super": ROLE_RIGHTS["analyst"] | ROLE_RIGHTS["data_engineer"]}
TOKEN_ROLES = {"super": ["analyst", "data_engineer"]}


def _places() -> dict[str, frozenset[str]]:
    table = json.loads(PLACES_JSON.read_text())
    return {place["id"]: frozenset(place["rights"]) for place in table["places"]}


def shown(held: frozenset[Right], places: dict[str, frozenset[str]]) -> list[str]:
    """The switcher's rule, as `shell/places.ts` applies it."""
    values = {r.value for r in held}
    return [place for place, rights in places.items() if rights & values]


def places_of(path: str) -> frozenset[str]:
    for pattern, places, _ in PLACE_RULES:
        if re.search(pattern, path):
            return places
    raise AssertionError(path)  # the last rule matches everything


def _routes() -> list[APIRoute]:
    from services.api.app import app

    return [r for r in app.routes if isinstance(r, APIRoute)]


def _declared(route: APIRoute) -> str | None:
    for dependency in route.dependant.dependencies:
        right = getattr(dependency.call, "required_right", None)
        if right is not None:
            return str(right)
    return None


def test_every_rule_places_at_least_one_route() -> None:
    """A rule that matches nothing is a place assignment stated and exercised by nothing
    (rule 12)."""
    paths = [r.path for r in _routes()]
    for pattern, _, screen in PLACE_RULES[:-1]:
        assert any(re.search(pattern, p) for p in paths), (pattern, screen)


def test_each_place_opens_with_exactly_the_rights_its_own_routes_need() -> None:
    places = _places()
    needed: dict[str, set[str]] = {place: set() for place in places}
    for route in _routes():
        right = _declared(route)
        if right is None or route.endpoint.__name__ in AWAITING_ROUTE:
            continue
        for place in places_of(route.path):
            needed[place].add(right)
    # A shared route's right may open either of its places; a place's own rights are those of the
    # routes that are its alone, plus any shared one it names.
    alone: dict[str, set[str]] = {place: set() for place in places}
    for route in _routes():
        right, where = _declared(route), places_of(route.path)
        if right and len(where) == 1 and route.endpoint.__name__ not in AWAITING_ROUTE:
            alone[next(iter(where))].add(right)
    for place, rights in places.items():
        assert alone[place] <= rights, (place, sorted(alone[place] - rights))
        assert rights <= needed[place], (place, "opens with a right none of its routes needs",
                                         sorted(rights - needed[place]))  # fmt: skip


def test_a_studio_or_admin_route_with_no_right_is_a_named_catalogue() -> None:
    """Red with a route's `require_right` removed: the route would answer anyone, so a person the
    place is hidden from could still call it."""
    loose = [
        (r.endpoint.__name__, r.path)
        for r in _routes()
        if _declared(r) is None
        and places_of(r.path) & {"ingest", "admin"}
        and r.endpoint.__name__ not in ANY_SIGNED_IN
    ]
    assert loose == []


@pytest.mark.parametrize("name", sorted(AWAITING_ROUTE))
@pytest.mark.xfail(strict=True, reason="the owner's ruling of 7 November 2026, awaiting its lane")
def test_an_awaited_route_needs_a_right_of_its_own_place(name: str) -> None:
    route = next(r for r in _routes() if r.endpoint.__name__ == name)
    right = _declared(route)
    assert right is not None
    assert any(right in _places()[place] for place in places_of(route.path)), AWAITING_ROUTE[name]


@pytest.mark.parametrize("role", sorted(set(EXPECTED_PLACES) - set(AWAITING_ROLE)))
def test_each_role_is_offered_the_places_adr_145_lists(role: str) -> None:
    assert shown(ROLES[role], _places()) == EXPECTED_PLACES[role]


@pytest.mark.parametrize("role", sorted(AWAITING_ROLE))
@pytest.mark.xfail(strict=True, reason="the owner's ruling of 7 November 2026, awaiting ADR-112")
def test_an_awaited_role_is_offered_the_places_adr_145_lists(role: str) -> None:
    assert shown(ROLES[role], _places()) == EXPECTED_PLACES[role]


def _path(route: APIRoute) -> str:
    path = route.path
    for number in ("{z}", "{x}", "{y}"):
        path = path.replace(number, "0")
    return re.sub(r"\{[a-z_]+(:path)?\}", "x", path)


@pytest.mark.parametrize("role", sorted(ROLES))
def test_every_route_of_a_hidden_place_refuses_the_role(role: str) -> None:
    """Over HTTP, without the stores: the right is checked before anything else a route does
    (`require_right`), so a refusal here needs no case, dataset or store. A route that answers with
    anything but `403 right_required` is a place the switcher hides and the Conduit still opens."""
    from services.api.app import app, get_principal

    places = _places()
    hidden = set(places) - set(shown(ROLES[role], places))
    if role in AWAITING_ROLE:
        # Until ADR-112's amendment lands, the role still holds the crossing right, so the Studio is
        # shown to it: prove the refusal against the places it will be offered instead.
        hidden = set(places) - set(EXPECTED_PLACES[role])
    roles = TOKEN_ROLES.get(role, [role])
    who = Principal(id=f"place-{role}", clearance="SECRET", org_unit="unit-1", roles=roles)
    held = {r.value for r in rights_for(roles)}
    answered: list[tuple[str, str, int]] = []
    checked = 0
    app.dependency_overrides[get_principal] = lambda: who
    # No lifespan: nothing past the right check is reached, and a route that gets past it answers
    # (500, with no stores) rather than raising, so it is reported, not hidden.
    client = TestClient(app, raise_server_exceptions=False)
    for route in _routes():
        where = places_of(route.path)
        if not where <= hidden or route.endpoint.__name__ in ANY_SIGNED_IN:
            continue
        if role in AWAITING_ROLE and _declared(route) in held:
            continue  # the crossing itself, awaited above
        if route.endpoint.__name__ in AWAITING_ROUTE and _declared(route) in held:
            continue
        checked += 1
        method = sorted(route.methods or {"GET"})[0]
        response = client.request(
            method, _path(route), headers={"Authorization": "Bearer x"}, json={}
        )
        refused = response.status_code == 403 and "right_required" in response.text
        if not refused:
            answered.append((route.endpoint.__name__, route.path, response.status_code))
    app.dependency_overrides.pop(get_principal, None)
    assert answered == [], answered
    if hidden:
        assert checked > 0, (role, hidden)
