"""HTTP route wiring for `/v1/investigations/{id}/sites/*` —
`spec/00_ARCHITECTURE.md` §1.2, `08_ACCEPTANCE_SCENARIOS.md` A1. Mirrors
`test_app.py`'s own discipline: dependency overrides and monkeypatched
module-level helpers, never a live ArcadeDB/Postgres/MinIO — `SiteStore`'s
own correctness is proven in `test_sites_store.py`, the connector +
recipe's in `tests/ingest/test_site_grid_recipe_end_to_end.py`; what
belongs here is only "does the right dependency's result end up in the
right response, with the right status code"."""

from __future__ import annotations

import struct
from datetime import UTC, datetime
from types import SimpleNamespace

import duckdb
import pytest
from fastapi.testclient import TestClient
from services.api.app import (
    ControlPointQuad,
    app,
    get_analytics,
    get_audit,
    get_graph,
    get_investigations,
    get_ontology,
    get_principal,
    get_site_image_storage,
    get_sites,
)
from services.api.sites import ControlPointRecord, Site, SiteNotFoundError

from adapters.analytics_duckdb.adapter import AnalyticsDuckDBAdapter
from adapters.analytics_duckdb.schema import create_events_table, create_geometries_table
from ontology.handling import load_uk_le_scheme
from schemas.domain import Handling, Principal
from tests.services.api.test_app import _FakeAudit, _FakeInvestigations

PRINCIPAL = Principal(id="analyst-1", clearance="OFFICIAL", org_unit="unit-1")

_CONTROL_POINTS: ControlPointQuad = (
    ControlPointRecord(px=0, py=0, lon=-1.836, lat=52.409),
    ControlPointRecord(px=1000, py=0, lon=-1.834, lat=52.409),
    ControlPointRecord(px=1000, py=1000, lon=-1.834, lat=52.408),
    ControlPointRecord(px=0, py=1000, lon=-1.836, lat=52.408),
)


def _png_bytes(width: int, height: int) -> bytes:
    signature = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">I", 13) + b"IHDR" + struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return signature + ihdr + b"\x00\x00\x00\x00"


def _site(**overrides: object) -> Site:
    defaults: dict[str, object] = {
        "id": "site-1",
        "investigation_id": "inv-1",
        "owning_unit": "unit-1",
        "created_at": datetime(2026, 1, 1, tzinfo=UTC),
        "created_by": "analyst-1",
        "label": "HMP Hollywood aerial",
        "image_object_key": "sites/site-1/image",
        "image_width_px": 2000,
        "image_height_px": 1500,
    }
    defaults.update(overrides)
    return Site(**defaults)  # type: ignore[arg-type]


class _FakeSites:
    def __init__(self, site: Site | None = None) -> None:
        self.site = site
        self.set_control_points_calls: list[tuple[str, ControlPointQuad]] = []
        self.set_grid_calls: list[tuple[str, int, int]] = []

    async def create(self, principal: Principal, **kwargs: object) -> Site:
        self.site = _site(**{**kwargs, "owning_unit": principal.org_unit})  # type: ignore[arg-type]
        return self.site

    async def get_authorized(self, site_id: str, principal: Principal) -> Site:
        if self.site is None or self.site.id != site_id:
            raise SiteNotFoundError(site_id)
        if self.site.owning_unit != principal.org_unit:
            raise SiteNotFoundError(site_id)
        return self.site

    async def set_control_points(
        self, site_id: str, principal: Principal, control_points: ControlPointQuad
    ) -> Site:
        self.set_control_points_calls.append((site_id, control_points))
        assert self.site is not None
        self.site = self.site.model_copy(update={"control_points": control_points})
        return self.site

    async def set_grid(self, site_id: str, principal: Principal, *, rows: int, cols: int) -> Site:
        self.set_grid_calls.append((site_id, rows, cols))
        assert self.site is not None
        self.site = self.site.model_copy(update={"grid_rows": rows, "grid_cols": cols})
        return self.site


class _FakeGraph:
    """Only the transaction lifecycle the `set_grid` route drives directly
    — `run_recipe` itself is monkeypatched in the tests that reach it, so
    this never needs to behave like a real `GraphPort`."""

    def __init__(self) -> None:
        self.committed = False
        self.rolled_back = False
        #: Round 13cf: the grid route now reads back each cell `Location` the recipe made and
        #: moves its ref (R9 (b)), and writes geocode edges (R10). `run_recipe` is still
        #: monkeypatched, so this stands in for "the recipe created one node per site_ref".
        #: The real graph's behaviour is proven over the wire, not here.
        self.nodes: dict[str, SimpleNamespace] = {}
        self.node_writes: list[object] = []
        self.edge_writes: list[object] = []

    async def find_node(
        self, entity_type: str, key: str, value: str, principal: object
    ) -> SimpleNamespace:
        return self.nodes.setdefault(
            value,
            SimpleNamespace(
                id=f"node-{value}",
                type=entity_type,
                properties={"site_ref": value, "geometry_ref": "geo:point-shaped"},
                handling=Handling(
                    classification="OFFICIAL", handling_code="P", owning_unit="unit-1",
                    originator="unit-1",
                ),
            ),
        )

    async def upsert_nodes(self, writes: list[object], tx: str) -> list[str]:
        self.node_writes.extend(writes)
        for write in writes:
            node = self.nodes[write.properties["site_ref"]]  # type: ignore[attr-defined]
            node.properties = dict(write.properties)  # type: ignore[attr-defined]
        return [w.id for w in writes]  # type: ignore[attr-defined]

    async def upsert_edges(self, writes: list[object], tx: str) -> list[str]:
        self.edge_writes.extend(writes)
        return [w.id for w in writes]  # type: ignore[attr-defined]

    async def begin_transaction(self) -> str:
        return "tx-1"

    async def commit_transaction(self, tx: str) -> None:
        self.committed = True

    async def rollback_transaction(self, tx: str) -> None:
        self.rolled_back = True


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    sites = _FakeSites()
    graph = _FakeGraph()
    written_images: list[tuple[bytes, str]] = []

    def fake_write_site_image(data: bytes, *, storage: object, object_key: str) -> None:
        written_images.append((data, object_key))

    def fake_read_site_image(*, storage: object, object_key: str) -> bytes:
        return _png_bytes(2000, 1500)

    async def fake_run_recipe(
        recipe: object, rows: object, **kwargs: object
    ) -> tuple[object, list[object]]:
        class _Report:
            nodes_created = len(list(rows))  # type: ignore[arg-type]
            rejections: list[object] = []

        return _Report(), []

    monkeypatch.setattr("services.api.app.write_site_image", fake_write_site_image)
    monkeypatch.setattr("services.api.app.read_site_image", fake_read_site_image)
    monkeypatch.setattr("services.api.app.run_recipe", fake_run_recipe)
    # **The real recipe, not a stand-in — round 13cde.** The grid route now reads the recipe's
    # own `connector.source_crs` and `defaults.handling` to load each cell's geometry, so an
    # `object()` here stopped fitting the route the moment it did something with the recipe.

    # **A real analytics store, in memory — round 13cde.** The grid route loads a
    # `GeometryRecord` per cell through `AnalyticsPort`; a fake would prove the route calls a
    # method, not that a cell's ref resolves afterwards.
    analytics_con = duckdb.connect(":memory:")
    create_events_table(analytics_con)
    create_geometries_table(analytics_con)
    analytics = AnalyticsDuckDBAdapter(analytics_con, load_uk_le_scheme())

    app.dependency_overrides[get_principal] = lambda: PRINCIPAL
    app.dependency_overrides[get_sites] = lambda: sites
    app.dependency_overrides[get_graph] = lambda: graph
    app.dependency_overrides[get_ontology] = lambda: object()
    app.dependency_overrides[get_site_image_storage] = lambda: object()
    app.dependency_overrides[get_audit] = lambda: _FakeAudit()
    app.dependency_overrides[get_analytics] = lambda: analytics

    # `AuthorizedInvestigationDep` on `create_site` needs `investigations`
    # too — reuse `test_app.py`'s own fake rather than a third copy.
    app.dependency_overrides[get_investigations] = lambda: _FakeInvestigations()

    test_client = TestClient(app)
    test_client.sites = sites  # type: ignore[attr-defined]
    test_client.graph = graph  # type: ignore[attr-defined]
    test_client.written_images = written_images  # type: ignore[attr-defined]
    test_client.analytics_con = analytics_con  # type: ignore[attr-defined]
    try:
        yield test_client
    finally:
        app.dependency_overrides.clear()


def test_create_site_uploads_the_image_and_creates_the_record(client: TestClient) -> None:
    response = client.post(
        "/v1/investigations/inv-1/sites",
        data={"label": "HMP Hollywood aerial"},
        files={"image": ("site.png", _png_bytes(2000, 1500), "image/png")},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["image_width_px"] == 2000
    assert body["image_height_px"] == 1500
    assert body["control_points"] is None
    assert len(client.written_images) == 1  # type: ignore[attr-defined]


def test_create_site_rejects_an_unsupported_image_format(client: TestClient) -> None:
    response = client.post(
        "/v1/investigations/inv-1/sites",
        data={"label": "HMP Hollywood aerial"},
        files={"image": ("site.gif", b"GIF89a" + b"\x00" * 20, "image/gif")},
    )

    assert response.status_code == 422
    assert response.json()["error"] == "unsupported_image_format"


def test_get_site_returns_404_for_a_site_in_a_different_unit(client: TestClient) -> None:
    client.sites.site = _site(owning_unit="unit-2")  # type: ignore[attr-defined]

    response = client.get("/v1/investigations/inv-1/sites/site-1")

    assert response.status_code == 404
    assert response.json()["error"] == "site_not_found"


def test_get_site_returns_404_when_the_site_belongs_to_a_different_investigation(
    client: TestClient,
) -> None:
    client.sites.site = _site(investigation_id="inv-2")  # type: ignore[attr-defined]

    response = client.get("/v1/investigations/inv-1/sites/site-1")

    assert response.status_code == 404
    assert response.json()["error"] == "site_not_found"


def test_set_control_points_requires_exactly_four(client: TestClient) -> None:
    client.sites.site = _site()  # type: ignore[attr-defined]

    response = client.patch(
        "/v1/investigations/inv-1/sites/site-1/control-points",
        json={"control_points": [cp.model_dump() for cp in _CONTROL_POINTS[:3]]},
    )

    assert response.status_code == 422


def test_set_control_points_updates_the_site_and_audits(client: TestClient) -> None:
    client.sites.site = _site()  # type: ignore[attr-defined]

    response = client.patch(
        "/v1/investigations/inv-1/sites/site-1/control-points",
        json={"control_points": [cp.model_dump() for cp in _CONTROL_POINTS]},
    )

    assert response.status_code == 200
    assert response.json()["control_points"] is not None
    assert client.sites.set_control_points_calls  # type: ignore[attr-defined]


def test_grid_cannot_be_set_before_control_points(client: TestClient) -> None:
    client.sites.site = _site()  # type: ignore[attr-defined]

    response = client.post(
        "/v1/investigations/inv-1/sites/site-1/grid", json={"rows": 10, "cols": 10}
    )

    assert response.status_code == 422


def test_grid_runs_the_recipe_and_returns_the_updated_site(client: TestClient) -> None:
    client.sites.site = _site(control_points=_CONTROL_POINTS)  # type: ignore[attr-defined]

    response = client.post(
        "/v1/investigations/inv-1/sites/site-1/grid", json={"rows": 2, "cols": 2}
    )

    assert response.status_code == 200
    body = response.json()
    assert (body["grid_rows"], body["grid_cols"]) == (2, 2)
    assert client.graph.committed  # type: ignore[attr-defined]
    assert not client.graph.rolled_back  # type: ignore[attr-defined]

    # Rounds 13cde/13cf: every cell's geometry is loaded as a polygon, none as a point, and a
    # redraw loads nothing more (R9 (a)).
    con = client.analytics_con  # type: ignore[attr-defined]
    kinds = "SELECT kind, count(*) FROM geometries GROUP BY kind"
    assert con.execute(kinds).fetchall() == [("polygon", 4)]
    again = client.post("/v1/investigations/inv-1/sites/site-1/grid", json={"rows": 2, "cols": 2})
    assert again.status_code == 200, again.text
    assert con.execute(kinds).fetchall() == [("polygon", 4)]


def test_grid_moves_each_cell_ref_to_its_polygon_and_geocodes_incidents(
    client: TestClient,
) -> None:
    """**R9 (b), R9 (c) and R10, in process — round 13cf.** A cell drawn with the old
    point-shaped ref keeps its node and gets the polygon's ref. An incident with a point inside a
    cell records that cell and gains a `PRESENT_AT` edge to it, carrying the incident's own
    handling. One outside the site is untouched. A redraw writes no second edge and moves nothing.
    """
    client.sites.site = _site(control_points=_CONTROL_POINTS)  # type: ignore[attr-defined]
    con = client.analytics_con  # type: ignore[attr-defined]
    incidents = [
        # r0-c0 is the north-west quarter of the quad; r0-c1 north-east; r1-c1 south-east.
        ("inc-nw", -1.8355, 52.4088, "OFFICIAL", "hmp-intel"),
        ("inc-se", -1.8345, 52.4082, "OFFICIAL", "unit-1"),
        ("inc-secret", -1.8345, 52.4088, "SECRET", "unit-1"),
        ("inc-out", -1.8, 52.5, "OFFICIAL", "unit-1"),
    ]
    for event_id, lon, lat, classification, originator in incidents:
        con.execute(
            "INSERT INTO events (event_id, edge_id, edge_type, source_id, target_id, "
            "occurred_at, lat, lon, properties, investigation_scope, handling_classification, "
            "handling_code, owning_unit, originator) VALUES (?, ?, 'PRESENT_AT', ?, 'yard-a', "
            "TIMESTAMP '2026-01-05 10:00:00', ?, ?, '{}', 'inv-1', ?, 'P', 'unit-1', ?)",
            [event_id, f"edge-{event_id}", f"person-{event_id}", lat, lon, classification,
             originator],
        )

    grid = {"rows": 2, "cols": 2}
    response = client.post("/v1/investigations/inv-1/sites/site-1/grid", json=grid)
    assert response.status_code == 200, response.text

    graph = client.graph  # type: ignore[attr-defined]
    moved = {w.properties["site_ref"]: w.properties["geometry_ref"] for w in graph.node_writes}
    assert set(moved) == {f"site-1-r{r}-c{c}" for r in range(2) for c in range(2)}
    stored_refs = {row[0] for row in con.execute("SELECT geometry_ref FROM geometries").fetchall()}
    assert set(moved.values()) == stored_refs, "a Location's ref does not name its polygon"

    cell_of = dict(
        con.execute(
            "SELECT event_id, json_extract_string(properties, '$.site_cell') FROM events"
        ).fetchall()
    )
    # The SECRET incident is inside r0-c1 but invisible to this OFFICIAL analyst, so their draw
    # neither geocodes it nor writes an edge for it: access applies to this path like any read.
    assert cell_of == {
        "inc-nw": "node-site-1-r0-c0",
        "inc-se": "node-site-1-r1-c1",
        "inc-secret": None,
        "inc-out": None,
    }
    # Each edge carries its incident's handling, not the cell's (whose originator is unit-1).
    edges = {(w.source, w.target, w.handling.originator) for w in graph.edge_writes}
    assert edges == {
        ("person-inc-nw", "node-site-1-r0-c0", "hmp-intel"),
        ("person-inc-se", "node-site-1-r1-c1", "unit-1"),
    }

    again = client.post("/v1/investigations/inv-1/sites/site-1/grid", json={"rows": 2, "cols": 2})
    assert again.status_code == 200, again.text
    assert len(graph.edge_writes) == 2, "a redraw wrote a second occurrence to an edge"
    assert len(graph.node_writes) == 4, "a redraw moved a ref that had already moved"


def test_get_site_image_returns_the_bytes_with_the_right_content_type(client: TestClient) -> None:
    client.sites.site = _site()  # type: ignore[attr-defined]

    response = client.get("/v1/investigations/inv-1/sites/site-1/image")

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
