"""SE4 item 1 (C016): the map administration's address check judges the same ranges the connector
reads do (`schemas.sources.address_is_inside`).

`map_admin._is_inside` unwrapped an IPv4-mapped IPv6 address and asked Python's own predicates,
which call shared space (100.64.0.0/10) global, and which do not look inside NAT64 (64:ff9b::/96)
or 6to4 (2002::/16) addresses. A holder of `manage_geospatial` could therefore point the Conduit's
tile proxy at an address that is, or carries, one inside the deployment's network.

Planted in the shape the code meets: a URL host through the real route (brackets for IPv6), and the
host as `host_inside` gets it. Rule 15 controls: a public address is not inside, and every address
the existing route tests refuse is still refused.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from services.api import map_admin
from services.api.app import app, get_principal
from services.api.map_admin import InMemoryMapAdminAudit, MapAdmin, MapKeyFile, MapSettingsFile

from schemas.domain import Principal
from schemas.mapconfig import MapConfig
from schemas.sources import address_is_inside

ADMIN = Principal(id="admin-1", clearance="OFFICIAL", org_unit="u", roles=["osprey-admin"])
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

#: The three ranges the old check missed, each as a literal host (an IPv6 one in a URL's brackets).
MISSED = [
    pytest.param("100.64.3.2", "100.64.3.2", id="shared-space"),
    pytest.param("64:ff9b::a9fe:a9fe", "[64:ff9b::a9fe:a9fe]", id="nat64-carrying-link-local"),
    pytest.param("2002:7f00:1::", "[2002:7f00:1::]", id="6to4-carrying-loopback"),
]
#: What the existing route tests refuse today: still inside.
REFUSED_TODAY = [
    pytest.param("127.0.0.1", "127.0.0.1", id="loopback"),
    pytest.param("::1", "[::1]", id="ipv6-loopback"),
    pytest.param("169.254.169.254", "169.254.169.254", id="link-local"),
    pytest.param("10.0.0.5", "10.0.0.5", id="ten"),
    pytest.param("172.18.0.4", "172.18.0.4", id="one-seven-two"),
    pytest.param("192.168.1.10", "192.168.1.10", id="one-nine-two"),
    pytest.param("::ffff:127.0.0.1", "[::ffff:127.0.0.1]", id="mapped-loopback"),
    pytest.param("0.0.0.0", "0.0.0.0", id="unspecified"),
    pytest.param("224.0.0.1", "224.0.0.1", id="multicast"),
    pytest.param("240.0.0.1", "240.0.0.1", id="reserved"),
    # Carrying a public IPv4 address: the connector reads' check would take them, but this check has
    # refused them (Python's own predicates call them reserved or private), and the slice keeps
    # every refusal it had (the brief: the callers keep their behaviour for every address they
    # refuse today). Fail closed; nobody names a tile server by a NAT64 or 6to4 literal.
    pytest.param("64:ff9b::5db8:d822", "[64:ff9b::5db8:d822]", id="nat64-carrying-public"),
    pytest.param("2002:5db8:d822::", "[2002:5db8:d822::]", id="6to4-carrying-public"),
]
PUBLIC = [
    pytest.param("93.184.216.34", "93.184.216.34", id="public-v4"),
    pytest.param("2606:2800:220:1::1", "[2606:2800:220:1::1]", id="public-v6"),
]


@pytest.fixture(autouse=True)
def _no_real_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(map_admin, "resolve_host", lambda host: [])


@pytest.fixture
def audit(tmp_path: Path) -> Iterator[InMemoryMapAdminAudit]:
    folder = tmp_path / "map-settings"
    recorded = InMemoryMapAdminAudit()
    app.state.map_admin = MapAdmin(
        installed=MapConfig.model_validate({"default": "osm-local", "providers": [OSM]}),
        settings_file=MapSettingsFile(folder),
        key_file=MapKeyFile(folder),
        audit=recorded,
        tiles_root=tmp_path / "tiles",
    )
    app.dependency_overrides[get_principal] = lambda: ADMIN
    yield recorded
    app.dependency_overrides.clear()
    del app.state.map_admin


def _save(address_host: str) -> object:
    source = f"http://{address_host}/{{z}}/{{x}}/{{y}}.png"
    return TestClient(app).post(
        "/v1/admin/maps/providers",
        content=json.dumps({"provider": {**HOSTED, "id": "probe", "source": source}}),
    )


# --- The three ranges, through the address check and the route -----------------------------------


@pytest.mark.parametrize(("literal", "host"), MISSED)
def test_the_range_the_old_check_missed_is_judged_inside(literal: str, host: str) -> None:
    assert map_admin.host_inside(host)
    assert map_admin.host_inside(literal)


@pytest.mark.parametrize(("literal", "host"), MISSED)
def test_the_route_refuses_a_provider_at_a_range_the_old_check_missed(
    audit: InMemoryMapAdminAudit, literal: str, host: str
) -> None:
    answer = _save(host)
    assert answer.status_code == 422, (host, answer.text)  # type: ignore[attr-defined]
    assert "inside this deployment" in answer.text  # type: ignore[attr-defined]
    assert audit.entries == []


@pytest.mark.parametrize(("literal", "host"), MISSED)
def test_a_name_that_resolves_to_such_a_range_is_refused_at_save_and_at_a_fetch(
    audit: InMemoryMapAdminAudit, monkeypatch: pytest.MonkeyPatch, literal: str, host: str
) -> None:
    monkeypatch.setattr(map_admin, "resolve_host", lambda name: [literal])
    assert map_admin.host_inside("tiles.example.test")
    answer = TestClient(app).post(
        "/v1/admin/maps/providers",
        content=json.dumps({"provider": {**HOSTED, "id": "rebind"}}),
    )
    assert answer.status_code == 422 and "resolves inside" in answer.json()["detail"]["detail"]


@pytest.mark.parametrize(("literal", "host"), MISSED)
def test_the_connector_reads_judge_the_same_address_the_same_way(literal: str, host: str) -> None:
    """One question, one answer: the map check and the connector reads' check agree."""
    import ipaddress

    assert address_is_inside(ipaddress.ip_address(literal))
    assert map_admin.host_inside(host) == address_is_inside(ipaddress.ip_address(literal))


# --- Controls (rule 15) ---------------------------------------------------------------------------


@pytest.mark.parametrize(("literal", "host"), REFUSED_TODAY)
def test_what_was_refused_before_is_still_refused(
    audit: InMemoryMapAdminAudit, literal: str, host: str
) -> None:
    assert map_admin.host_inside(host)
    answer = _save(host)
    assert answer.status_code == 422, (host, answer.text)  # type: ignore[attr-defined]
    assert audit.entries == []


@pytest.mark.parametrize(("literal", "host"), PUBLIC)
def test_a_public_address_is_not_inside(literal: str, host: str) -> None:
    assert not map_admin.host_inside(host)


@pytest.mark.parametrize(("literal", "host"), PUBLIC)
def test_a_provider_at_a_public_address_is_taken(
    audit: InMemoryMapAdminAudit, literal: str, host: str
) -> None:
    answer = _save(host)
    assert answer.status_code == 200, (host, answer.text)  # type: ignore[attr-defined]
