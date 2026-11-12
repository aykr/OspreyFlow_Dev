"""The guides from Home (`06_DECISIONS.md` ADR-145 Amendment 10): `GET /v1/guides/{guide}` answers a
guide's PDF only to a principal whose rights open the place it belongs to (rules 3 and 4), refuses
everyone else in words, and answers the deployment's own file, byte for byte.

Who should be answered is computed here from `places.json` itself, the table the place switcher
and Home read, not from `guides.py`'s copy of it, so a wrong right in the Conduit's copy fails the
matrix below as well as the table's own comparison. Offline: the principal is stood in for (as
`test_place_routes.py` does), so the check under test is the route's alone. The same route signed
in with a real token, through the real `get_principal`, is `test_route_rights.py`'s live case.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from tools.layout import REPO as REPO_ROOT

from schemas.domain import Principal
from schemas.rights import LEGACY_ROLE_RIGHTS, ROLE_RIGHTS, SUPER_USER_PRESET, Right, rights_for

PLACES_JSON = REPO_ROOT / "apps/workspace/src/shell/places.json"
PDF_DIR = REPO_ROOT / "docs/pdf"
#: ADR-145 Amendment 10: which card each guide sits under. The architecture guide is not served.
GUIDE_PLACE = {"user": "glass", "developer": "ingest", "administration": "admin"}
GUIDE_FILE = {"user": "user-guide", "developer": "developer-guide",
              "administration": "administration-guide"}  # fmt: skip

#: The token roles each case signs in with, as `test_place_routes.py` signs in: the roles, the Super
#: user preset, the legacy roles, every right granted singly, and nobody's.
TOKEN_ROLES: dict[str, list[str]] = (
    {role: [role] for role in ROLE_RIGHTS}
    | {"super": list(SUPER_USER_PRESET)}
    | {role: [role] for role in LEGACY_ROLE_RIGHTS}
    | {f"right:{r.value}": [f"right:{r.value}"] for r in Right}
    | {"none": []}
)

#: What each named role reads (ADR-145 decision 7 and Amendment 4 decision 1's places, through
#: Amendment 10's cards): written out, so the computed matrix is itself checked against the ADR.
EXPECTED_GUIDES = {
    "analyst": {"user"},
    "data_engineer": {"user", "developer", "administration"},
    "osprey-admin": {"user", "administration"},
    "reports_viewer": {"user"},
    "rule_author": {"user"},
    "super": {"user", "developer", "administration"},
    "none": set(),
}


def _places() -> dict[str, dict[str, frozenset[str]]]:
    table = json.loads(PLACES_JSON.read_text(encoding="utf-8"))
    return {
        p["id"]: {"rights": frozenset(p["rights"]), "needs": frozenset(p.get("needs", []))}
        for p in table["places"]
    }


def _opens(place: str, roles: list[str]) -> bool:
    """`places.ts`'s `placesFor`, over `places.json`: one of the place's rights and all it needs."""
    held = {r.value for r in rights_for(roles)}
    entry = _places()[place]
    return bool(held & entry["rights"]) and entry["needs"] <= held


def _readable(roles: list[str]) -> set[str]:
    return {g for g, place in GUIDE_PLACE.items() if _opens(place, roles)}


@pytest.fixture
def as_who() -> Iterator[tuple[TestClient, list[Principal]]]:
    """A client whose requests are made as the principal last appended to the list."""
    from services.api.app import app, get_principal

    who: list[Principal] = []
    app.dependency_overrides[get_principal] = lambda: who[-1]
    try:
        # No lifespan: the route reads no store, and a route that did would answer 500, not pass.
        yield TestClient(app, raise_server_exceptions=False), who
    finally:
        app.dependency_overrides.pop(get_principal, None)


def _principal(name: str, roles: list[str]) -> Principal:
    return Principal(id=f"guide-{name}", clearance="SECRET", org_unit="unit-1", roles=roles)


# --- The table the Conduit holds is the places' own ----------------------------------------------


def test_the_conduit_s_place_rights_are_places_json_s() -> None:
    from services.api import guides

    places = _places()
    for place in ("glass", "ingest", "admin"):
        assert {r.value for r in guides.PLACE_RIGHTS[place]} == places[place]["rights"], place
        assert {r.value for r in guides.PLACE_NEEDS[place]} == places[place]["needs"], place
    assert {g: guide.place for g, guide in guides.GUIDES.items()} == GUIDE_PLACE


def test_the_named_roles_read_the_guides_adr_145_amendment_10_gives_them() -> None:
    for role, guides in EXPECTED_GUIDES.items():
        assert _readable(TOKEN_ROLES[role]) == guides, role


# --- Who is answered, and who refused (rule 4) ---------------------------------------------------


@pytest.mark.parametrize("role", sorted(TOKEN_ROLES))
def test_each_guide_answers_exactly_whom_its_place_opens(
    role: str, as_who: tuple[TestClient, list[Principal]]
) -> None:
    """For every role and every right granted singly, each guide: 200 and the PDF where the guide's
    place opens for them, 403 in words where it does not, never a byte of the file."""
    client, who = as_who
    who.append(_principal(role, TOKEN_ROLES[role]))
    readable = _readable(TOKEN_ROLES[role])
    for guide, place in GUIDE_PLACE.items():
        response = client.get(f"/v1/guides/{guide}", headers={"Authorization": "Bearer x"})
        if guide in readable:
            assert response.status_code == 200, (role, guide, response.text[:200])
            assert response.headers["content-type"] == "application/pdf"
            assert response.content.startswith(b"%PDF-")
        else:
            assert response.status_code == 403, (role, guide, response.status_code)
            assert not response.content.startswith(b"%PDF-")
            detail = response.json()["detail"]
            assert detail["error"] == "place_required" and detail["place"] == place
            assert "Ask an administrator" in detail["message"], detail


def test_a_custom_role_s_rights_count_as_single_grants(
    as_who: tuple[TestClient, list[Principal]],
) -> None:
    """`get_principal` adds a custom role's current rights as single grants (ADR-145 Amendment 5),
    so a custom role holding only `edit_pipelines` reads the developer guide and nothing else."""
    client, who = as_who
    who.append(_principal("custom", ["role:studio-only", "right:edit_pipelines"]))
    statuses = {g: client.get(f"/v1/guides/{g}").status_code for g in GUIDE_PLACE}
    assert statuses == {"user": 403, "developer": 200, "administration": 403}


def test_the_refusal_says_which_place_and_which_rights_open_it(
    as_who: tuple[TestClient, list[Principal]],
) -> None:
    client, who = as_who
    who.append(_principal("analyst", ["analyst"]))
    detail = client.get("/v1/guides/administration").json()["detail"]
    assert detail == {
        "error": "place_required",
        "place": "admin",
        "rights": sorted(_places()["admin"]["rights"]),
        "message": "The administration guide opens with Admin, which your roles do not open. "
        "Ask an administrator for a role that opens Admin.",
    }


def test_without_a_token_nothing_is_answered() -> None:
    from services.api.app import app

    response = TestClient(app, raise_server_exceptions=False).get("/v1/guides/user")
    assert response.status_code in (401, 403)
    assert not response.content.startswith(b"%PDF-")


@pytest.mark.parametrize("guide", ["architecture", "x", "user-guide", "..%2Fmanifest.json"])
def test_a_guide_that_is_not_one_of_the_three_is_not_found(
    guide: str, as_who: tuple[TestClient, list[Principal]]
) -> None:
    """The architecture guide is not served (ADR-145 Amendment 10), and no path reaches another
    file."""
    client, who = as_who
    who.append(_principal("super", list(SUPER_USER_PRESET)))
    response = client.get(f"/v1/guides/{guide}")
    assert response.status_code == 404, (guide, response.status_code)
    assert not response.content.startswith(b"%PDF-")


# --- The file served is the deployment's own ------------------------------------------------------


@pytest.mark.parametrize("guide", sorted(GUIDE_PLACE))
def test_the_pdf_served_is_byte_for_byte_the_file_carried(
    guide: str, as_who: tuple[TestClient, list[Principal]]
) -> None:
    """The bytes answered are the file in `docs/pdf/`, which is the PDF `manifest.json` records for
    its version: the guide this deployment was built with, not another copy of it."""
    client, who = as_who
    who.append(_principal("super", list(SUPER_USER_PRESET)))
    response = client.get(f"/v1/guides/{guide}")
    on_disk = (PDF_DIR / f"{GUIDE_FILE[guide]}.pdf").read_bytes()
    manifest = json.loads((PDF_DIR / "manifest.json").read_text(encoding="utf-8"))
    entry = manifest[f"{GUIDE_FILE[guide]}.md"]
    assert response.status_code == 200
    assert hashlib.sha256(response.content).hexdigest() == hashlib.sha256(on_disk).hexdigest()
    assert response.content == on_disk
    assert hashlib.sha256(on_disk).hexdigest() == entry["pdf"], "manifest out of step with the PDF"
    assert response.headers["x-guide-version"] == entry["version"]
    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["content-disposition"].startswith("inline")


def test_a_deployment_built_without_the_pdf_says_so(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    as_who: tuple[TestClient, list[Principal]],
) -> None:
    """A missing file is said in words (503), never answered as an empty or another document, and
    the place's check still comes first: a refused reader learns nothing about what is carried."""
    monkeypatch.setenv("OSPREY_GUIDES_DIR", str(tmp_path))
    client, who = as_who
    who.append(_principal("super", list(SUPER_USER_PRESET)))
    response = client.get("/v1/guides/user")
    assert response.status_code == 503
    assert response.json()["detail"]["error"] == "guide_not_carried"
    who.append(_principal("none", []))
    assert client.get("/v1/guides/user").status_code == 403


# --- The image carries what is served -------------------------------------------------------------


def _final_stage(dockerfile: Path) -> list[str]:
    lines = dockerfile.read_text(encoding="utf-8").splitlines()
    starts = [i for i, line in enumerate(lines) if line.strip().upper().startswith("FROM ")]
    return [line.strip() for line in lines[starts[-1] :]]


def test_the_conduit_image_carries_the_three_guides_and_their_manifest() -> None:
    """`services/api/Dockerfile`'s final stage copies the three PDFs and the manifest from the build
    context to `/app/docs/pdf/` (`guides.py`'s default folder, `parents[2] / docs / pdf` from
    `/app/services/api/guides.py`), and not the architecture guide."""
    copies = [
        line for line in _final_stage(REPO_ROOT / "services/api/Dockerfile")
        if line.upper().startswith("COPY ") and "--from=" not in line
    ]  # fmt: skip
    carried = [line for line in copies if "docs/pdf" in line]
    assert len(carried) == 1, carried
    tokens = [t for t in carried[0].split()[1:] if not t.startswith("--")]
    sources, target = tokens[:-1], tokens[-1]
    assert sorted(sources) == sorted(
        [f"docs/pdf/{name}.pdf" for name in GUIDE_FILE.values()] + ["docs/pdf/manifest.json"]
    )
    assert target in ("./docs/pdf/", "/app/docs/pdf/")
    from services.api import guides

    assert guides._DEFAULT_DIR == REPO_ROOT / "docs" / "pdf"
