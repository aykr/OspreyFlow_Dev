"""*Admin › Models* shows the extraction engine, read-only (`06_DECISIONS.md` ADR-135 Amendment 5
decision 2 and Amendment 9; the orchestrator's ruling of 11 November): it is chosen at set-up, in
`osprey.yaml`, and takes effect when the deployment is rendered again, so Admin shows what the
render made and offers no change (as P11's ruling: Admin never offers what the render did not
make).

- `GET /v1/admin/models` says which engine the deployment was rendered with (`extraction_engine`),
  read from what the render told the Conduit (`OSPREY_EXTRACTION_ENGINE`); `deep_read` when it says
  nothing.
- **No route writes it**: no method but GET under `/v1/admin/models` names the extraction engine.
- **Access (rule 4)**: the view is `manage_models`'s alone; anyone else is refused before it is
  read.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from services.api.app import app, get_principal
from services.api.model_admin import Installed

from schemas.domain import Principal
from tests.services.api.test_model_admin_routes import ADMIN, World

ANALYST = Principal(id="a-1", clearance="SECRET", org_unit="u", roles=["analyst"])


@pytest.fixture
def world(tmp_path: Path) -> Iterator[World]:
    w = World(tmp_path)
    app.state.model_admin = w.admin
    app.dependency_overrides[get_principal] = lambda: ADMIN
    yield w
    app.dependency_overrides.clear()
    app.state.model_admin = None


@pytest.mark.parametrize("engine", ["laurium", "deep_read"])
def test_the_view_says_which_engine_the_deployment_was_rendered_with(
    world: World, engine: str
) -> None:
    world.installed = replace(world.installed, extraction_engine=engine)
    world.admin = world.make_admin()
    app.state.model_admin = world.admin
    view = TestClient(app).get("/v1/admin/models")
    assert view.status_code == 200
    assert view.json()["extraction_engine"] == engine


@pytest.mark.parametrize(
    ("environ", "engine"),
    [({}, "deep_read"), ({"OSPREY_EXTRACTION_ENGINE": "deep_read"}, "deep_read"),
     ({"OSPREY_EXTRACTION_ENGINE": "laurium"}, "laurium")],
)  # fmt: skip
def test_installed_reads_what_the_render_told_the_conduit(
    world: World, environ: dict[str, str], engine: str
) -> None:
    from services.api.config import DeploymentModels

    assert Installed.from_env(DeploymentModels.from_env(), environ).extraction_engine == engine


def test_no_route_writes_the_extraction_engine() -> None:
    writes = [
        (sorted(r.methods), r.path)
        for r in app.routes
        if isinstance(r, APIRoute)
        and r.path.startswith("/v1/admin/models")
        and "extraction" in r.path
        and set(r.methods) - {"GET", "HEAD"}
    ]
    assert writes == []


def test_the_view_is_manage_models_alone(world: World) -> None:
    app.dependency_overrides[get_principal] = lambda: ANALYST
    assert TestClient(app).get("/v1/admin/models").status_code == 403


def _fields(annotation: object) -> set[str]:
    fields = getattr(annotation, "model_fields", None)
    if not isinstance(fields, dict):
        return set()
    names = set(fields)
    for field in fields.values():
        names |= _fields(field.annotation)
    return names


def test_no_write_routes_body_takes_the_extraction_engine() -> None:
    """The lane-reviewer's item 16: not only no route by name, but no write route under
    `/v1/admin/models` whose body model (or any model inside it) has an `extraction_engine` field.
    These routes read their bodies themselves (`_model_admin_body(request, <Input>)`, or
    `<Input>.model_validate_json`), so the input
    model is read from each route's own code; a route reading none is named, never passed over."""
    import inspect
    import re

    import schemas.model_admin as inputs

    taking, unread = [], []
    for r in app.routes:
        if not (isinstance(r, APIRoute) and r.path.startswith("/v1/admin/models")):
            continue
        if not set(r.methods) - {"GET", "HEAD"}:
            continue
        source = inspect.getsource(r.endpoint)
        names = re.findall(r"_model_admin_body\(request, (\w+)\)", source)
        names += re.findall(r"(\w+)\.model_validate_json\(", source)
        if not names and r.methods != {"DELETE"} and not r.path.endswith("/test"):
            unread.append(r.path)
        for name in names:
            if "extraction_engine" in _fields(getattr(inputs, name)):
                taking.append((sorted(r.methods), r.path, name))
    assert taking == []
    assert unread == [], f"a write route whose body this test cannot read: {unread}"
