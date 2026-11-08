"""The three places (`06_DECISIONS.md` ADR-145 decisions 1 and N6, Amendment 1): the switcher shows
a person only the places their rights open, and **each hidden place's routes refuse that
person** (rule 3: hiding a place is never the control).

A route's checks, as read here (`_checks`), are the right its decorator names (`require_right`), the
Studio role its signature or its dependencies ask for (`require_studio_role`, `SourceAuthorDep`; a
Studio role is a right, `_STUDIO_ROLE_RIGHT`), and the administrator role (`require_admin_role`). A
check made inside a route's body (such as `_require_administrator`) is not read, so this file may
offer a place a body check then refuses, never the reverse (rule 15). Each route belongs to the
place whose screens call it (`PLACE_RULES`), and:

1. a place is offered for the rights that reach its entry screen's first read (`ENTRY`; the Glass's
   case list is everyone's, so any of its routes). `shell/placesByRole.json` records that for every
   role, legacy role and right granted singly, and the Glass's `placesFor` is held to it
   (`shell/places.test.tsx`); `shell/places.json`'s rights are exactly the single rights that open a
   place, and each reaches a screen of that place (read from the workspace's source);
2. every route of a place hidden from a person refuses them, but for routes they hold the checks of
   (a legacy role's own Studio actions), recorded per role as `answered_hidden`;
3. each call site in the workspace's source is among its route's places (shown red by a planted
   Admin screen importing a Studio call, `test_a_planted_call_from_another_place_is_found`).
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from schemas.domain import Principal
from schemas.ingest import StudioRole
from schemas.rights import LEGACY_ROLE_RIGHTS, ROLE_RIGHTS, SUPER_USER_PRESET, Right, rights_for

WORKSPACE_SRC = Path(__file__).resolve().parents[4] / "OspreyFlow_Core/apps/workspace/src"
PLACES_JSON = WORKSPACE_SRC / "shell/places.json"
BY_ROLE_JSON = WORKSPACE_SRC / "shell/placesByRole.json"

# (path pattern, the places whose screens call it, which screen). First match wins.
PLACE_RULES: list[tuple[str, frozenset[str], str]] = [
    (r"^/v1/admin/screening-lists", frozenset({"glass"}), "Monitoring › Lists (alerts/api.ts)"),
    (r"^/v1/admin/", frozenset({"admin"}), "the Admin place"),
    (r"^/v1/exports$", frozenset({"admin"}), "the export ledger, Admin's right (ADR-112 A8)"),
    (r"/ingest/recipes/\{recipe_id\}/held-rows/release$", frozenset({"glass"}),
     "Monitoring's held rows (alerts/api.ts)"),
    (r"/ingest/(extract|candidates)", frozenset({"glass"}),
     "extraction of a case's files, an investigation right (ADR-112 I4)"),
    (r"/ingest/|^/v1/ingest/|^/v1/datasets/\{dataset_id\}/(sources|source-files|model)",
     frozenset({"ingest"}), "the Ingest Studio"),
    (r"", frozenset({"glass"}), "the Glass"),
]  # fmt: skip

#: Routes no place is shown from, each with its reason: the catalogues and the preview read nothing
#: of the deployment; the export ledger reads the deployment but no screen calls it yet.
EXEMPT = {
    # Reference catalogues: any signed-in person (`test_route_rights.py` records them as `None`).
    "list_connectors": "a reference catalogue",
    "list_domain_packs": "a reference catalogue",
    "list_transforms": "a reference catalogue",
    # ADR-145 Amendment 1 (the owner's answer, 7 November 2026): run times computed from the cron
    # text it is sent; Admin › Operations and the Studio's schedule editor both call it.
    "schedule_preview_route": "computes run times from the text sent; reads no store",
    # No screen calls the export ledger's route yet, so no place is shown from it. Its right,
    # Admin's (ADR-112 A8), also answers the legacy `compliance` role, which is offered no place;
    # it refuses everyone else (`test_route_rights.py`). Exempt only while no
    # screen calls it (`test_the_export_ledger_is_exempt_only_while_no_screen_calls_it`).
    "list_exports_route": "no screen calls it",
}

#: A place must be usable, not only answered (the orchestrator's settlement, 7 November 2026): the
#: Studio and Admin are offered for the rights their entry screen's first read needs. The Studio's
#: is the recipe registry (`ingest/api.ts`'s `fetchRecipeRegistry`); Admin's is the first read of
#: the first built section the person holds a right for (ADR-145 Amendment 3: for
#: `administer_system`, Datasets, the first in decision 5's order). The Glass's entry, the case
#: list, is open to every signed-in person, so the Glass is offered for any right one of its routes
#: needs.
ENTRY = {
    "ingest": {"list_studio_recipe_registry"},
    "admin": {"list_people_route", "list_dashboards_route", "list_schedules_route",
              "admin_datasets_route", "list_link_type_proposals_route"},
}  # fmt: skip

#: What each named role is offered (ADR-145 decision 7 lists the places).
EXPECTED_PLACES = {
    "analyst": ["glass"],
    "data_engineer": ["glass", "ingest", "admin"],
    "osprey-admin": ["glass", "admin"],
    "reports_viewer": ["glass"],
    # ADR-112 Amendment 5 decision 2: works alerts in the Glass; Rules and Monitoring, which
    # `author_rules` opens, is the rules lane's L2.9. Never the Studio.
    "rule_author": ["glass"],
    "super": ["glass", "ingest", "admin"],
}
#: The token roles each case signs in with: the four roles, the Super user preset, the legacy roles,
#: every right granted singly (`right:<name>`), and nobody's.
TOKEN_ROLES: dict[str, list[str]] = (
    {role: [role] for role in ROLE_RIGHTS}
    | {"super": list(SUPER_USER_PRESET)}
    | {role: [role] for role in LEGACY_ROLE_RIGHTS}
    | {f"right:{r.value}": [f"right:{r.value}"] for r in Right}
    | {"none": []}
)
PLACE_ORDER = ["glass", "ingest", "admin"]


def _routes() -> list[APIRoute]:
    from services.api.app import app

    return [r for r in app.routes if isinstance(r, APIRoute)]


def _checks_of(dependant: object) -> set[str]:
    from services.api import app as conduit

    found: set[str] = set()
    for dependency in dependant.dependencies:  # type: ignore[attr-defined]
        call = dependency.call
        right = getattr(call, "required_right", None)
        if right is not None:
            found.add(str(right))
        if getattr(call, "__qualname__", "").startswith("require_studio_role"):
            for cell in call.__closure__ or ():
                if isinstance(cell.cell_contents, StudioRole):
                    found.add(str(conduit._STUDIO_ROLE_RIGHT[cell.cell_contents]))
        if call is conduit.require_admin_role:
            found.add(f"role:{conduit.ADMIN_ROLE}")
        found |= _checks_of(dependency)
    return found


def _checks(route: APIRoute) -> frozenset[str]:
    """The checks the route declares, its decorator's and its signature's, nested ones included;
    not one made inside its body."""
    return frozenset(_checks_of(route.dependant))


def _answers(route: APIRoute, roles: list[str]) -> bool:
    held = {str(r) for r in rights_for(roles)} | {f"role:{r}" for r in roles}
    return _checks(route) <= held


def places_of(path: str) -> frozenset[str]:
    for pattern, places, _ in PLACE_RULES:
        if re.search(pattern, path):
            return places
    raise AssertionError(path)  # the last rule matches everything


def _placed() -> list[APIRoute]:
    """The routes a place is shown from: each with a check, none exempt."""
    return [r for r in _routes() if _checks(r) and r.endpoint.__name__ not in EXEMPT]


def _entry_routes(place: str) -> list[APIRoute]:
    if place in ENTRY:
        return [r for r in _routes() if r.endpoint.__name__ in ENTRY[place]]
    return [r for r in _placed() if place in places_of(r.path)]


def offered(roles: list[str]) -> list[str]:
    """The places whose entry this person's checks reach, from the routes alone (not
    `places.json`): the Studio's and Admin's entry reads, any route of the Glass."""
    return [p for p in PLACE_ORDER if any(_answers(r, roles) for r in _entry_routes(p))]


def answered_hidden(roles: list[str]) -> list[str]:
    """Routes of a place not offered to this person that still answer them, by their own checks:
    the Studio's run routes for a `loader`, say, whose Studio is not offered because its entry
    read needs `edit_pipelines`. Recorded per role in `placesByRole.json`, so each is seen."""
    hidden = set(PLACE_ORDER) - set(offered(roles))
    return sorted(
        r.endpoint.__name__ for r in _placed() if places_of(r.path) <= hidden and _answers(r, roles)
    )


def _places_json() -> dict[str, frozenset[str]]:
    table = json.loads(PLACES_JSON.read_text())
    return {place["id"]: frozenset(place["rights"]) for place in table["places"]}


def _by_role() -> dict[str, dict[str, list[str]]]:
    return {
        name: {
            "rights": sorted(str(r) for r in rights_for(roles)),
            "places": offered(roles),
            "answered_hidden": answered_hidden(roles),
        }
        for name, roles in sorted(TOKEN_ROLES.items())
    }


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
#: The workspace's path helpers, read as the prefixes they build (`ingest/api.ts`'s `studioCase`,
#: `ingest/sources/api.ts`'s `dataset`).
BASES = {"studioCase": "/v1/investigations/{x}", "dataset": "/v1/datasets/{x}"}
#: Helpers that take a path relative to a prefix, read wherever they are called: `admin/api.ts`'s
#: `call(api, "people")`, `alerts/api.ts`'s `caseUrl(base, id, "held-rows")`, and
#: `reports/caseHttp.ts`'s `send(api, "GET", "data-feeds")`.
_PATH = r"([`\"][^`\"]*[`\"])"
RELATIVE_CALLS = [
    (re.compile(r"\bcall<[^>]*>\(\s*api,\s*" + _PATH), "/v1/admin", "admin/api.ts"),
    (re.compile(r"\bcaseUrl\([^,()]+,\s*[^,()]+,\s*" + _PATH), "/v1/investigations/{x}", None),
    (re.compile(r"\bsend\(\s*api,\s*\"[A-Z]+\",\s*" + _PATH), "/v1/investigations/{x}", None),
]


def _own_place(rel: str) -> str | None:
    if rel in MOVED:
        return MOVED[rel]
    if rel.startswith(NEUTRAL):
        return None
    if rel.startswith("ingest/"):
        return "ingest"
    return "admin" if rel.startswith("admin/") else "glass"


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


def _fragments(text: str, prefix: str = "") -> list[str]:
    """The API paths a piece of source names: each literal holding a path, its `${…}` parts as
    `{x}` (a known path helper as the prefix it builds), from its first segment, without a query."""
    found = []
    for match in _LITERAL.finditer(text):
        literal = match.group(1) if match.group(1) is not None else match.group(2)
        base = re.match(r"^\$\{(\w+)\(", literal)
        lead = BASES.get(base.group(1), "") if base else ""
        literal = prefix + lead + re.sub(r"^\$\{[^}]*\}", "", literal)
        literal = re.sub(r"\$\{[^}]*\}", "{x}", literal).split("?")[0]
        if " " in literal or "/" not in literal:
            continue
        segments = [s for s in literal.strip("/").split("/") if s]
        # A generic helper's literal (`/v1/admin/${path}`) names no route: two real segments, or a
        # path from `/v1/` itself (`/v1/investigations`, `/v1/investigations/${id}`).
        literal_segments = [s for s in segments if re.fullmatch(r"[a-z][a-z-]*", s) and s != "v1"]
        rooted = segments[:1] == ["v1"] and segments != ["v1", "admin", "{x}"]
        if len(literal_segments) >= 2 or (rooted and literal_segments):
            found.append("/" + "/".join(segments))
    return found


def _chunk_fragments(rel: str, chunk: str) -> list[str]:
    found = _fragments(chunk)
    for pattern, prefix, only in RELATIVE_CALLS:
        if only is not None and rel != only:
            continue
        for match in pattern.finditer(chunk):
            found += _fragments(match.group(1), prefix + "/")
    return found


def screen_places(root: Path) -> dict[str, set[str]]:
    """For each API path fragment the workspace's source names, the places whose screens call it: an
    exported API function's fragments belong to the places of the files that import it, and any
    other fragment to its own file's place (a file's folder: `ingest/` the Studio, `admin/` Admin,
    the shell and Home none, anything else the Glass; `MOVED` the exceptions). A component
    (capitalised) is drawn where its folder says, wherever it is embedded (the Studio's Verify
    embeds the Glass's canvas). An under-approximation: a route this misses is not proved, but one
    it finds in the wrong place is a real call."""
    root = root.resolve()
    files = {p.relative_to(root).as_posix(): p.read_text() for p in root.rglob("*.ts*")
             if ".test." not in p.name and not p.name.endswith(".d.ts")}  # fmt: skip
    users: dict[tuple[str, str], set[str]] = {}
    for rel, text in files.items():
        for names, spec in _IMPORT.findall(text):
            target = _resolve(root / rel, spec, root)
            if target is None or target not in files:
                continue
            for name in re.findall(r"(?:type\s+)?(\w+)(?:\s+as\s+\w+)?\s*(?:,|$)", names or ""):
                users.setdefault((target, name), set()).add(rel)
    places: dict[str, set[str]] = {f: ({p} if (p := _own_place(f)) else set()) for f in files}
    reached: dict[str, set[str]] = {}
    for rel, text in files.items():
        starts = [(m.start(), m.group(1) or m.group(2)) for m in _EXPORTED.finditer(text)]
        chunks: list[tuple[str | None, str]] = [(None, text[: starts[0][0]] if starts else text)]
        for i, (start, name) in enumerate(starts):
            end = starts[i + 1][0] if i + 1 < len(starts) else len(text)
            chunks.append((name, text[start:end]))
        for name, chunk in chunks:
            callers = users.get((rel, name), set()) if name and name[0].islower() else set()
            where = set().union(*(places[c] for c in callers)) if callers else places[rel]
            for fragment in _chunk_fragments(rel, chunk):
                reached.setdefault(fragment, set()).update(where)
    return reached


def _normal(path: str) -> str:
    return re.sub(r"\{[a-z_]+(?::path)?\}", "{x}", path)


def _callers(route: APIRoute, reached: dict[str, set[str]]) -> set[str]:
    """The places whose fragments name the route. A fragment ending in a value
    (`/v1/datasets/${id}`, the Studio's base for a dataset's routes) is not taken for a route with a
    word there (`/v1/datasets/composites`) where another route holds an id at that place
    (`/v1/datasets/{dataset_id}/sources`): the value is that id, not the word."""
    normal = _normal(route.path)
    normals = {_normal(r.path) for r in _routes()}
    where: set[str] = set()
    for fragment, places in reached.items():
        found = re.search(re.escape(fragment).replace(r"\{x\}", r"[^/]+") + "$", normal)
        if found is None:
            continue
        if fragment.endswith("{x}") and not normal.endswith("{x}"):
            an_id_there = normal[: found.end()].rsplit("/", 1)[0] + "/{x}"
            if any(n == an_id_there or n.startswith(an_id_there + "/") for n in normals):
                continue
        where |= places
    return where


def _misplaced(root: Path) -> list[tuple[str, list[str], list[str]]]:
    """Routes a screen of another place calls. The scan does not see methods, so a path shared with
    a route any signed-in person may call (`GET /v1/investigations`, the case list, beside
    `POST`, a new case) is left out: its call may be that one."""
    reached = screen_places(root)
    open_paths = {r.path for r in _routes() if not _checks(r)}
    return [
        (route.path, sorted(where), sorted(places_of(route.path)))
        for route in _placed()
        if route.path not in open_paths
        and not (where := _callers(route, reached)) <= places_of(route.path)
    ]


def test_every_call_site_s_place_is_among_its_route_s_places() -> None:
    reached = screen_places(WORKSPACE_SRC)
    assert len(reached) > 60, "the source scan found too few call sites to mean anything"
    assert {"glass", "ingest", "admin"} <= set().union(*reached.values())
    assert _misplaced(WORKSPACE_SRC) == []


def test_a_planted_call_from_another_place_is_found(tmp_path: Path) -> None:
    """The red half of the case above, in a real call site's shape: an Admin screen importing a
    Studio API function, whose path is built through the Studio's own `dataset` helper."""
    (tmp_path / "admin").mkdir()
    (tmp_path / "ingest/sources").mkdir(parents=True)
    (tmp_path / "ingest/sources/api.ts").write_text(
        "const dataset = (api: Api, id: string) => `${api.apiBaseUrl}/v1/datasets/${id}`;\n"
        "export const listSources = (api: Api, datasetId: string) =>\n"
        '  call<Source[]>(api, `${dataset(api, datasetId)}/sources`, "Reading the sources");\n'
    )
    (tmp_path / "admin/Planted.tsx").write_text(
        'import { listSources } from "../ingest/sources/api";\n'
        "export function Planted() { void listSources(api, 'd'); return null; }\n"
    )
    assert [w[0] for w in _misplaced(tmp_path)] == ["/v1/datasets/{dataset_id}/sources"] * 2


def test_a_dataset_base_is_not_taken_for_the_composites_route_but_a_call_to_it_is() -> None:
    """The case above's matching, both ways: the Studio's base for a dataset's routes is not a call
    to `POST /v1/datasets/composites`, which no screen makes; a Studio file naming that route is."""
    from services.api.app import app

    route = next(
        r for r in app.routes if isinstance(r, APIRoute) and r.path == "/v1/datasets/composites"
    )
    assert _callers(route, {"/v1/datasets/{x}": {"ingest"}}) == set()
    assert _callers(route, {"/v1/datasets/composites": {"ingest"}}) == {"ingest"}


# --- The places' table against the routes --------------------------------------------------------


def test_every_rule_places_at_least_one_route() -> None:
    """A rule that matches nothing is a place assignment stated and exercised by nothing
    (rule 12)."""
    paths = [r.path for r in _routes()]
    for pattern, _, screen in PLACE_RULES[:-1]:
        assert any(re.search(pattern, p) for p in paths), (pattern, screen)


def test_a_check_in_a_route_s_signature_is_read() -> None:
    """The reader sees a Studio role asked for in a route's signature (`SourceAuthorDep`) as well
    as its decorator's right: the dataset's sources need `edit_pipelines` as well."""
    route = next(r for r in _routes() if r.endpoint.__name__ == "list_dataset_sources")
    assert _checks(route) == {"add_ingest_files", "edit_pipelines"}


def _openers(place: str) -> set[frozenset[str]]:
    sets = {_checks(r) for r in _entry_routes(place)}
    return {s for s in sets if not any(o < s for o in sets)}


def test_places_json_names_exactly_the_single_rights_that_open_each_place() -> None:
    """`placesFor` asks for any one right, so every way into a place must be a single right, or
    hold one, or be the administrator role (whose holders hold Admin's rights)."""
    table = _places_json()
    for place in PLACE_ORDER:
        openers = _openers(place)
        singles = {next(iter(s)) for s in openers if len(s) == 1}
        assert table[place] == singles, (place, sorted(table[place] ^ singles))
        for combined in openers - {frozenset({s}) for s in singles}:
            roles = {c.removeprefix("role:") for c in combined if c.startswith("role:")}
            covered = combined & singles or any(
                {str(r) for r in ROLE_RIGHTS.get(role, ())} & singles for role in roles
            )
            assert covered, (place, sorted(combined))


def test_each_right_a_place_claims_reaches_a_screen_of_that_place() -> None:
    """The other direction: a right in `places.json` opens its place only if a screen of that place
    calls an entry route that right alone answers, so nobody is offered an empty place (red with a
    `loader`'s `run_pipelines` planted in the Studio's rights)."""
    reached = screen_places(WORKSPACE_SRC)
    unused = []
    for place, rights in _places_json().items():
        for right in rights:
            routes = [r for r in _entry_routes(place) if _checks(r) == {right}]
            if not any(place in _callers(r, reached) for r in routes):
                unused.append((place, right))
    assert unused == []


def test_the_entry_reads_are_the_places_own() -> None:
    """A rule that names an entry read no route has, or one in another place, proves nothing."""
    names = {r.endpoint.__name__: r for r in _routes()}
    for place, entries in ENTRY.items():
        for name in entries:
            assert name in names and place in places_of(names[name].path), (place, name)


def test_the_record_of_places_by_role_is_the_routes() -> None:
    """`placesByRole.json` is what the routes answer; `places.test.tsx` holds `placesFor` to it.
    Rewrite it with `OSPREY_WRITE_PLACES_BY_ROLE=1` after a deliberate change."""
    computed = _by_role()
    if os.environ.get("OSPREY_WRITE_PLACES_BY_ROLE") == "1":
        BY_ROLE_JSON.write_text(json.dumps({"roles": computed}, indent=1) + "\n")
    assert json.loads(BY_ROLE_JSON.read_text())["roles"] == computed


@pytest.mark.parametrize("role", sorted(EXPECTED_PLACES))
def test_each_role_is_offered_the_places_adr_145_lists(role: str) -> None:
    assert offered(TOKEN_ROLES[role]) == EXPECTED_PLACES[role]


@pytest.mark.parametrize(
    "name",
    ["list_ingest_connections", "list_dataset_source_files", "list_dataset_sources",
     "register_dataset_source", "get_dataset_source", "get_dataset_source_profile",
     "get_dataset_source_lineage"],
)  # fmt: skip
def test_an_analyst_is_refused_on_the_dataset_s_sources_routes(name: str) -> None:
    """The orchestrator's case of 7 November 2026: these seven name `add_ingest_files`, which every
    Analyst holds, and refuse an Analyst anyway, by the Studio role in their signature."""
    from services.api.app import app, get_principal, require_studio_dataset

    route = next(r for r in _routes() if r.endpoint.__name__ == name)
    who = Principal(id="place-analyst", clearance="SECRET", org_unit="unit-1", roles=["analyst"])
    app.dependency_overrides[get_principal] = lambda: who
    # The dataset is one the Analyst reaches, so nothing but the route's checks can refuse them.
    app.dependency_overrides[require_studio_dataset] = lambda dataset_id: dataset_id
    try:
        client = TestClient(app, raise_server_exceptions=False)
        response = client.request(sorted(route.methods or {"GET"})[0], _path(route), json={})
    finally:
        app.dependency_overrides.pop(get_principal, None)
        app.dependency_overrides.pop(require_studio_dataset, None)
    assert response.status_code == 403 and "studio role" in response.text, (name, response.text)


def test_the_export_ledger_is_exempt_only_while_no_screen_calls_it() -> None:
    """The day a screen calls `GET /v1/exports`, this fails: take it out of `EXEMPT`, and it is an
    Admin route like the others (the legacy `compliance` role, holding its right alone, is then
    offered Admin, or the screen's place)."""
    route = next(r for r in _routes() if r.endpoint.__name__ == "list_exports_route")
    assert places_of(route.path) == {"admin"}
    assert _callers(route, screen_places(WORKSPACE_SRC)) == set()


def test_the_schedule_preview_reads_no_store() -> None:
    """Why it is exempt: its only dependencies are who is asking and their right, and the body."""
    route = next(r for r in _routes() if r.endpoint.__name__ == "schedule_preview_route")
    from services.api.app import get_principal

    def calls(dependant: object) -> set[str]:
        found = set()
        for d in dependant.dependencies:  # type: ignore[attr-defined]
            found.add(getattr(d.call, "__name__", repr(d.call)))
            found |= calls(d)
        return found

    named = {c for c in calls(route.dependant) if not c.startswith("<fastapi.security")}
    assert named <= {"_dependency", get_principal.__name__}, named
    assert _checks(route) == {"schedule_pipelines"}


def test_a_schedule_an_administrator_owns_still_runs(monkeypatch: pytest.MonkeyPatch) -> None:
    """`scheduler.py`'s own run check (`ScheduleExecutor._owner`) refuses a schedule whose owner
    lacks `schedule_pipelines`: an administrator's schedule passes it, an analyst's is refused."""
    import asyncio
    from types import SimpleNamespace

    from services.api import scheduler

    monkeypatch.setattr(scheduler, "resolve_source_handling", lambda recipe: None)
    monkeypatch.setattr(scheduler, "principal_may_view", lambda handling, owner, scheme: True)
    people = {
        who: Principal(id=who, clearance="SECRET", org_unit="unit-1", roles=[role])
        for who, role in (("adm-1", "osprey-admin"), ("ana-1", "analyst"))
    }
    executor = object.__new__(scheduler.ScheduleExecutor)

    async def resolve(owner_id: str) -> Principal:
        return people[owner_id]

    async def check_case(owner: Principal, case: str) -> Principal:
        return owner

    executor._resolve = resolve  # type: ignore[method-assign]
    executor.check_case = check_case
    executor.scheme = None  # type: ignore[assignment]

    def run(owner: str) -> object:
        recipe = SimpleNamespace(schedule_owner=owner, schedule_case="case-1")
        return asyncio.run(executor._owner(recipe))  # type: ignore[arg-type]

    assert run("adm-1")[0].id == "adm-1"  # type: ignore[index]
    with pytest.raises(scheduler._Refused, match="schedule_pipelines"):
        run("ana-1")


def _path(route: APIRoute) -> str:
    path = route.path
    for number in ("{z}", "{x}", "{y}"):
        path = path.replace(number, "0")
    return re.sub(r"\{[a-z_]+(:path)?\}", "x", path)


@pytest.mark.parametrize("role", sorted(TOKEN_ROLES))
def test_every_route_of_a_hidden_place_refuses_the_role(role: str) -> None:
    """The checks (`_checks`) of each route of each place hidden from this person refuse them, but
    for the routes recorded as `answered_hidden`. And over HTTP, without the stores, none of those
    routes answers them: a check's 403,
    or a 404 or 500 where a store or a case is reached before the checks, but never a success. A
    case's or a dataset's lookup cannot stand in for the checks: the dataset is given as reached."""
    from services.api.app import app, get_principal, require_studio_dataset

    roles = TOKEN_ROLES[role]
    hidden = set(PLACE_ORDER) - set(offered(roles))
    recorded = set(json.loads(BY_ROLE_JSON.read_text())["roles"][role]["answered_hidden"])
    routes = [r for r in _placed() if places_of(r.path) <= hidden and not _answers(r, roles)]
    assert set(answered_hidden(roles)) == recorded, "placesByRole.json is out of date"
    who = Principal(id=f"place-{role}", clearance="SECRET", org_unit="unit-1", roles=roles)
    answered: list[tuple[str, int]] = []
    refused_by_a_check = 0
    app.dependency_overrides[get_principal] = lambda: who
    app.dependency_overrides[require_studio_dataset] = lambda dataset_id: dataset_id
    # No lifespan: a route that gets past its checks reaches a missing store and answers 500 rather
    # than raising, so it is counted, not hidden.
    client = TestClient(app, raise_server_exceptions=False)
    try:
        for route in routes:
            method = sorted(route.methods or {"GET"})[0]
            headers = {"Authorization": "Bearer x"}
            response = client.request(method, _path(route), headers=headers, json={})
            if response.status_code < 400:
                answered.append((route.endpoint.__name__, response.status_code))
            by_a_check = re.search(r"right_required|lacks required", response.text)
            if response.status_code == 403 and by_a_check:
                refused_by_a_check += 1
    finally:
        app.dependency_overrides.pop(get_principal, None)
        app.dependency_overrides.pop(require_studio_dataset, None)
    assert answered == [], answered
    if routes:
        # Most refusals are the checks' own: the right is checked before anything else.
        assert refused_by_a_check >= len(routes) * 0.8, (role, refused_by_a_check, len(routes))
