"""*Admin › Maps*' routes (`06_DECISIONS.md` ADR-147), through the real app, the real right check
and the real logger:

- rule 4: every `/v1/admin/maps` and `/v1/admin/geospatial` route, found by walking the app's own
  routes (so a route added later is walked too), refuses a principal without `manage_geospatial`,
  an administrator holding every other administration right included, and changes nothing;
- the key (ADR-135 Amendment 2's rule): a recognisable planted key, sent through the real key route,
  and planted in a malformed body, a refused provider and an unknown provider's key route, is in no
  response, log record, audit entry or maps file; it reaches the tile proxy's upstream request only;
- the map follows *Admin › Maps* with no restart: `/v1/map/providers` lists a provider added there;
- a provider that needs a key and holds none answers its tiles in words, never an address.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from services.api import app as app_module
from services.api.app import app, get_principal
from services.api.map_admin import InMemoryMapAdminAudit, MapAdmin, MapKeyFile, MapSettingsFile

from schemas.domain import Principal
from schemas.mapconfig import MapConfig

PLANTED = "k-PLANTED-map-route-key-W4R2-do-not-leak"
PNG = b"\x89PNG\r\n\x1a\n synthetic tile"
ADMIN = Principal(id="admin-1", clearance="OFFICIAL", org_unit="u", roles=["osprey-admin"])
MAPS_ONLY = Principal(
    id="g-1", clearance="OFFICIAL", org_unit="u", roles=["right:manage_geospatial"]
)
#: Every administration right but this one, granted singly, and the admin role the geospatial
#: build and verify also check (kept, the orchestrator's settlement of 8 November).
EVERY_OTHER_ADMIN_RIGHT = Principal(
    id="admin-2",
    clearance="OFFICIAL",
    org_unit="u",
    roles=[
        f"right:{r}" for r in ("administer_system", "manage_people", "manage_models", "read_audit")
    ],
)
OSM = {
    "id": "osm-local", "label": "OpenStreetMap", "kind": "vector",
    "source": "file:///data/tiles/gb.pmtiles", "style": "bundled:osprey-dark",
    "attribution": "© OpenStreetMap contributors",
    "licence": {"id": "ODbL-1.0", "redistributable": True, "client_scope": "open"},
}  # fmt: skip
HOSTED = {
    "id": "hosted-tiles", "label": "Hosted tiles", "kind": "raster",
    "source": "https://tiles.example.test/{z}/{x}/{y}.png?key={credential}",
    "proxy": "required", "attribution": "Example",
    "licence": {"id": "example", "redistributable": False, "client_scope": "per-deployment"},
}  # fmt: skip
#: A body for each route the walk calls, so a refusal is the right check's and not the body's.
BODIES: dict[str, Any] = {
    "/v1/admin/maps/providers": {"provider": HOSTED},
    "/v1/admin/maps/providers/{provider_id}": {"provider": OSM},
    "/v1/admin/maps/providers/{provider_id}/key": {"key": PLANTED},
    "/v1/admin/maps/default": {"default": "osm-local"},
    "/v1/admin/maps/areas": {"areas": []},
    "/v1/admin/maps/schedule": {"schedule": {"every_hours": 6}},
    "/v1/admin/geospatial/build-basemap": {"region": "rutland"},
}


@pytest.fixture(autouse=True)
def _no_real_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every `.test` name resolves to nothing, as it should, whatever this network's resolver does;
    a case that needs a name to resolve inside says so itself."""
    from services.api import map_admin

    monkeypatch.setattr(map_admin, "resolve_host", lambda host: [])


class World:
    def __init__(self, tmp_path: Path) -> None:
        self.folder = tmp_path / "map-settings"
        self.audit = InMemoryMapAdminAudit()
        self.admin = MapAdmin(
            installed=MapConfig.model_validate({"default": "osm-local", "providers": [OSM]}),
            settings_file=MapSettingsFile(self.folder),
            key_file=MapKeyFile(self.folder),
            audit=self.audit,
            tiles_root=tmp_path / "tiles",
        )

    def kept(self) -> str:
        files = "".join(
            p.read_text() for p in self.folder.glob("*.yaml") if p.name != "map-keys.yaml"
        )
        return files + "".join(e.model_dump_json() for e in self.audit.entries)


@pytest.fixture
def world(tmp_path: Path) -> Iterator[World]:
    w = World(tmp_path)
    app.state.map_admin = w.admin
    app.dependency_overrides[get_principal] = lambda: ADMIN
    yield w
    app.dependency_overrides.clear()
    del app.state.map_admin


def _as(principal: Principal) -> None:
    app.dependency_overrides[get_principal] = lambda: principal


def _maps_routes() -> list[tuple[str, str]]:
    found = []
    for route in app.routes:
        if isinstance(route, APIRoute) and route.path.startswith(
            ("/v1/admin/maps", "/v1/admin/geospatial")
        ):
            found.extend((method, route.path) for method in sorted(route.methods))
    return found


def _call(client: TestClient, method: str, path: str) -> Any:
    url = path.replace("{provider_id}", "hosted-tiles")
    body = BODIES.get(path)
    if method in {"GET", "DELETE"} or body is None:
        return client.request(method, url)
    return client.request(method, url, content=json.dumps(body))


def test_the_walk_finds_every_maps_route() -> None:
    """Not vacuous: the walk below covers at least these (a removed one fails here)."""
    found = set(_maps_routes())
    for expected in [
        ("GET", "/v1/admin/maps"), ("GET", "/v1/admin/maps/history"),
        ("POST", "/v1/admin/maps/providers"), ("PUT", "/v1/admin/maps/providers/{provider_id}"),
        ("DELETE", "/v1/admin/maps/providers/{provider_id}"),
        ("PUT", "/v1/admin/maps/providers/{provider_id}/key"),
        ("DELETE", "/v1/admin/maps/providers/{provider_id}/key"),
        ("PUT", "/v1/admin/maps/default"), ("PUT", "/v1/admin/maps/areas"),
        ("PUT", "/v1/admin/maps/schedule"), ("POST", "/v1/admin/maps/prefetch"),
        ("POST", "/v1/admin/geospatial/build-basemap"), ("POST", "/v1/admin/geospatial/verify"),
    ]:  # fmt: skip
        assert expected in found, expected


@pytest.mark.parametrize("principal", [EVERY_OTHER_ADMIN_RIGHT], ids=["every-other-admin-right"])
def test_every_maps_route_refuses_a_principal_without_manage_geospatial(
    world: World, principal: Principal
) -> None:
    _as(principal)
    client = TestClient(app, raise_server_exceptions=False)
    for method, path in _maps_routes():
        response = _call(client, method, path)
        assert response.status_code == 403, (method, path, response.status_code)
        assert response.json()["detail"] == {
            "error": "right_required", "right": "manage_geospatial"
        }, (method, path)  # fmt: skip
    assert not world.folder.exists() and world.audit.entries == []


def test_a_holder_of_manage_geospatial_alone_manages_the_maps(world: World) -> None:
    _as(MAPS_ONLY)
    client = TestClient(app)
    added = client.post("/v1/admin/maps/providers", content=json.dumps({"provider": HOSTED}))
    assert added.status_code == 200, added.text
    assert [p["provider"]["id"] for p in added.json()["providers"]] == ["osm-local", "hosted-tiles"]
    # Build and verify also check the admin role (kept, the orchestrator's settlement): a holder of
    # the right alone is refused both, by the role, before anything runs.
    for path, body in (("verify", None), ("build-basemap", {"region": "rutland"})):
        answer = client.post(f"/v1/admin/geospatial/{path}", json=body)
        assert answer.status_code == 403 and "osprey-admin" in answer.text, path


def test_a_planted_key_is_in_no_response_log_audit_or_maps_file(
    world: World, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    client = TestClient(app, raise_server_exceptions=False)
    answers = [client.post("/v1/admin/maps/providers", content=json.dumps({"provider": HOSTED}))]
    answers.append(client.put("/v1/admin/maps/providers/hosted-tiles/key",
                              content=json.dumps({"key": PLANTED})))  # fmt: skip
    # The plants that a careless route would echo: a malformed body, an unknown provider, a refused
    # provider (the key pasted into its credential and into its label's place), a provider that
    # takes no key.
    answers += [
        client.put("/v1/admin/maps/providers/hosted-tiles/key",
                   content=json.dumps({"key": PLANTED, "extra": PLANTED})),
        client.put("/v1/admin/maps/providers/hosted-tiles/key", content=PLANTED),
        client.put("/v1/admin/maps/providers/nowhere/key", content=json.dumps({"key": PLANTED})),
        client.put("/v1/admin/maps/providers/osm-local/key", content=json.dumps({"key": PLANTED})),
        client.post("/v1/admin/maps/providers", content=json.dumps(
            {"provider": {**HOSTED, "id": "other", "credential": PLANTED}})),
        client.post("/v1/admin/maps/providers", content=json.dumps(
            {"provider": {**HOSTED, "id": "other", "credential_param": PLANTED}})),
        client.get("/v1/admin/maps"),
        client.get("/v1/admin/maps/history"),
        client.get("/v1/map/providers"),
    ]  # fmt: skip
    statuses = [a.status_code for a in answers]
    assert statuses == [200, 200, 422, 422, 404, 409, 422, 422, 200, 200, 200], statuses
    for answer in answers:
        assert PLANTED not in answer.text, answer.text
    assert all(PLANTED not in r.getMessage() for r in caplog.records)
    assert PLANTED not in world.kept()
    assert world.admin.key_for("hosted-tiles") == PLANTED
    view = answers[-3].json()
    assert (
        next(p for p in view["providers"] if p["provider"]["id"] == "hosted-tiles")["key_state"]
        == "set"
    )
    assert [e.action for e in world.audit.entries] == ["provider_added", "key_set"]


def test_the_tile_proxy_carries_the_admin_key_upstream_and_nowhere_else(
    world: World, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    asked: list[str] = []

    async def fetch(url: str) -> bytes:
        asked.append(url)
        return PNG

    monkeypatch.setattr(app_module, "fetch_tile", fetch)
    # The provider keeps no cache, so the route never reaches its storage.
    monkeypatch.setattr(app.state, "tile_cache_storage", None, raising=False)
    client = TestClient(app, raise_server_exceptions=False)
    client.post("/v1/admin/maps/providers", content=json.dumps({"provider": HOSTED}))

    refused = client.get("/v1/map/tiles/hosted-tiles/1/2/3")
    assert refused.status_code == 503 and "Admin › Maps" in refused.json()["detail"]
    assert "tiles.example.test" not in refused.text and asked == []

    client.put("/v1/admin/maps/providers/hosted-tiles/key", content=json.dumps({"key": PLANTED}))
    tile = client.get("/v1/map/tiles/hosted-tiles/1/2/3")

    assert tile.status_code == 200 and tile.content == PNG
    assert asked == [f"https://tiles.example.test/1/2/3.png?key={PLANTED}"]
    assert PLANTED not in tile.text and PLANTED not in json.dumps(dict(tile.headers))
    assert all(PLANTED not in r.getMessage() for r in caplog.records)


def test_the_map_follows_a_change_in_admin_with_no_restart(world: World) -> None:
    client = TestClient(app)
    before = client.get("/v1/map/providers").json()
    client.post("/v1/admin/maps/providers", content=json.dumps({"provider": HOSTED}))
    client.put("/v1/admin/maps/default", content=json.dumps({"default": "hosted-tiles"}))
    after = client.get("/v1/map/providers").json()
    assert [p["id"] for p in before["providers"]] == ["osm-local"]
    assert [p["id"] for p in after["providers"]] == ["osm-local", "hosted-tiles"]
    assert after["default"] == "hosted-tiles"


def test_an_area_over_the_cap_is_refused_in_words_through_the_route(world: World) -> None:
    client = TestClient(app)
    client.post("/v1/admin/maps/providers", content=json.dumps(
        {"provider": {**HOSTED, "cache": {"ttl_days": 30}}}))  # fmt: skip
    big = {"name": "Everywhere", "provider_id": "hosted-tiles", "west": -10, "south": 49,
           "east": 3, "north": 60, "zoom_min": 0, "zoom_max": 15}  # fmt: skip
    answer = client.put("/v1/admin/maps/areas", content=json.dumps({"areas": [big]}))
    assert answer.status_code == 422
    assert "tiles over its zooms" in answer.json()["detail"]["detail"]


# --- What Admin may name (the review's blocker): an `env:` reference to any of the Conduit's
# --- secrets, or an address inside the deployment, from a holder of `manage_geospatial` alone.


@pytest.mark.parametrize(
    "credential", ["env:POSTGRES_PASSWORD", "env:OIDC_TOKEN_EXCHANGE_CLIENT_SECRET", "env:MAP_KEY"]
)
def test_admin_never_names_an_environment_variable_for_a_provider_s_key(
    world: World, credential: str
) -> None:
    client = TestClient(app)
    answer = client.post("/v1/admin/maps/providers", content=json.dumps(
        {"provider": {**HOSTED, "id": "exfil", "credential": credential}}))  # fmt: skip
    assert answer.status_code == 422, answer.text
    assert "Admin › Maps" in answer.json()["detail"]["detail"]
    assert credential.removeprefix("env:") not in answer.text
    assert world.admin.config().providers[-1].id == "osm-local" and world.audit.entries == []


def test_an_installer_s_reference_is_kept_by_an_edit_and_never_changed_by_one(
    world: World, tmp_path: Path
) -> None:
    installed = {**HOSTED, "credential": "env:OS_DATAHUB_API_KEY"}
    world.admin._installed = MapConfig.model_validate(  # noqa: SLF001 - the installer's osprey.yaml
        {"default": "osm-local", "providers": [OSM, installed]}
    )
    client = TestClient(app)
    kept = client.put("/v1/admin/maps/providers/hosted-tiles", content=json.dumps(
        {"provider": {**installed, "label": "Renamed"}}))  # fmt: skip
    assert kept.status_code == 200, kept.text
    changed = client.put("/v1/admin/maps/providers/hosted-tiles", content=json.dumps(
        {"provider": {**installed, "credential": "env:POSTGRES_PASSWORD"}}))  # fmt: skip
    assert changed.status_code == 422 and "POSTGRES" not in changed.text


@pytest.mark.parametrize(
    "address",
    [
        "http://localhost/{z}/{x}/{y}.png", "http://127.0.0.1:2480/{z}/{x}/{y}",
        "http://[::1]/{z}/{x}/{y}", "http://169.254.169.254/latest/meta-data/{z}/{x}/{y}",
        "http://10.0.0.5/{z}/{x}/{y}", "http://172.18.0.4:5432/{z}/{x}/{y}",
        "http://192.168.1.10/{z}/{x}/{y}", "http://postgres:5432/{z}/{x}/{y}",
        "http://keycloak/{z}/{x}/{y}", "https://{host}/{z}/{x}/{y}", "ftp://tiles.example.test/{z}",
        "file:///etc/passwd", "file:///data/tiles/../../etc/passwd", "gopher://tiles.example.test/",
        "https://user:pw@tiles.example.test/{z}/{x}/{y}",
    ],
)  # fmt: skip
def test_admin_never_points_the_conduit_inside_the_deployment(world: World, address: str) -> None:
    client = TestClient(app)
    answer = client.post("/v1/admin/maps/providers", content=json.dumps(
        {"provider": {**HOSTED, "id": "inside", "source": address}}))  # fmt: skip
    assert answer.status_code == 422, (address, answer.text)
    assert world.audit.entries == []


@pytest.mark.parametrize(
    "address",
    ["https://tiles.example.test/{z}/{x}/{y}.png?key={credential}",
     "http://gis.corp.example.test/tiles/{z}/{x}/{y}.png?key={credential}"],
)  # fmt: skip
def test_a_named_host_outside_the_deployment_is_taken(world: World, address: str) -> None:
    client = TestClient(app)
    answer = client.post("/v1/admin/maps/providers", content=json.dumps(
        {"provider": {**HOSTED, "id": "outside", "source": address}}))  # fmt: skip
    assert answer.status_code == 200, answer.text


def test_a_wmts_endpoint_is_held_to_the_same_rule(world: World) -> None:
    wmts = {**HOSTED, "id": "w", "source": None, "service": "wmts", "layer": "a",
            "tile_matrix_set": "GM", "format": "image/png", "wmts_style": "default",
            "endpoint": "http://arcadedb:2480/wmts"}  # fmt: skip
    answer = TestClient(app).post(
        "/v1/admin/maps/providers", content=json.dumps({"provider": wmts})
    )
    assert answer.status_code == 422


def test_a_key_is_never_given_to_a_provider_the_browser_fetches(world: World) -> None:
    client = TestClient(app)
    answer = client.post("/v1/admin/maps/providers", content=json.dumps(
        {"provider": {**HOSTED, "id": "browser", "proxy": "none"}}))  # fmt: skip
    assert answer.status_code == 422 and "browser" in answer.json()["detail"]["detail"]


# --- The independent review's blocker: an installer's `env:` key, pointed elsewhere by an edit


def test_an_installer_s_key_never_follows_an_edit_to_another_host(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The reviewer's plant, exactly: a holder of `manage_geospatial` edits an `osprey.yaml`
    provider carrying `env:OS_DATAHUB_API_KEY` to point at a host of their choosing; the next tile
    would have carried the installer's key there. An edit that changes the address of a provider
    with a key from the installer's settings is refused in words, and the tile proxy is never given
    that key for any address but the installer's."""
    monkeypatch.setenv("OS_DATAHUB_API_KEY", PLANTED)
    installed = {**HOSTED, "credential": "env:OS_DATAHUB_API_KEY"}
    world.admin._installed = MapConfig.model_validate(  # noqa: SLF001 - the installer's osprey.yaml
        {"default": "osm-local", "providers": [OSM, installed]}
    )
    asked: list[str] = []

    async def fetch(url: str) -> bytes:
        asked.append(url)
        return PNG

    monkeypatch.setattr(app_module, "fetch_tile", fetch)
    monkeypatch.setattr(app.state, "tile_cache_storage", None, raising=False)
    client = TestClient(app, raise_server_exceptions=False)
    moved = {**installed, "source": "https://attacker.example/{z}/{x}/{y}?k={credential}"}
    answer = client.put(
        "/v1/admin/maps/providers/hosted-tiles", content=json.dumps({"provider": moved})
    )
    assert answer.status_code == 422, answer.text
    assert "osprey.yaml" in answer.json()["detail"]["detail"]
    client.get("/v1/map/tiles/hosted-tiles/1/2/3")
    assert asked and all(u.startswith("https://tiles.example.test/") for u in asked)
    assert not any("attacker" in u for u in asked)


def test_a_maps_file_written_outside_admin_never_moves_an_installer_s_key(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A restored or hand-edited maps file is held to what Admin may name: a provider there
    carrying an installer's `env:` reference to another address, or one `osprey.yaml` never gave,
    has none."""
    monkeypatch.setenv("OS_DATAHUB_API_KEY", PLANTED)
    installed = {**HOSTED, "credential": "env:OS_DATAHUB_API_KEY"}
    world.admin._installed = MapConfig.model_validate(  # noqa: SLF001
        {"default": "osm-local", "providers": [OSM, installed]}
    )
    world.folder.mkdir(parents=True, exist_ok=True)
    edited = {**installed, "source": "https://attacker.example/{z}/{x}/{y}?k={credential}"}
    other = {**HOSTED, "id": "other", "credential": "env:POSTGRES_PASSWORD"}
    import yaml

    (world.folder / "maps.yaml").write_text(yaml.safe_dump(
        {"map": {"default": "osm-local", "providers": [OSM, edited, other]}}))  # fmt: skip
    from services.api.tile_proxy import MissingMapKeyError, build_upstream_url

    for provider_id in ("hosted-tiles", "other"):
        provider = world.admin.provider(provider_id)
        assert provider.credential is None, provider_id
        with pytest.raises(MissingMapKeyError):
            build_upstream_url(provider, 1, 2, 3, key=world.admin.key_for(provider_id))


# --- The independent review's must-fix 2: the host check, bypassed -------------------------------


@pytest.mark.parametrize(
    "address",
    [
        "http://1{z}7.0.0.1/{z}/{x}/{y}.png",  # 107.0.0.1 with "0", 127.0.0.1 at zoom 2
        "https://tiles.example.test:{z}/{z}/{x}/{y}.png", "http://127.1/{z}/{x}/{y}",
        "http://0x7f.1/{z}/{x}/{y}", "http://169.254.43518/{z}/{x}/{y}",
        "http://2130706433/{z}/{x}/{y}", "http://postgres./{z}/{x}/{y}",
        "http://keycloak.:8080/{z}/{x}/{y}",
    ],
)  # fmt: skip
def test_the_host_check_is_not_bypassed(world: World, address: str) -> None:
    answer = TestClient(app).post("/v1/admin/maps/providers", content=json.dumps(
        {"provider": {**HOSTED, "id": "bypass", "source": address}}))  # fmt: skip
    assert answer.status_code == 422, (address, answer.text)


@pytest.mark.parametrize(
    "resolved", ["127.0.0.1", "10.0.0.5", "169.254.169.254", "::1", "172.18.0.4"]
)
def test_a_name_that_resolves_inside_is_refused_at_save(
    world: World, monkeypatch: pytest.MonkeyPatch, resolved: str
) -> None:
    from services.api import map_admin

    monkeypatch.setattr(map_admin, "resolve_host", lambda host: [resolved])
    answer = TestClient(app).post("/v1/admin/maps/providers", content=json.dumps(
        {"provider": {**HOSTED, "id": "rebind"}}))  # fmt: skip
    assert answer.status_code == 422 and "resolves inside" in answer.json()["detail"]["detail"]


def test_a_name_that_resolves_inside_by_the_time_of_a_fetch_is_not_fetched(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """DNS can change between save and fetch: an Admin-added provider's host is looked up again
    before each tile, and one that now resolves inside is refused in words, never fetched."""
    from services.api import map_admin

    asked: list[str] = []

    async def fetch(url: str) -> bytes:
        asked.append(url)
        return PNG

    monkeypatch.setattr(app_module, "fetch_tile", fetch)
    monkeypatch.setattr(app.state, "tile_cache_storage", None, raising=False)
    client = TestClient(app, raise_server_exceptions=False)
    plain = {**HOSTED, "id": "rebind", "source": "https://tiles.example.test/{z}/{x}/{y}.png"}
    assert (
        client.post("/v1/admin/maps/providers", content=json.dumps({"provider": plain})).status_code
        == 200
    )
    assert client.get("/v1/map/tiles/rebind/1/2/3").status_code == 200

    monkeypatch.setattr(map_admin, "resolve_host", lambda host: ["127.0.0.1"])
    answer = client.get("/v1/map/tiles/rebind/1/2/3")
    assert answer.status_code == 502 and "inside this deployment" in answer.json()["detail"]
    assert len(asked) == 1


# --- The independent review's should-fixes ------------------------------------------------------


@pytest.mark.parametrize(
    "address",
    ["https://tiles.example.test/{z}/{x}/{y}.png?key=k-PLANTED-pasted-1234",
     "https://tiles.example.test/{z}/{x}/{y}.png?access_token=pasted",
     "https://tiles.example.test/{z}/{x}/{y}.png?layer=a&apiKey=pasted"],
)  # fmt: skip
def test_a_key_typed_into_the_address_is_refused_pointing_to_enter_key(
    world: World, address: str
) -> None:
    answer = TestClient(app).post("/v1/admin/maps/providers", content=json.dumps(
        {"provider": {**HOSTED, "id": "pasted", "source": address}}))  # fmt: skip
    assert answer.status_code == 422 and "Enter key" in answer.json()["detail"]["detail"]
    assert "pasted" not in answer.json()["detail"]["detail"].replace("'pasted'", "")


@pytest.mark.parametrize("hours", [1, 5, 12, 48])
def test_the_schedule_is_six_hours_a_day_or_a_week(world: World, hours: int) -> None:
    answer = TestClient(app).put("/v1/admin/maps/schedule", content=json.dumps(
        {"schedule": {"every_hours": hours}}))  # fmt: skip
    assert answer.status_code == 422
