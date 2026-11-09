"""The Admin place's sections (`06_DECISIONS.md` ADR-145 decision 5, ADR-110 Amendment 14): each is
shown only to a holder of its right (`admin/sections.json`, the Glass's `sectionsFor`), and **each
built section's routes refuse a principal without that right** (rule 3: hiding a section is never
the control).

A section's routes are read from the code, not a hand-kept list: the routes its screen file calls,
following the files it imports (a component module whole; a lower-case module, such as an `api.ts`,
only for the names imported from it), matched to the Conduit's routes as the place test matches them
(`test_place_routes.py`, whose reading of a route's checks is used here: its decorator's right, its
signature's Studio role, the administrator role; never a check inside its body). Then:

1. every route a built section calls declares the section's right, but for the reads `SHARED` names
   for that section, each with its reason (`test_each_built_section_s_routes_need_its_right`);
2. over HTTP, a principal holding every right but the section's is refused on each of them;
3. every `/v1/admin` route is some section's, or recorded here with its reason; every file under
   `admin/sections/` is a section's screen; and the component `AdminPlace.tsx`'s `SCREENS` draws for
   each section is imported from the very file `sections.json` names
   (`test_admin_place_draws_each_section_from_its_declared_screen`).

Shown red: a route declaring another right, a route with its check removed, a planted screen calling
another section's route, and a `SCREENS` entry drawing another section's file are each found.

What the walk cannot see (an under-approximation, as the place test's scan is): a namespace
import, or a default import beside named ones, of a lower-case module; a call in a lower-case
module's helper that is not exported (only the chunks of exported names imported are read); an
`export class` or `export default`. A call it misses to a route outside `/v1/admin` that declares
no check would escape all of these tests; today the only open route a section reads is the handling
scheme, named in `SHARED`.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest
from fastapi import Depends, FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from schemas.domain import Principal
from schemas.rights import Right
from tests.services.api.test_place_routes import (
    _EXPORTED,
    _IMPORT,
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
    # ADR-145 Amendment 8 (L3.8): the ownership route is built; People's Disable… reads it in admin's L2.5b
    # (CARRIES), which removes this line.
    r"^/v1/admin/people/\{user_id\}/ownership$": "People's Disable…, not yet drawn (L2.5b)",
    # L3.4 (ADR-143 Amendment 2 decision 1): an administrator's *Delete* of a removed case's layer,
    # after Admin's own dry run. Its button in Admin › Datasets is the admin lane's screen, asked for
    # through the orchestrator; until it lands no section calls it (the Studio's Authors delete
    # through their own route meanwhile).
    r"^/v1/admin/datasets/\{dataset_id\}/cases/\{investigation_id\}/delete$":
        "Admin › Datasets' Delete, the admin lane's screen to come",
    # ADR-090 Amendment 4 (L2.7): Admin's Proposed types is removed, proposals being decided on
    # the Studio's Model tab. These routes stay for the proposals that name no dataset (those
    # made before ADR-099 Amendment 3 among them) (ADR-143 decision 5: the administrator's promotion "remains only" for
    # those), with no screen of their own; the list names no other, in its query
    # (`test_link_type_routes.py`'s `test_the_administrators_list_holds_no_proposal_that_names_a_dataset`).
    r"^/v1/admin/link-types(/\{proposal_id\}/(promote|reject)|/retire)?$": (
        "the proposals naming no dataset, decided by the API alone since L2.7"
    ),
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


#: Routes a section's screen reads that are not the section's own, by route name: the sections
#: that read each, and why. Only these are passed over, and only for those sections: any other
#: route a screen calls must declare the section's right, so a route whose check is removed is found
#: (`test_a_route_with_its_check_removed_is_found`).
SHARED: dict[str, tuple[frozenset[str], str]] = {
    "get_handling_scheme_route": (
        frozenset({"people", "dashboards"}),
        "the deployment's classifications and handling codes, open to every signed-in person "
        "(People's access editor, Dashboards' clearance)",
    ),
    # The place test's exemption (ADR-145 Amendment 1): it computes run times from the cron text it
    # is sent and reads no store. It asks for `schedule_pipelines`, so a holder of
    # `operate_schedules` alone is shown Operations but refused its *Change schedule* preview.
    "schedule_preview_route": (
        frozenset({"operations"}),
        "Change schedule's preview, which reads no store (ADR-145 Amendment 1)",
    ),
}


def section_routes(
    root: Path, screen: str, routes: list[APIRoute], section: str | None = None
) -> list[APIRoute]:
    """The routes a section's screen calls that are its own: all but what `SHARED` names for it."""
    if section is None:
        section = next((s["id"] for s in built() if s["screen"] == screen), "")
    return [
        r
        for r in _reached(screen_fragments(root, screen), routes)
        if section not in SHARED.get(r.name, (frozenset(), ""))[0]
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
    assert unguarded(s["right"], _guarded_part(section, routes)) == []


#: A section that reads a reference catalogue any signed-in person may read
#: (`test_route_rights.py`'s `REFERENCE_CATALOGUES`), named here with exactly the routes it reads
#: so: opening the section needs its right, but the catalogue never did, so it cannot loosen it.
#: L2.7: Policies' Grading scheme, over `GET /v1/grading-scheme` (ADR-143 decision 11), alone.
REFERENCE_READS: dict[str, set[str]] = {"grading-scheme": {"/v1/grading-scheme"}}


def _guarded_part(section: str, routes: list[Any]) -> list[Any]:
    return [r for r in routes if r.path not in REFERENCE_READS.get(section, set())]


def test_a_section_reading_a_reference_catalogue_reads_it_and_nothing_unguarded() -> None:
    """Each section named in `REFERENCE_READS` calls exactly those routes, each one a reference
    catalogue of `test_route_rights.py` (so the exemption can neither hide another route nor name
    a route that holds a unit's data)."""
    from tests.services.api.test_route_rights import REFERENCE_CATALOGUES

    by_path = {r.path: r for r in _routes()}
    for section, paths in REFERENCE_READS.items():
        s = next(x for x in built() if x["id"] == section)
        walked = {r.path for r in section_routes(WORKSPACE_SRC, s["screen"], _routes())}
        assert walked == paths, (section, walked)
        assert {by_path[p].endpoint.__name__ for p in paths} <= REFERENCE_CATALOGUES


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
    routes = _guarded_part(section, section_routes(WORKSPACE_SRC, s["screen"], _routes()))
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
    # A section reading only a reference catalogue has none to refuse (`REFERENCE_READS`).
    assert answers or section in REFERENCE_READS, section
    assert all(code == 403 and why for _, code, why in answers), answers


def test_every_admin_route_is_some_section_s() -> None:
    routes = _routes()
    covered = {r.path for s in built() for r in section_routes(WORKSPACE_SRC, s["screen"], routes)}
    left = sorted({r.path for r in routes if r.path.startswith("/v1/admin/")} - covered)
    unexplained = [p for p in left if not any(re.search(rule, p) for rule in NOT_A_SECTION_S)]
    assert unexplained == []
    # Each recorded reason still names a route that exists and no section calls.
    for rule in NOT_A_SECTION_S:
        assert any(re.search(rule, p) for p in left), rule


def test_every_section_file_is_a_section_s_screen() -> None:
    screens = {s["screen"] for s in built()}
    folder = WORKSPACE_SRC / "admin/sections"
    under = {p.relative_to(WORKSPACE_SRC).as_posix() for p in folder.glob("*.tsx")
             if ".test." not in p.name}  # fmt: skip
    assert under <= screens


_SCREENS_BLOCK = re.compile(r"export const SCREENS\b.*?> = \{(.*?)\n\};", re.S)
_SCREEN_ENTRY = re.compile(r"^\s*\"?([\w-]+)\"?:\s*\(api\)\s*=>\s*<(\w+)\b", re.M)


def drawn_screens(text: str, path: Path) -> dict[str, str | None]:
    """For each id in `SCREENS`, the file its component is imported from (`None` if none)."""
    imported: dict[str, str | None] = {}
    for names, spec in _IMPORT.findall(text):
        for name in re.findall(r"(\w+)\s*(?:,|$)", names or ""):
            imported[name] = _resolve(path, spec, WORKSPACE_SRC)
    block = _SCREENS_BLOCK.search(text)
    assert block, "AdminPlace.tsx's SCREENS was not found"
    return {
        sid: imported.get(component) for sid, component in _SCREEN_ENTRY.findall(block.group(1))
    }


def test_admin_place_draws_each_section_from_its_declared_screen() -> None:
    """The route test reads `sections.json`'s screen; this holds what is drawn to it, so the two
    cannot drift (a hand-kept `SCREENS` drawing another file would pass every other test)."""
    drawn = drawn_screens(ADMIN_PLACE.read_text(), ADMIN_PLACE)
    assert drawn == {s["id"]: s["screen"] for s in built()}


def test_a_screens_entry_drawing_another_file_is_found() -> None:
    text = ADMIN_PLACE.read_text().replace(
        "operations: (api) => <Operations", "operations: (api) => <System"
    )
    assert "operations: (api) => <System" in text
    drawn = drawn_screens(text, ADMIN_PLACE)
    assert drawn["operations"] == "admin/sections/System.tsx"
    assert drawn != {s["id"]: s["screen"] for s in built()}


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


def test_each_shared_read_is_read_by_exactly_the_sections_named() -> None:
    routes = {r.name: r for r in _routes()}
    assert not _checks(routes["get_handling_scheme_route"]), "the handling scheme is no longer open"
    for name, (named, _) in SHARED.items():
        readers = {
            s["id"]
            for s in built()
            if routes[name]
            in _reached(screen_fragments(WORKSPACE_SRC, s["screen"]), [routes[name]])
        }
        assert readers == named, name


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
