"""A SQL, API or JSON connection is bound to the datasets an administrator names when making it, and
a source may read only through a connection bound to its own dataset (`06_DECISIONS.md` ADR-140
Amendment 13 decision 7 as corrected; the orchestrator's ruling on L1.6's second review, rule 3).

A connection is opened only to register a source (its first read) and by *Refresh now*; both go
through `read_into_file`, which refuses an unbound dataset, and the register route refuses before
anything is read. Test, a step's sample and the run read the source's file in its own dataset's
folder, which only a bound connection wrote, and never open a connection
(`test_test_the_sample_and_the_run_never_open_a_connection`).

What a mistake would do, and the case that catches it:
- an author of dataset B reading dataset A's database into B —
  `test_an_author_of_another_dataset_cannot_register_through_its_connection`;
- a refresh through a connection no longer bound to the source's dataset —
  `test_refresh_now_through_an_unbound_connection_is_refused`;
- a caller of `read_into_file` that forgets the route's check —
  `test_the_one_read_path_refuses_an_unbound_dataset`;
- one connection's secret reused by another pointing elsewhere, so its password goes to another
  host or database — `test_a_secret_belongs_to_one_connection`;
- an unknown connection answered 500, a refused read not audited, or a server path in the reply —
  `test_an_unknown_connection_is_404_and_a_refused_read_is_audited_without_paths`.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from services.api import connector_reads
from services.api.app import app
from services.api.connector_reads import Readers, read_into_file
from services.api.datasets import Dataset, InMemoryDatasetStore
from services.api.sources import InMemorySourceStore
from services.ingest.connectors.reads import ConnectorRefused

from schemas.domain import Principal
from schemas.sources import ApiRead

TOKEN = "synthetic-telco-secret-9f3a"
HANDLING = {"classification": "OFFICIAL", "handling_code": "P", "originator": "unit-1",
            "owning_unit": "unit-1"}  # fmt: skip
PEOPLE = {
    "author_a": Principal(id="a-1", clearance="SECRET", org_unit="unit-1", roles=["data_engineer"]),
    "author_b": Principal(id="b-1", clearance="SECRET", org_unit="unit-1", roles=["data_engineer"]),
    "admin": Principal(id="adm-1", clearance="SECRET", org_unit="unit-1", roles=["osprey-admin"]),
}
CASES = {"a-1": {"case-a": ["ds-a"]}, "b-1": {"case-b": ["ds-b"]}, "adm-1": {}}


def _telco(request: httpx.Request) -> httpx.Response:
    if request.headers.get("authorization") != f"Bearer {TOKEN}":
        return httpx.Response(401)
    return httpx.Response(200, json={"data": [{"number": "07700900001"}]})


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
    for d in ("ds-a", "ds-b"):
        (root / "uploaded" / d).mkdir(parents=True)
    monkeypatch.setenv("OSPREY_INGEST_ROOT", str(root))
    monkeypatch.setenv("OSPREY_CONNECTION_SECRET_TELCO_A", TOKEN)
    monkeypatch.setenv("OSPREY_CONNECTOR_SECRETS", "TELCO_A")  # declared (Amendment 15)
    monkeypatch.setattr(connector_reads, "resolve_host", lambda host: ["93.184.215.14"])
    datasets = InMemoryDatasetStore()
    for d in ("ds-a", "ds-b"):
        datasets.add(Dataset(id=d, name=d, owning_unit="unit-1", created_by="s",
                             created_at=datetime(2026, 1, 1, tzinfo=UTC)))  # fmt: skip
    for person in CASES.values():
        for case, reads in person.items():
            datasets.cases[case] = reads
    audit, sources = _Audit(), InMemorySourceStore()
    readers = Readers(http_transport=httpx.MockTransport(_telco), allowed_hosts=["telco.example"])
    state = {"principal_resolver": _Resolver(), "investigations": _Cases(), "datasets": datasets,
             "sources": sources, "studio_recipes": _Recipes(), "audit": audit,
             "connector_readers": readers}  # fmt: skip
    for name, value in state.items():
        monkeypatch.setattr(app.state, name, value, raising=False)
    yield SimpleNamespace(client=TestClient(app, raise_server_exceptions=False), root=root,
                          audit=audit, sources=sources)  # fmt: skip


def _as(person: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {person}"}


def _connection(world: SimpleNamespace, secret: str = "TELCO_A", datasets: list[str] | None = None,
                host: str = "telco.example") -> Any:  # fmt: skip
    body = {"kind": "api", "name": f"Telco {secret} {host}", "datasets": datasets or ["ds-a"],
            "settings": {"kind": "api", "base_url": f"https://{host}", "auth": "bearer",
                         "secret": secret}}  # fmt: skip
    return world.client.post("/v1/admin/connections", json=body, headers=_as("admin"))


def _register(world: SimpleNamespace, dataset: str, connection_id: str, person: str) -> Any:
    body = {"connection_id": connection_id, "name": "Telco numbers", "location": "telco_numbers",
            "handling": HANDLING, "read": {"kind": "api", "path": "/v1/n", "records_at": "data"}}
    return world.client.post(f"/v1/datasets/{dataset}/sources", json=body, headers=_as(person))


def test_an_author_of_another_dataset_cannot_register_through_its_connection(
    world: SimpleNamespace,
) -> None:
    connection_id = _connection(world).json()["id"]
    refused = _register(world, "ds-b", connection_id, "author_b")
    assert refused.status_code == 404 and "not bound" not in refused.text
    assert list((world.root / "uploaded" / "ds-b").iterdir()) == []
    assert world.sources._sources == {}
    allowed = _register(world, "ds-a", connection_id, "author_a")
    assert allowed.status_code == 201, allowed.text


def test_refresh_now_through_an_unbound_connection_is_refused(world: SimpleNamespace) -> None:
    connection_id = _connection(world).json()["id"]
    made = _register(world, "ds-a", connection_id, "author_a").json()
    file = world.root / "uploaded" / "ds-a" / "telco_numbers.csv"
    held = file.read_text()
    bound = world.sources._connections[connection_id]
    world.sources._connections[connection_id] = bound.model_copy(update={"datasets": ["ds-b"]})
    refused = world.client.post(f"/v1/datasets/ds-a/sources/{made['id']}/read",
                                headers=_as("author_a"))  # fmt: skip
    assert refused.status_code == 404 and "not bound" not in refused.text
    assert file.read_text() == held


def test_the_one_read_path_refuses_an_unbound_dataset(world: SimpleNamespace) -> None:
    connection_id = _connection(world).json()["id"]
    connection = world.sources._connections[connection_id]
    source = SimpleNamespace(read=ApiRead(path="/v1/n", records_at="data"), refresh=None)
    readers = Readers(http_transport=httpx.MockTransport(_telco), allowed_hosts=["telco.example"])
    with pytest.raises(ConnectorRefused, match="not bound to this dataset"):
        asyncio.run(read_into_file(source, connection, dataset_id="ds-b", name="theirs",
                                   cursor=None, readers=readers, root=world.root))  # fmt: skip
    assert not (world.root / "uploaded" / "ds-b" / "theirs.csv").exists()


def test_a_secret_belongs_to_one_connection(world: SimpleNamespace) -> None:
    assert _connection(world).status_code == 201
    again = _connection(world, host="elsewhere.example", datasets=["ds-b"])
    assert again.status_code == 422 and "already used by another connection" in again.text
    assert len([c for c in world.sources._connections.values() if c.kind == "api"]) == 1


def test_an_unknown_connection_is_404_and_a_refused_read_is_audited_without_paths(
    world: SimpleNamespace,
) -> None:
    missing = world.client.post("/v1/admin/connections/nope/test", headers=_as("admin"))
    assert missing.status_code == 404
    connection_id = _connection(world).json()["id"]
    made = _register(world, "ds-a", connection_id, "author_a").json()
    gone = world.client.post(f"/v1/datasets/ds-a/sources/{made['id']}/read",
                             headers=_as("author_a"))  # fmt: skip
    assert gone.status_code == 200 and str(world.root) not in gone.text
    assert gone.json()["file"] == "telco_numbers.csv"
    del world.sources._connections[connection_id]
    unknown = world.client.post(f"/v1/datasets/ds-a/sources/{made['id']}/read",
                                headers=_as("author_a"))  # fmt: skip
    assert unknown.status_code == 404, unknown.text
    refused = _register(world, "ds-b", "nope", "author_b")
    assert refused.status_code == 404
    other = _connection(world, secret="TELCO_B", host="other.example").json()["id"]
    bad = _register(world, "ds-b", other, "author_b")
    assert bad.status_code == 404
    refusals = [e for e in world.audit.entries if e["action"] == "connector_read_refused"]
    assert [e["resolved_query"]["dataset_id"] for e in refusals] == ["ds-b"]
    assert str(world.root) not in json.dumps([e.get("resolved_query") for e in world.audit.entries])


def test_test_the_sample_and_the_run_never_open_a_connection() -> None:
    """Nothing but registration and *Refresh now* opens a connection: a static read of the callers
    of `read_into_file` and `read_rows` in the Conduit."""
    core = Path(__file__).resolve().parents[4] / "OspreyFlow_Core" / "services"
    call = __import__("re").compile(r"(?<![\w.])(read_into_file|read_rows)\(")
    callers = sorted(
        str(p.relative_to(core)) for p in core.rglob("*.py")
        if call.search(p.read_text()) and p.name != "connector_reads.py"
    )  # fmt: skip
    assert callers == ["api/app.py"], callers
    text = (core / "api" / "app.py").read_text()
    assert text.count("await read_into_file(") == 2  # registration, and Refresh now


def test_a_source_author_is_shown_only_connections_bound_to_a_dataset_they_author(
    world: SimpleNamespace,
) -> None:
    """The register wizard's list (`GET /v1/ingest/connections`) is decision 1's ruling too: a
    source author sees a SQL, API or JSON connection's name and kind only when it is bound to a
    dataset one of their cases loads into, by that dataset's own gate, and never which datasets a
    connection is bound to (another dataset's id would tell them it exists, rule 3)."""
    _connection(world)  # bound to ds-a only

    def listed(person: str) -> list[dict[str, Any]]:
        reply = world.client.get("/v1/ingest/connections", headers=_as(person))
        assert reply.status_code == 200, reply.text
        return [c for c in reply.json() if c["kind"] != "files"]

    assert listed("author_b") == []
    mine = listed("author_a")
    assert [c["name"] for c in mine] == ["Telco TELCO_A telco.example"]
    assert all(not c.get("datasets") and c.get("settings") is None for c in mine)
    _connection(world, secret="TELCO_B", host="other.example", datasets=["ds-a", "ds-b"])
    assert [c["name"] for c in listed("author_b")] == ["Telco TELCO_B other.example"]
    assert all(not c.get("datasets") for c in listed("author_b"))


def test_an_unbound_connection_answers_as_an_unknown_one(world: SimpleNamespace) -> None:
    """Amendment 13 decision 1, the orchestrator's review of Amendment 15, item 12: another
    dataset's connection is not confirmed to exist. Registering through it and Refresh now through
    it answer exactly as a connection that does not exist does, status and body alike."""
    connection_id = _connection(world).json()["id"]
    unbound = _register(world, "ds-b", connection_id, "author_b")
    unknown = _register(world, "ds-b", "no-such-connection", "author_b")
    assert (unbound.status_code, unbound.json()) == (unknown.status_code, unknown.json())
    assert unbound.status_code == 404
    made = _register(world, "ds-a", connection_id, "author_a").json()
    url = f"/v1/datasets/ds-a/sources/{made['id']}/read"
    bound = world.sources._connections[connection_id]
    world.sources._connections[connection_id] = bound.model_copy(update={"datasets": ["ds-b"]})
    rebound = world.client.post(url, headers=_as("author_a"))
    del world.sources._connections[connection_id]
    gone = world.client.post(url, headers=_as("author_a"))
    assert (rebound.status_code, rebound.json()) == (gone.status_code, gone.json())
    assert rebound.status_code == 404
