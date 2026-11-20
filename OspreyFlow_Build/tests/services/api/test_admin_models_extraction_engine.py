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

from collections.abc import Iterable, Iterator
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from pydantic import BaseModel
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


class Smuggled(BaseModel):
    extraction_engine: str


class Wrapped(BaseModel):
    inner: Smuggled


class Plain(BaseModel):
    label: str


def _bodies(routes: Iterable[object]) -> tuple[list[tuple[list[str], str, str]], list[str]]:
    """Each write route under `/v1/admin/models` read for the models its body is: the ones FastAPI
    parses as typed parameters (`body: LimitsInput`), and the ones a route reads itself
    (`_model_admin_body(request, <Input>)`, or `<Input>.model_validate_json`). Returns the routes
    whose body has an `extraction_engine` field, and the routes whose body could not be read."""
    import inspect
    import re

    import schemas.model_admin as inputs

    taking: list[tuple[list[str], str, str]] = []
    unread: list[str] = []
    for r in routes:
        if not (isinstance(r, APIRoute) and r.path.startswith("/v1/admin/models")):
            continue
        if not set(r.methods) - {"GET", "HEAD"}:
            continue
        source = inspect.getsource(r.endpoint)
        names = re.findall(r"_model_admin_body\(request, (\w+)\)", source)
        names += re.findall(r"(\w+)\.model_validate_json\(", source)
        models = [getattr(inputs, n) for n in names]
        # A typed body parameter is a body however the route's own code reads (or does not read) it.
        models += [p.field_info.annotation for p in r.dependant.body_params]
        # A route with no `request` and no typed body reads no body at all (a delete, the test,
        # **Add** a check).
        takes_a_body = "request" in inspect.signature(r.endpoint).parameters
        if not models and takes_a_body:
            unread.append(r.path)
        for model in models:
            if "extraction_engine" in _fields(model):
                taking.append((sorted(r.methods), r.path, getattr(model, "__name__", str(model))))
    return taking, unread


def test_no_write_routes_body_takes_the_extraction_engine() -> None:
    """The lane-reviewer's item 16: not only no route by name, but no write route under
    `/v1/admin/models` whose body model (or any model inside it) has an `extraction_engine` field.
    A body is read from the route's typed parameters, and from its own code where it reads the
    request itself; a route that reads one it cannot be shown to read is named, never passed
    over."""
    taking, unread = _bodies(app.routes)
    assert taking == []
    assert unread == [], f"a write route whose body this test cannot read: {unread}"


def test_the_body_scan_sees_a_typed_body_and_a_body_read_by_hand() -> None:
    """Rule 15: the scan above shown red on planted routes, a scratch `FastAPI()` each. A typed
    body parameter with no `request` was once passed over; so was a route reading its own body."""
    from fastapi import FastAPI, Request

    scratch = FastAPI()

    @scratch.put("/v1/admin/models/typed")
    async def typed(body: Smuggled) -> None: ...

    @scratch.put("/v1/admin/models/wrapped")
    async def wrapped(body: Wrapped) -> None: ...

    @scratch.put("/v1/admin/models/harmless")
    async def harmless(body: Plain) -> None: ...

    @scratch.post("/v1/admin/models/by-hand")
    async def by_hand(request: Request) -> None: ...

    @scratch.delete("/v1/admin/models/nothing")
    async def nothing() -> None: ...

    taking, unread = _bodies(scratch.routes)
    assert sorted(path for _, path, _ in taking) == [
        "/v1/admin/models/typed",
        "/v1/admin/models/wrapped",
    ]
    assert unread == ["/v1/admin/models/by-hand"]
