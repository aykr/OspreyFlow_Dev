"""Phase 9's connections and the sources read through them, on their routes (`06_DECISIONS.md`
ADR-140 Amendment 13; rules 3 and 4). Offline: the API is a synthetic fixture transport that
refuses what a real API refuses (rule 15); the SQL connector runs live in
`tests/connectors/test_sql_connector_live.py`.

What a mistake would do, and the case that catches it:
- a connection's secret answered, audited or kept anywhere —
  `test_a_secret_is_named_and_its_value_never_leaves_the_deployment`;
- a connection named or tested by someone who is not an administrator —
  `test_only_an_administrator_names_or_tests_a_connection`;
- a source registered although its first read failed, leaving a source with no rows behind it —
  `test_a_source_whose_first_read_is_refused_is_not_registered`;
- a read landing anywhere but the source's own file in its own dataset's folder, or a file source
  "refreshed" through the connector route — `test_a_connector_source_lands_as_its_one_file`;
- *Refresh now* reached for another unit's dataset or by someone without the Studio role —
  `test_refresh_now_is_reached_only_through_the_dataset_s_own_gate`.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from services.api.app import app
from services.api.connector_reads import Readers
from services.api.datasets import Dataset, InMemoryDatasetStore
from services.api.sources import InMemorySourceStore

from schemas.domain import Principal

TOKEN = "synthetic-telco-secret-9f3a"
HANDLING = {
    "classification": "OFFICIAL",
    "handling_code": "P",
    "originator": "unit-1",
    "owning_unit": "unit-1",
}
PEOPLE = {
    name: Principal(id=pid, clearance="SECRET", org_unit=unit, roles=[role])
    for name, pid, unit, role in (
        ("engineer", "eng-1", "unit-1", "data_engineer"),
        ("analyst", "ana-1", "unit-1", "analyst"),
        ("stranger", "str-1", "unit-2", "data_engineer"),
        ("reader", "read-1", "unit-1", "data_engineer"),
        ("admin", "adm-1", "unit-1", "osprey-admin"),
    )
}
#: `read-1`'s one case reads ds-a second: through it a load would go into ds-x, so ds-a's routes are
#: not theirs (the dataset's own gate; the lane review of L1.6, item 9).
CASES = {
    "eng-1": {"case-a": ["ds-a"]},
    "ana-1": {"case-y": ["ds-a"]},
    "str-1": {"case-s": ["ds-s"]},
    "read-1": {"case-r": ["ds-x", "ds-a"]},
    "adm-1": {},
}
NUMBERS = [
    {"number": "07700900001", "network": "Synthetic Mobile"},
    {"number": "07700900002", "network": "Fictional Telecom"},
]


def _telco(request: httpx.Request) -> httpx.Response:
    if request.headers.get("authorization") != f"Bearer {TOKEN}":
        return httpx.Response(401)
    if request.url.path != "/v1/numbers":
        return httpx.Response(404)
    return httpx.Response(200, json={"data": NUMBERS})


class _Resolver:
    def resolve(self, token: str) -> Principal:
        return PEOPLE[token]


class _Cases:
    async def list_for(self, principal: Principal) -> list[tuple[Any, str]]:
        return [(SimpleNamespace(id=c), "editor") for c in CASES[principal.id]]


class _Recipes:
    async def using_source(self, dataset_id: str, location: str) -> list[Any]:
        return []


class _Audit:
    def __init__(self) -> None:
        self.entries: list[dict[str, Any]] = []

    async def record(self, **kwargs: Any) -> None:
        self.entries.append(kwargs)


@pytest.fixture
def world(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[SimpleNamespace]:
    root = tmp_path / "ingest"
    (root / "uploaded" / "ds-a").mkdir(parents=True)
    (root / "ds-a").mkdir()
    (root / "ds-a" / "bookings-1.json").write_text(
        json.dumps({"records": [{"booking_id": 1, "visitor": "SYN-V-1"}]})
    )
    monkeypatch.setenv("OSPREY_INGEST_ROOT", str(root))
    monkeypatch.setenv("OSPREY_CONNECTION_SECRET_TELCO", TOKEN)
    # No lookup leaves the machine: `sneaky.example` resolves inside, everything else to nothing.
    from services.api import connector_reads

    monkeypatch.setattr(
        connector_reads,
        "resolve_host",
        lambda host: ["10.1.2.3"] if host == "sneaky.example" else ["93.184.215.14"],
    )
    datasets = InMemoryDatasetStore()
    for d, unit in (("ds-a", "unit-1"), ("ds-s", "unit-2"), ("ds-x", "unit-1")):
        datasets.add(
            Dataset(
                id=d,
                name=d,
                owning_unit=unit,
                created_by="s",
                created_at=datetime(2026, 1, 1, tzinfo=UTC),
            )
        )
    for person in CASES.values():
        for case, reads in person.items():
            datasets.cases[case] = reads
    audit, sources = _Audit(), InMemorySourceStore()
    readers = Readers(http_transport=httpx.MockTransport(_telco), allowed_hosts=["telco.example"])
    state = {
        "principal_resolver": _Resolver(),
        "investigations": _Cases(),
        "datasets": datasets,
        "sources": sources,
        "studio_recipes": _Recipes(),
        "audit": audit,
        "connector_readers": readers,
    }
    for name, value in state.items():
        monkeypatch.setattr(app.state, name, value, raising=False)
    yield SimpleNamespace(
        client=TestClient(app), root=root, audit=audit, sources=sources, readers=readers
    )


def _as(person: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {person}"}


API = {
    "kind": "api",
    "name": "Telco lookup (synthetic)",
    "datasets": ["ds-a"],
    "settings": {
        "kind": "api",
        "base_url": "https://telco.example",
        "auth": "bearer",
        "secret": "TELCO",
    },
}


def _connection(world: SimpleNamespace, body: dict[str, Any] = API) -> str:
    made = world.client.post("/v1/admin/connections", json=body, headers=_as("admin"))
    assert made.status_code == 201, made.text
    return str(made.json()["id"])


def _register(
    world: SimpleNamespace,
    connection_id: str,
    read: dict[str, Any],
    name: str = "telco_numbers",
    person: str = "engineer",
) -> Any:
    body = {
        "connection_id": connection_id,
        "name": "Telco numbers",
        "location": name,
        "handling": HANDLING,
        "read": read,
    }
    return world.client.post("/v1/datasets/ds-a/sources", json=body, headers=_as(person))


def test_only_an_administrator_names_or_tests_a_connection(world: SimpleNamespace) -> None:
    for person in ("engineer", "analyst"):
        named = world.client.post("/v1/admin/connections", json=API, headers=_as(person))
        assert named.status_code == 403, person
    connection_id = _connection(world)
    for person in ("engineer", "analyst"):
        tested = world.client.post(
            f"/v1/admin/connections/{connection_id}/test", headers=_as(person)
        )
        assert tested.status_code == 403, person
    ok = world.client.post(f"/v1/admin/connections/{connection_id}/test", headers=_as("admin"))
    assert ok.json() == {"ok": True, "words": "The host is allowed and the secret is set."}
    world.readers.allowed_hosts = ["elsewhere.example"]
    off = world.client.post(f"/v1/admin/connections/{connection_id}/test", headers=_as("admin"))
    assert off.json()["ok"] is False and "egress allow-list" in off.json()["words"]
    missing = world.client.post("/v1/admin/connections/nope/test", headers=_as("admin"))
    assert missing.status_code == 404
    assert "test_ingest_connection" in [e["action"] for e in world.audit.entries]


def test_a_secret_is_named_and_its_value_never_leaves_the_deployment(
    world: SimpleNamespace,
) -> None:
    connection_id = _connection(world)
    listed = world.client.get("/v1/admin/connections", headers=_as("admin"))
    studio = world.client.get("/v1/ingest/connections", headers=_as("engineer"))
    registered = _register(
        world, connection_id, {"kind": "api", "path": "/v1/numbers", "records_at": "data"}
    )
    refreshed = world.client.post(
        f"/v1/datasets/ds-a/sources/{registered.json()['id']}/read", headers=_as("engineer")
    )
    answers = [listed.text, studio.text, registered.text, refreshed.text]
    assert all(TOKEN not in a for a in answers)
    assert "TELCO" in listed.text  # the name, never the value, and only to an administrator
    for setting in ("TELCO", "telco.example", "base_url"):
        assert setting not in studio.text, setting  # a source author sees names and kinds only
    assert TOKEN not in json.dumps(world.audit.entries, default=str)
    with_value = {**API, "settings": {**API["settings"], "password": TOKEN}}  # type: ignore[dict-item]
    assert (
        world.client.post(
            "/v1/admin/connections", json=with_value, headers=_as("admin")
        ).status_code
        == 422
    )


def test_a_connector_source_lands_as_its_one_file(world: SimpleNamespace) -> None:
    connection_id = _connection(world)
    made = _register(
        world, connection_id, {"kind": "api", "path": "/v1/numbers", "records_at": "data"}
    )
    assert made.status_code == 201, made.text
    file = world.root / "uploaded" / "ds-a" / "telco_numbers.csv"
    assert made.json()["location"] == str(file)
    assert (
        file.read_text() == "number,network\n07700900001,Synthetic Mobile\n"
        "07700900002,Fictional Telecom\n"
    )
    again = world.client.post(
        f"/v1/datasets/ds-a/sources/{made.json()['id']}/read", headers=_as("engineer")
    )
    assert again.status_code == 200 and again.json()["rows"] == 2, again.text
    assert again.json()["file"] == file.name
    json_connection = _connection(
        world, {"kind": "json", "name": "Bookings files", "settings": {"kind": "json"},
                "datasets": ["ds-a"]}
    )
    json_read = {"kind": "json", "pattern": "bookings-*.json", "records_at": "records"}
    bookings = _register(world, json_connection, json_read, name="bookings")
    assert bookings.status_code == 201, bookings.text
    assert (world.root / "uploaded" / "ds-a" / "bookings.csv").read_text() == (
        "booking_id,visitor\n1,SYN-V-1\n"
    )
    path = world.root / "uploaded" / "ds-a" / "cells.csv"
    path.write_text("a\n1\n")
    file_source = world.client.post(
        "/v1/datasets/ds-a/sources",
        headers=_as("engineer"),
        json={
            "connection_id": "files",
            "name": "Cells",
            "location": str(path),
            "handling": HANDLING,
        },
    )
    assert file_source.status_code == 201, file_source.text
    refused = world.client.post(
        f"/v1/datasets/ds-a/sources/{file_source.json()['id']}/read", headers=_as("engineer")
    )
    assert refused.status_code == 422 and "upload the new file" in refused.text


def test_a_source_whose_first_read_is_refused_is_not_registered(world: SimpleNamespace) -> None:
    connection_id = _connection(world)
    for read, name in (
        ({"kind": "api", "path": "/v1/elsewhere", "records_at": "data"}, "telco_numbers"),
        ({"kind": "api", "path": "/v1/numbers", "records_at": "rows"}, "telco_numbers"),
        ({"kind": "json", "pattern": "*.json"}, "telco_numbers"),
        ({"kind": "api", "path": "/v1/numbers", "records_at": "data"}, "../escape"),
    ):
        refused = _register(world, connection_id, read, name)
        assert refused.status_code == 422, (read, refused.text)
    world.readers.allowed_hosts = []
    off = _register(
        world, connection_id, {"kind": "api", "path": "/v1/numbers", "records_at": "data"}
    )
    assert off.status_code == 422 and "egress allow-list" in off.text
    assert world.sources._sources == {}
    assert list((world.root / "uploaded" / "ds-a").iterdir()) == []


def test_refresh_now_is_reached_only_through_the_dataset_s_own_gate(world: SimpleNamespace) -> None:
    connection_id = _connection(world)
    made = _register(
        world, connection_id, {"kind": "api", "path": "/v1/numbers", "records_at": "data"}
    )
    url = f"/v1/datasets/ds-a/sources/{made.json()['id']}/read"
    assert world.client.post(url, headers=_as("stranger")).status_code == 404
    assert world.client.post(url, headers=_as("reader")).status_code == 404
    assert (
        _register(
            world,
            connection_id,
            {"kind": "api", "path": "/v1/numbers"},
            name="theirs",
            person="reader",
        ).status_code
        == 404
    )
    assert world.client.post(url, headers=_as("analyst")).status_code == 403
    other = world.client.post(
        f"/v1/datasets/ds-s/sources/{made.json()['id']}/read", headers=_as("stranger")
    )
    assert other.status_code == 404
    assert (
        _register(
            world,
            connection_id,
            {"kind": "api", "path": "/v1/numbers"},
            name="other",
            person="analyst",
        ).status_code
        == 403
    )


def test_a_registration_never_overwrites_a_file_and_leaves_none_when_refused(
    world: SimpleNamespace,
) -> None:
    """The lane review of L1.6 (item 4): the first read wrote `<name>.csv` before anything was
    checked, so a source named after a file already there overwrote it and was then refused."""
    connection_id = _connection(world)
    uploaded = world.root / "uploaded" / "ds-a" / "estabs.csv"
    uploaded.write_text("estab_id,name\nE1,HMP Synthetic One\n")
    read = {"kind": "api", "path": "/v1/numbers", "records_at": "data"}
    clash = _register(world, connection_id, read, name="estabs")
    assert clash.status_code == 409 and "another name" in clash.text
    assert uploaded.read_text() == "estab_id,name\nE1,HMP Synthetic One\n"
    first = _register(world, connection_id, read)
    assert first.status_code == 201
    file = world.root / "uploaded" / "ds-a" / "telco_numbers.csv"
    held = file.read_text()
    again = _register(world, connection_id, read)
    assert again.status_code == 409 and file.read_text() == held

    class _Refusing:
        async def using_source(self, dataset_id: str, location: str) -> list[Any]:
            return [SimpleNamespace(label="Keyless", status="published", deduplicate=None)]

    world.client.app.state.studio_recipes = _Refusing()
    watch = {"trigger": "watch", "pattern": "x"}
    body = {
        "connection_id": connection_id,
        "name": "Watched",
        "location": "watched",
        "handling": HANDLING,
        "read": read,
        "refresh": watch,
    }
    refused = world.client.post("/v1/datasets/ds-a/sources", json=body, headers=_as("engineer"))
    assert refused.status_code == 422 and "Keyless" in refused.text, refused.text
    assert not (world.root / "uploaded" / "ds-a" / "watched.csv").exists()


def test_a_registration_the_store_fails_takes_its_file_back(
    world: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    connection_id = _connection(world)

    async def broken(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("the store went away")

    monkeypatch.setattr(world.sources, "register", broken)
    client = TestClient(app, raise_server_exceptions=False)
    body = {
        "connection_id": connection_id,
        "name": "Telco numbers",
        "location": "telco_numbers",
        "handling": HANDLING,
        "read": {"kind": "api", "path": "/v1/numbers", "records_at": "data"},
    }
    failed = client.post("/v1/datasets/ds-a/sources", json=body, headers=_as("engineer"))
    assert failed.status_code == 500
    assert not (world.root / "uploaded" / "ds-a" / "telco_numbers.csv").exists()


def test_a_connection_whose_host_resolves_inside_is_never_kept(world: SimpleNamespace) -> None:
    """The orchestrator's review of L1.6 (item 4): refused at save, before anything is kept."""
    body = {**API, "settings": {**API["settings"], "base_url": "https://sneaky.example/v1"}}  # type: ignore[dict-item]
    refused = world.client.post("/v1/admin/connections", json=body, headers=_as("admin"))
    assert refused.status_code == 422 and "resolves inside" in refused.text
    inside = {**API, "settings": {**API["settings"], "base_url": "https://169.254.169.254/v1"}}  # type: ignore[dict-item]
    assert (
        world.client.post("/v1/admin/connections", json=inside, headers=_as("admin")).status_code
        == 422
    )
    assert [
        c["kind"] for c in world.client.get("/v1/admin/connections", headers=_as("admin")).json()
    ] == ["files"]
