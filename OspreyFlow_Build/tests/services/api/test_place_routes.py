"""The three places (`06_DECISIONS.md` ADR-145 decisions 1 and N6, Amendment 1): the switcher
shows a person only the places their rights open, and **each hidden place's routes refuse that
person** (rule 3: hiding a place is never the control).

The places and the rights that open each are one table, `apps/workspace/src/shell/places.json`,
which the Glass's switcher and Home read. This file assigns every Conduit route to the places whose
screens call it (`PLACE_RULES`), and proves:

1. the assignment covers what the screens really call: each call site's place, derived from the
   workspace's source and its imports, is among its route's places (`screen_places`; shown red by a
   planted Admin screen calling a Studio route, `test_a_planted_call_from_another_place_is_found`);
2. each place's rights in `places.json` are exactly the rights its own routes need;
3. a route of the Studio or Admin with no right is a named reference catalogue, never an omission;
4. each built-in role, legacy role and single `right:` grant is offered the places ADR-145 lists,
   and every route of each place hidden from it refuses it over HTTP with `403 right_required`
   (red with any one route's `require_right` removed: shown red on 7 November 2026 for
   `invite_person_route` and `list_studio_recipe_drafts`).

The owner's ruling of 7 November 2026 ("Re-home the routes"): no role loses a right. The analyst's
upload (ADR-067) answers as a Glass route; the schedule preview, a pipeline's schedule and its pause
and resume, and a source's refresh pause and resume answer as Admin routes too; the Studio's other
routes need a Studio right (ADR-145 Amendment 1).
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from pathlib import Path

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from schemas.domain import Principal
from schemas.rights import LEGACY_ROLE_RIGHTS, ROLE_RIGHTS, Right, rights_for

WORKSPACE_SRC = Path(__file__).resolve().parents[4] / "OspreyFlow_Core/apps/workspace/src"
PLACES_JSON = WORKSPACE_SRC / "shell/places.json"

# (path pattern, the places whose screens call it, which screen). First match wins.
PLACE_RULES: list[tuple[str, frozenset[str], str]] = [
    (r"^/v1/admin/screening-lists", frozenset({"glass"}), "Monitoring › Lists (alerts/api.ts)"),
    (r"^/v1/admin/", frozenset({"admin"}), "the Admin place"),
    (r"^/v1/ingest/schedule-preview$|/ingest/recipes/\{recipe_id\}/schedule(/pause|/resume)?$"
     r"|/sources/\{source_id\}/refresh/(pause|resume)$", frozenset({"ingest", "admin"}),
     "the Studio's schedules, and Admin's (the owner's ruling: Admin routes too)"),
    (r"/ingest/source-files$", frozenset({"glass", "ingest"}),
     "the analyst's upload (ADR-067), a Glass route by the owner's ruling; the Studio's Connect"),
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

#: What each role is offered (ADR-145 decision 7 lists the places), the bundles as `rights.py` has
#: them.
EXPECTED_PLACES = {
    "analyst": ["glass"],
    "data_engineer": ["glass", "ingest", "admin"],
    "osprey-admin": ["glass", "admin"],
    "reports_viewer": ["glass"],
    "super": ["glass", "ingest", "admin"],
    "source_author": ["glass", "ingest"],
    "source_approver": ["ingest", "admin"],
    "loader": ["ingest"],
    "compliance": ["glass"],
}
#: The token roles each case signs in with: the four roles, the Super user preset, the legacy roles,
#: and every right granted singly (`right:<name>`).
TOKEN_ROLES: dict[str, list[str]] = (
    {role: [role] for role in ROLE_RIGHTS}
    | {"super": ["analyst", "data_engineer"]}
    | {role: [role] for role in LEGACY_ROLE_RIGHTS}
    | {f"right:{r.value}": [f"right:{r.value}"] for r in Right}
)


def _places() -> dict[str, frozenset[str]]:
    table = json.loads(PLACES_JSON.read_text())
    return {place["id"]: frozenset(place["rights"]) for place in table["places"]}


def places_for(held: Iterable[Right | str], places: dict[str, frozenset[str]]) -> list[str]:
    """`shell/places.ts`'s `placesFor` for known rights: a place is offered for any one of its
    rights, in the table's order."""
    values = {str(r) for r in held}
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


# --- What the screens call, read from the workspace's source ------------------------------------

#: The shell and Home stand outside every place: they frame them, so importing a module does not
#: make it theirs (Home reads each place's figures only for whom that place is open).
NEUTRAL = ("App.tsx", "main.tsx", "shell/", "home/", "testing/")
_IMPORT = re.compile(
    r"""(?:import|export)\s+(?:type\s+)?(?:\{([^}]*)\}|[\w*\s,{}]+?)\s+from\s+["'](\.[^"']+)["']"""
)
_EXPORTED = re.compile(r"^export\s+(?:(?:async\s+)?function\s+(\w+)|const\s+(\w+)\s*=)", re.M)
_LITERAL = re.compile(r"`([^`]*)`|\"([^\"\n]*)\"")


#: A file whose screen stands in another place than its folder says.
MOVED = {"linktypes/ProposedTypes.tsx": "admin"}  # ADR-090 Amendment 5: Proposed types, in Admin


def _own_place(rel: str) -> str | None:
    if rel in MOVED:
        return MOVED[rel]
    if rel.startswith(NEUTRAL):
        return None
    return (
        "ingest" if rel.startswith("ingest/") else "admin" if rel.startswith("admin/") else "glass"
    )


def _resolve(base: Path, spec: str, root: Path) -> str | None:
    target = (base.parent / spec).resolve()
    candidates = [
        target,
        target.with_name(target.name + ".ts"),
        target.with_name(target.name + ".tsx"),
        target / "index.ts",
        target / "index.tsx",
    ]
    for candidate in candidates:
        if candidate.is_file():
            try:
                return candidate.relative_to(root.resolve()).as_posix()
            except ValueError:
                return None
    return None


#: The workspace's path helpers, read as the prefixes they build (`ingest/api.ts`'s `studioCase`,
#: `ingest/sources/api.ts`'s `dataset`, `alerts/api.ts`'s `caseUrl`).
BASES = {"studioCase": "/v1/investigations/{x}", "dataset": "/v1/datasets/{x}"}


def _fragments(text: str) -> list[str]:
    """The API paths a piece of source names: each literal holding a path, its `${…}` parts as
    `{x}` (a known path helper as the prefix it builds), from its first segment, without a query."""
    found = []
    for match in _LITERAL.finditer(text):
        literal = match.group(1) if match.group(1) is not None else match.group(2)
        base = re.match(r"^\$\{(\w+)\(", literal)
        prefix = BASES.get(base.group(1), "") if base else ""
        literal = prefix + re.sub(r"^\$\{[^}]*\}", "", literal)
        literal = re.sub(r"\$\{[^}]*\}", "{x}", literal).split("?")[0]
        if " " in literal or "/" not in literal:
            continue
        segments = [s for s in literal.strip("/").split("/") if s]
        # A generic helper's literal (`/v1/admin/${path}`) names no route: two real segments.
        literal_segments = [s for s in segments if re.fullmatch(r"[a-z][a-z-]*", s) and s != "v1"]
        if len(literal_segments) >= 2:
            found.append("/" + "/".join(segments))
    return found


def screen_places(root: Path) -> dict[str, set[str]]:
    """For each API path fragment the workspace's source names, the places whose screens call it: an
    exported function's fragments belong to the places of the files that import that function, and
    any other fragment to its own file's place (a file's folder: `ingest/` the Studio, `admin/`
    Admin, the shell and Home none, anything else the Glass; `MOVED` the exceptions). An
    under-approximation — a component imported across places counts once, by its own folder — so
    a route this misses is not proved, but one it finds in the wrong place is a real call."""
    root = root.resolve()
    files = {p.relative_to(root).as_posix(): p.read_text() for p in root.rglob("*.ts*")
             if ".test." not in p.name and not p.name.endswith(".d.ts")}  # fmt: skip
    importers: dict[str, set[str]] = {f: set() for f in files}
    users: dict[tuple[str, str], set[str]] = {}
    for rel, text in files.items():
        for names, spec in _IMPORT.findall(text):
            target = _resolve(root / rel, spec, root)
            if target is None or target not in files:
                continue
            importers[target].add(rel)
            for name in re.findall(r"(?:type\s+)?(\w+)(?:\s+as\s+\w+)?\s*(?:,|$)", names or ""):
                users.setdefault((target, name), set()).add(rel)
    places: dict[str, set[str]] = {f: ({p} if (p := _own_place(f)) else set()) for f in files}
    reached: dict[str, set[str]] = {}
    for rel, text in files.items():
        starts = [(m.start(), m.group(1) or m.group(2)) for m in _EXPORTED.finditer(text)]
        chunks: list[tuple[str | None, str]] = [(None, text[: starts[0][0]] if starts else text)]
        for i, (start, name) in enumerate(starts):
            chunks.append(
                (name, text[start : starts[i + 1][0] if i + 1 < len(starts) else len(text)])
            )
        for name, chunk in chunks:
            # A component (capitalised) is drawn where its folder says, wherever it is embedded (the
            # Studio's Verify embeds the Glass's canvas); an API function belongs to its callers.
            callers = users.get((rel, name), set()) if name and name[0].islower() else set()
            where = set().union(*(places[c] for c in callers)) if callers else places[rel]
            for fragment in _fragments(chunk):
                reached.setdefault(fragment, set()).update(where)
    return reached


def _misplaced(root: Path) -> list[tuple[str, str, list[str], list[str]]]:
    reached = screen_places(root)
    wrong = []
    for route in _routes():
        if _declared(route) is None:
            continue  # any signed-in person's: no place's (`test_route_rights.py` records it)
        normal = re.sub(r"\{[a-z_]+(?::path)?\}", "{x}", route.path)
        for fragment, where in reached.items():
            pattern = re.escape(fragment).replace(r"\{x\}", r"[^/]+") + "$"
            if re.search("/" + pattern.lstrip("/"), normal) and not where <= places_of(route.path):
                wrong.append((route.path, fragment, sorted(where), sorted(places_of(route.path))))
    return wrong


def test_every_call_site_s_place_is_among_its_route_s_places() -> None:
    reached = screen_places(WORKSPACE_SRC)
    assert len(reached) > 60, "the source scan found too few call sites to mean anything"
    assert {"glass", "ingest", "admin"} <= set().union(*reached.values())
    assert _misplaced(WORKSPACE_SRC) == []


def test_a_planted_call_from_another_place_is_found(tmp_path: Path) -> None:
    """The red half of the case above: an Admin screen calling a Studio-only route is reported."""
    (tmp_path / "admin").mkdir()
    (tmp_path / "admin/Planted.tsx").write_text(
        "export async function planted(base: string, id: string) {\n"
        "  return fetch(`${base}/v1/investigations/${id}/ingest/recipe-registry`);\n}\n"
    )
    assert [w[0] for w in _misplaced(tmp_path)] == [
        "/v1/investigations/{investigation_id}/ingest/recipe-registry"
    ]


# --- The places' table against the routes --------------------------------------------------------


def test_every_rule_places_at_least_one_route() -> None:
    """A rule that matches nothing is a place assignment stated and exercised by nothing
    (rule 12)."""
    paths = [r.path for r in _routes()]
    for pattern, _, screen in PLACE_RULES[:-1]:
        assert any(re.search(pattern, p) for p in paths), (pattern, screen)


def test_each_place_opens_with_exactly_the_rights_its_own_routes_need() -> None:
    places = _places()
    needed: dict[str, set[str]] = {place: set() for place in places}
    alone: dict[str, set[str]] = {place: set() for place in places}
    for route in _routes():
        right, where = _declared(route), places_of(route.path)
        if right is None:
            continue
        for place in where:
            needed[place].add(right)
        if len(where) == 1:
            alone[next(iter(where))].add(right)
        # A shared route's right must open at least one of its places.
        assert any(right in places[p] for p in where), (route.path, right, sorted(where))
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


@pytest.mark.parametrize("role", sorted(EXPECTED_PLACES))
def test_each_role_is_offered_the_places_adr_145_lists(role: str) -> None:
    assert places_for(rights_for(TOKEN_ROLES[role]), _places()) == EXPECTED_PLACES[role]


def test_a_schedule_an_administrator_owns_still_runs() -> None:
    """`scheduler.py`'s run check asks the schedule's owner for `schedule_pipelines`: re-homing the
    routes kept that right with the administrator, so an administrator's schedules still run."""
    assert Right.SCHEDULE_PIPELINES in rights_for(["osprey-admin"])


def _path(route: APIRoute) -> str:
    path = route.path
    for number in ("{z}", "{x}", "{y}"):
        path = path.replace(number, "0")
    return re.sub(r"\{[a-z_]+(:path)?\}", "x", path)


@pytest.mark.parametrize("role", sorted(TOKEN_ROLES))
def test_every_route_of_a_hidden_place_refuses_the_role(role: str) -> None:
    """Over HTTP, without the stores: the right is checked before anything else a route does
    (`require_right`), so a refusal here needs no case, dataset or store. A route that answers with
    anything but `403 right_required` is a place the switcher hides and the Conduit still opens."""
    from services.api.app import app, get_principal

    places = _places()
    roles = TOKEN_ROLES[role]
    hidden = set(places) - set(places_for(rights_for(roles), places))
    who = Principal(id=f"place-{role}", clearance="SECRET", org_unit="unit-1", roles=roles)
    answered: list[tuple[str, str, int]] = []
    checked = 0
    app.dependency_overrides[get_principal] = lambda: who
    # No lifespan: nothing past the right check is reached, and a route that gets past it answers
    # (500, with no stores) rather than raising, so it is reported, not hidden.
    client = TestClient(app, raise_server_exceptions=False)
    try:
        for route in _routes():
            if not places_of(route.path) <= hidden or _declared(route) is None:
                continue  # a route with no right is any signed-in person's, checked above
            checked += 1
            method = sorted(route.methods or {"GET"})[0]
            response = client.request(
                method, _path(route), headers={"Authorization": "Bearer x"}, json={}
            )
            if not (response.status_code == 403 and "right_required" in response.text):
                answered.append((route.endpoint.__name__, route.path, response.status_code))
    finally:
        app.dependency_overrides.pop(get_principal, None)
    assert answered == [], answered
    if hidden:
        assert checked > 0, (role, hidden)
