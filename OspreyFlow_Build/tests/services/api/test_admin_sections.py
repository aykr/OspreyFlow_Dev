"""The Admin place's sections (`06_DECISIONS.md` ADR-145 decision 5, ADR-110 Amendment 14): each is
shown only to a holder of its right (`admin/sections.json`, the Glass's `sectionsFor`), and **each
built section's routes refuse a principal without that right** (rule 3: hiding a section is never
the control).

A section's routes are read from the code, not a hand-kept list: the routes its screen file calls,
following the files it imports (a component module whole; a lower-case module, such as an `api.ts`,
only for the names imported from it), matched to the Conduit's routes as the place test matches them
(`test_place_routes.py`, whose reading of a route's checks is used here: its decorator's right, its
signature's Studio role, the administrator role; never a check inside its body). Then:

1. every route a built section calls declares the section's right, but for the open reads named in
   `SHARED` and the place test's exemptions (`test_each_built_section_s_routes_need_its_right`);
2. over HTTP, a principal holding every right but the section's is refused on each of them;
3. every `/v1/admin` route is some section's, or recorded here with its reason; and every file under
   `admin/sections/` is a section's screen, drawn by `AdminPlace.tsx`.

Shown red: a route declaring another right is found, and a planted screen calling another section's
route is found (`test_a_route_declaring_another_right_is_found`,
`test_a_planted_screen_calling_another_section_s_route_is_found`).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from fastapi import Depends, FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from schemas.domain import Principal
from schemas.rights import Right
from tests.services.api.test_place_routes import (
    _EXPORTED,
    _IMPORT,
    EXEMPT,
    WORKSPACE_SRC,
    _checks,
    _chunk_fragments,
    _path,
    _resolve,
    _routes,
)

SECTIONS_JSON = WORKSPACE_SRC / "admin/sections.json"
ADMIN_PLACE = WORKSPACE_SRC / "admin/AdminPlace.tsx"

#: Folders a screen's walk does not enter: the design system and the brand draw no data.
NOT_WALKED = ("design/", "brand/")

#: `/v1/admin` routes no section calls, each with its reason.
NOT_A_SECTION_S = {
    # Monitoring › Lists in the Glass calls these (`test_place_routes.py`'s first rule).
    r"^/v1/admin/screening-lists": "the Glass's Monitoring › Lists",
    # Run by `ospreyflow` and the site geospatial wizard, not by a screen (App.tsx's note).
    r"^/v1/admin/geospatial/": "the geospatial wizard's, no screen",
}


def sections() -> list[dict[str, str]]:
    return [s for g in json.loads(SECTIONS_JSON.read_text())["groups"] for s in g["sections"]]


def built() -> list[dict[str, str]]:
    return [s for s in sections() if "screen" in s]


def _sources(root: Path) -> dict[str, str]:
    return {p.relative_to(root).as_posix(): p.read_text() for p in root.rglob("*.ts*")
            if ".test." not in p.name and not p.name.endswith(".d.ts")}  # fmt: skip


def screen_fragments(root: Path, screen: str) -> list[str]:
    """The API path fragments a screen's walk names: the screen and every component module it
    imports, whole; a lower-case module only in the chunks of the names imported from it."""
    root = root.resolve()
    files = _sources(root)
    wanted: dict[str, set[str] | None] = {screen: None}  # None: the whole file
    queue = [screen]
    while queue:
        rel = queue.pop()
        for names, spec in _IMPORT.findall(files.get(rel, "")):
            target = _resolve(root / rel, spec, root)
            if target is None or target not in files or target.startswith(NOT_WALKED):
                continue
            component = Path(target).name[0].isupper()
            imported = set(re.findall(r"(?:type\s+)?(\w+)(?:\s+as\s+\w+)?\s*(?:,|$)", names or ""))
            if component:
                if wanted.get(target, set()) is not None:
                    wanted[target] = None
                    queue.append(target)
            elif target not in wanted:
                wanted[target] = imported
                queue.append(target)
            elif wanted[target] is not None:
                wanted[target] |= imported  # type: ignore[operator]
    found: list[str] = []
    for rel, names in wanted.items():
        text = files[rel]
        starts = [(m.start(), m.group(1) or m.group(2)) for m in _EXPORTED.finditer(text)]
        if names is None:
            found += _chunk_fragments(rel, text) + _helper_fragments(root, rel, text)
            continue
        for i, (start, name) in enumerate(starts):
            if name in names:
                end = starts[i + 1][0] if i + 1 < len(starts) else len(text)
                found += _chunk_fragments(rel, text[start:end]) + _helper_fragments(
                    root, rel, text[start:end]
                )
    return found


#: `admin/api.ts`'s path helpers (`person(userId, "access")`, `schedule(recipeId, "runs")`), read
#: from their own definitions (`const person = (userId: string, what: string) => …`).
_HELPER = re.compile(
    r"const (\w+) = \(\w+: string, \w+: string\) => `([a-z-]+)/\$\{[^}]*\}/\$\{\w+\}`"
)
_HELPER_CALL = re.compile(r"\bcall<[^>]*>\(\s*api,\s*(\w+)\([^,()]+,\s*\"([a-z-]+)\"\)")


def _helper_fragments(root: Path, rel: str, chunk: str) -> list[str]:
    if rel != "admin/api.ts":
        return []
    helpers = dict(_HELPER.findall((root / rel).read_text()))
    return [
        f"/v1/admin/{helpers[name]}/{{x}}/{tail}"
        for name, tail in _HELPER_CALL.findall(chunk)
        if name in helpers
    ]


def _reached(fragments: list[str], routes: list[APIRoute]) -> list[APIRoute]:
    out = []
    for route in routes:
        normal = re.sub(r"\{[a-z_]+(?::path)?\}", "{x}", route.path)
        if any(
            re.search(re.escape(f).replace(r"\{x\}", r"[^/]+") + "$", normal) for f in fragments
        ):
            out.append(route)
    return out


#: Routes open to every signed-in person that a section's screen reads, each with its reason. Only
#: these are passed over: any other route a screen calls must declare the section's right, so a
#: route whose check is removed is found (`test_a_route_with_its_check_removed_is_found`).
SHARED = {
    "get_handling_scheme_route": "the deployment's classifications and handling codes, a reference "
    "every signed-in person reads (People's access editor, Dashboards' clearance)",
}


def section_routes(root: Path, screen: str, routes: list[APIRoute]) -> list[APIRoute]:
    """The routes a section's screen calls that are its own: all but `SHARED` and the place test's
    exemptions (a reference catalogue, the schedule preview)."""
    return [
        r
        for r in _reached(screen_fragments(root, screen), routes)
        if r.name not in SHARED | EXEMPT.keys()
    ]


def unguarded(right: str, routes: list[APIRoute]) -> list[tuple[str, str, list[str]]]:
    return [
        (sorted(r.methods or {"GET"})[0], r.path, sorted(_checks(r)))
        for r in routes
        if right not in _checks(r)
    ]


@pytest.mark.parametrize("section", [s["id"] for s in built()])
def test_each_built_section_s_routes_need_its_right(section: str) -> None:
    s = next(x for x in built() if x["id"] == section)
    routes = section_routes(WORKSPACE_SRC, s["screen"], _routes())
    assert routes, f"{section}: its screen's walk found no route; the scan is not reading it"
    assert unguarded(s["right"], routes) == []


def test_every_section_s_right_is_a_right() -> None:
    assert {s["right"] for s in sections()} <= {r.value for r in Right}
    for s in sections():
        assert ("screen" in s) != ("coming" in s), s["id"]


@pytest.mark.parametrize("section", [s["id"] for s in built()])
def test_each_section_s_routes_refuse_a_principal_without_its_right(section: str) -> None:
    """Over HTTP, without the stores: a principal holding every right but the section's, granted
    singly, is refused on each of the section's routes by the right's own check (403
    `right_required`), never answered."""
    from services.api.app import app, get_principal

    s = next(x for x in built() if x["id"] == section)
    routes = section_routes(WORKSPACE_SRC, s["screen"], _routes())
    who = Principal(id=f"section-{section}", clearance="SECRET", org_unit="unit-1",
                    roles=[f"right:{r.value}" for r in Right if r.value != s["right"]])  # fmt: skip
    app.dependency_overrides[get_principal] = lambda: who
    client = TestClient(app, raise_server_exceptions=False)
    answers: list[tuple[str, int, str]] = []
    try:
        for route in routes:
            method = sorted(route.methods or {"GET"})[0]
            response = client.request(
                method, _path(route), headers={"Authorization": "Bearer x"}, json={}
            )
            answers.append(
                (
                    route.path,
                    response.status_code,
                    s["right"] if "right_required" in response.text else "",
                )
            )
    finally:
        app.dependency_overrides.pop(get_principal, None)
    assert answers and all(code == 403 and why for _, code, why in answers), answers


def test_every_admin_route_is_some_section_s() -> None:
    routes = _routes()
    covered = {r.path for s in built() for r in section_routes(WORKSPACE_SRC, s["screen"], routes)}
    left = sorted({r.path for r in routes if r.path.startswith("/v1/admin/")} - covered)
    unexplained = [p for p in left if not any(re.search(rule, p) for rule in NOT_A_SECTION_S)]
    assert unexplained == []
    # Each recorded reason still names a route that exists and no section calls.
    for rule in NOT_A_SECTION_S:
        assert any(re.search(rule, p) for p in left), rule


def test_every_section_file_is_a_section_s_screen_drawn_by_the_admin_place() -> None:
    screens = {s["screen"] for s in built()}
    folder = WORKSPACE_SRC / "admin/sections"
    under = {p.relative_to(WORKSPACE_SRC).as_posix() for p in folder.glob("*.tsx")
             if ".test." not in p.name}  # fmt: skip
    assert under <= screens
    drawn = {
        _resolve(ADMIN_PLACE, spec, WORKSPACE_SRC)
        for _, spec in _IMPORT.findall(ADMIN_PLACE.read_text())
    }
    assert screens <= drawn


# ---- shown red (rule 15) -------------------------------------------------------------------------


def test_a_route_declaring_another_right_is_found() -> None:
    """A real route declaring another section's right, at a path the Datasets screen calls."""
    from services.api.app import require_right

    planted = FastAPI()

    @planted.get("/v1/admin/datasets", dependencies=[Depends(require_right(Right.MANAGE_PEOPLE))])
    async def admin_datasets_route() -> list[str]:
        return []

    routes = [r for r in planted.routes if isinstance(r, APIRoute)]
    found = section_routes(WORKSPACE_SRC, "admin/sections/Datasets.tsx", routes)
    assert unguarded("administer_system", found) == [
        ("GET", "/v1/admin/datasets", ["manage_people"])
    ]


def test_a_route_with_its_check_removed_is_found() -> None:
    """The Datasets route as it is, but with its `require_right` taken away: it answers everyone."""
    planted = FastAPI()

    @planted.put("/v1/admin/datasets/{dataset_id}/egress")
    async def set_dataset_egress_route(dataset_id: str) -> str:
        return dataset_id

    routes = [r for r in planted.routes if isinstance(r, APIRoute)]
    found = section_routes(WORKSPACE_SRC, "admin/sections/Datasets.tsx", routes)
    assert unguarded("administer_system", found) == [
        ("PUT", "/v1/admin/datasets/{dataset_id}/egress", [])
    ]


def test_the_shared_reads_are_open_and_read_by_a_section() -> None:
    routes = {r.name: r for r in _routes()}
    for name in SHARED:
        assert not _checks(routes[name]), f"{name} now declares a check: it is no longer shared"
    reached = {
        r.name
        for s in built()
        for r in _reached(screen_fragments(WORKSPACE_SRC, s["screen"]), list(routes.values()))
    }
    assert SHARED.keys() <= reached


def test_a_planted_screen_calling_another_section_s_route_is_found(tmp_path: Path) -> None:
    """A Datasets screen that also lists the people, as the real files are laid out."""
    (tmp_path / "admin/sections").mkdir(parents=True)
    (tmp_path / "admin/api.ts").write_text((WORKSPACE_SRC / "admin/api.ts").read_text())
    (tmp_path / "admin/sections/Datasets.tsx").write_text(
        'import { listDatasets, listPeople, type AdminApi } from "../api";\n'
        "export function Datasets({ api }: { api: AdminApi }) {\n"
        "  void listDatasets(api); void listPeople(api); return null;\n}\n"
    )
    routes = section_routes(tmp_path, "admin/sections/Datasets.tsx", _routes())
    assert ("GET", "/v1/admin/people", ["manage_people"]) in unguarded("administer_system", routes)
    # A lower-case module is read only for the names imported: without listPeople, nothing is.
    (tmp_path / "admin/sections/Datasets.tsx").write_text(
        'import { listDatasets, type AdminApi } from "../api";\n'
        "export function Datasets({ api }: { api: AdminApi }) {\n"
        "  void listDatasets(api); return null;\n}\n"
    )
    assert (
        unguarded(
            "administer_system", section_routes(tmp_path, "admin/sections/Datasets.tsx", _routes())
        )
        == []
    )
