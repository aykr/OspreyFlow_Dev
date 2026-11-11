"""S3 and Athena sources through the Conduit's routes, and who may read through them (L1.9 part 1;
`process/CLAUDE.md` rules 2, 3 and 4; ADR-140 Amendment 13 decision 7 as corrected, which binds a
connection to the datasets an administrator names).

Every read path of a cloud connection, each with its access-control case (rule 4):
- **registering a source** (its first read) — `test_another_dataset_s_author_cannot_read_through_it`;
- **Refresh now** — `test_refresh_now_through_a_rebound_connection_reads_nothing`;
- **Test connection** — `test_only_an_administrator_may_test_a_cloud_connection`;
- **the wizard's list of connections** — `test_a_cloud_connection_is_listed_only_to_its_datasets_authors`;
- **a source's own routes on another dataset** — `test_another_dataset_s_source_is_refused`.

And what each read must never do:
- reach a host off the operator's egress allow-list (ADR-148 decision 7) —
  `test_a_host_off_the_egress_allow_list_is_never_reached`;
- cut a read at the byte cap, or write part of it (rule 2) —
  `test_a_read_past_the_byte_cap_is_refused_with_its_typed_error_and_writes_nothing`;
- tell a source author what an administrator's settings hold —
  the fixed words asserted in the two cases above;
- land anything but the golden file — `test_s3_and_athena_sources_land_as_their_golden_files`.
"""

from __future__ import annotations

import shutil
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pyarrow.fs as pa_fs
import pytest
from fastapi.testclient import TestClient
from services.api import connector_reads
from services.api.app import READ_OVER_CAP_FOR_AUTHORS, READ_REFUSED_FOR_AUTHORS, app
from services.api.connector_reads import Readers
from services.api.datasets import Dataset, InMemoryDatasetStore
from services.api.sources import InMemorySourceStore
from services.ingest.connectors import reads

from schemas.domain import Principal

from ...connectors.athena_fixture import RecordedAthena
from ...connectors.test_athena_connector import BOOKINGS, COLUMNS

GOLDEN = Path(__file__).resolve().parents[2] / "connectors" / "golden"
BUCKET_HOST = "synthetic-exports.s3.eu-west-2.amazonaws.com"
ATHENA_HOST = "athena.eu-west-2.amazonaws.com"
HANDLING = {"classification": "OFFICIAL", "handling_code": "P", "originator": "unit-1",
            "owning_unit": "unit-1"}  # fmt: skip
PEOPLE = {
    "author_a": Principal(id="a-1", clearance="SECRET", org_unit="unit-1", roles=["data_engineer"]),
    "author_b": Principal(id="b-1", clearance="SECRET", org_unit="unit-1", roles=["data_engineer"]),
    "admin": Principal(id="adm-1", clearance="SECRET", org_unit="unit-1", roles=["osprey-admin"]),
}
CASES = {"a-1": {"case-a": ["ds-a"]}, "b-1": {"case-b": ["ds-b"]}, "adm-1": {}}


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


class _Bucket:
    """The synthetic exports as the bucket, every listing and open counted."""

    def __init__(self, root: Path) -> None:
        self.fs = pa_fs.SubTreeFileSystem(str(root), pa_fs.LocalFileSystem())
        self.calls = 0

    def get_file_info(self, selector: pa_fs.FileSelector) -> list[pa_fs.FileInfo]:
        self.calls += 1
        return self.fs.get_file_info(selector)  # type: ignore[no-any-return]

    def open_input_stream(self, path: str) -> Any:
        self.calls += 1
        return self.fs.open_input_stream(path)


@pytest.fixture
def world(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[SimpleNamespace]:
    root = tmp_path / "ingest"
    for d in ("ds-a", "ds-b"):
        (root / "uploaded" / d).mkdir(parents=True)
    shutil.copytree(GOLDEN / "s3", tmp_path / "store")
    monkeypatch.setenv("OSPREY_INGEST_ROOT", str(root))
    # AWS's own public names resolve to a public address (synthetic; nothing leaves this machine).
    monkeypatch.setattr(connector_reads, "resolve_host", lambda host: ["52.95.150.10"])
    datasets = InMemoryDatasetStore()
    for d in ("ds-a", "ds-b"):
        datasets.add(Dataset(id=d, name=d, owning_unit="unit-1", created_by="s",
                             created_at=datetime(2026, 1, 1, tzinfo=UTC)))  # fmt: skip
    for person in CASES.values():
        for case, loads in person.items():
            datasets.cases[case] = loads
    bucket = _Bucket(tmp_path / "store")
    athena = RecordedAthena(tables={"visits": {"visit_bookings": (COLUMNS, BOOKINGS)}}, polls=0)
    readers = Readers(allowed_hosts=[BUCKET_HOST, ATHENA_HOST], s3_store=lambda _s: bucket,
                      athena_client=lambda _s: athena.client())  # fmt: skip
    audit, sources = _Audit(), InMemorySourceStore()
    state = {"principal_resolver": _Resolver(), "investigations": _Cases(), "datasets": datasets,
             "sources": sources, "studio_recipes": _Recipes(), "audit": audit,
             "connector_readers": readers}  # fmt: skip
    for name, value in state.items():
        monkeypatch.setattr(app.state, name, value, raising=False)
    yield SimpleNamespace(client=TestClient(app, raise_server_exceptions=False), root=root,
                          audit=audit, sources=sources, bucket=bucket, athena=athena,
                          readers=readers)  # fmt: skip


def _as(person: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {person}"}


SETTINGS = {
    "s3": {
        "kind": "s3",
        "region": "eu-west-2",
        "bucket": "synthetic-exports",
        "prefix": "client-a/",
    },
    "athena": {"kind": "athena", "region": "eu-west-2", "databases": ["visits"]},
}
READS = {
    "s3": {"kind": "s3", "folder": "visits/2026/", "format": "csv"},
    "athena": {"kind": "athena", "table": "visits.visit_bookings"},
}
GOLDEN_FILE = {"s3": "s3_visits.csv", "athena": "athena_visit_bookings.csv"}


def _connection(world: SimpleNamespace, kind: str, datasets: list[str] | None = None) -> str:
    body = {"kind": kind, "name": f"Synthetic {kind}", "datasets": datasets or ["ds-a"],
            "settings": SETTINGS[kind]}  # fmt: skip
    made = world.client.post("/v1/admin/connections", json=body, headers=_as("admin"))
    assert made.status_code == 201, made.text
    return str(made.json()["id"])


def _register(world: SimpleNamespace, dataset: str, connection_id: str, person: str,
              kind: str) -> Any:  # fmt: skip
    body = {
        "connection_id": connection_id,
        "name": "Visits",
        "location": "visits",
        "handling": HANDLING,
        "legal_basis": "Synthetic demonstration",
        "read": READS[kind],
    }
    return world.client.post(f"/v1/datasets/{dataset}/sources", json=body, headers=_as(person))


def _reads(world: SimpleNamespace) -> int:
    """How many times the bucket or Athena was asked anything."""
    return world.bucket.calls + len(world.athena.asked)


KINDS = pytest.mark.parametrize("kind", ["s3", "athena"])


@KINDS
def test_s3_and_athena_sources_land_as_their_golden_files(
    world: SimpleNamespace, kind: str
) -> None:
    made = _register(world, "ds-a", _connection(world, kind), "author_a", kind)
    assert made.status_code == 201, made.text
    landed = (world.root / "uploaded" / "ds-a" / "visits.csv").read_text(encoding="utf-8")
    assert landed == (GOLDEN / GOLDEN_FILE[kind]).read_text(encoding="utf-8")
    again = world.client.post(f"/v1/datasets/ds-a/sources/{made.json()['id']}/read",
                              headers=_as("author_a"))  # fmt: skip
    assert again.status_code == 200, again.text
    assert again.json()["file"] == "visits.csv" and str(world.root) not in again.text


@KINDS
def test_another_dataset_s_author_cannot_read_through_it(world: SimpleNamespace, kind: str) -> None:
    connection_id = _connection(world, kind)  # bound to ds-a only
    refused = _register(world, "ds-b", connection_id, "author_b", kind)
    unknown = _register(world, "ds-b", "no-such-connection", "author_b", kind)
    # Answered as a connection that does not exist (rule 3): its existence is not confirmed.
    assert (refused.status_code, refused.json()) == (unknown.status_code, unknown.json())
    assert refused.status_code == 404
    assert _reads(world) == 0  # nothing was asked of the bucket or Athena
    assert list((world.root / "uploaded" / "ds-b").iterdir()) == []
    # And through dataset A's own route, which author B does not author: refused at the dataset,
    # in the reply a dataset that does not exist gets, whole (rules 3 and 4; the orchestrator's
    # review of L1.9, round 1, item 5: a status of 403 or 404 told the two apart).
    theirs = _register(world, "ds-a", connection_id, "author_b", kind)
    nowhere = _register(world, "ds-nowhere", connection_id, "author_b", kind)
    assert (theirs.status_code, theirs.json()) == (nowhere.status_code, nowhere.json())
    assert theirs.status_code == 404
    assert _reads(world) == 0
    audited = [e for e in world.audit.entries if e["action"] == "connector_read_refused"]
    assert [e["resolved_query"]["dataset_id"] for e in audited] == ["ds-b"]


@KINDS
def test_refresh_now_through_a_rebound_connection_reads_nothing(
    world: SimpleNamespace, kind: str
) -> None:
    connection_id = _connection(world, kind)
    made = _register(world, "ds-a", connection_id, "author_a", kind).json()
    file = world.root / "uploaded" / "ds-a" / "visits.csv"
    held, asked = file.read_text(), _reads(world)
    bound = world.sources._connections[connection_id]
    world.sources._connections[connection_id] = bound.model_copy(update={"datasets": ["ds-b"]})
    refused = world.client.post(f"/v1/datasets/ds-a/sources/{made['id']}/read",
                                headers=_as("author_a"))  # fmt: skip
    assert refused.status_code == 404 and "not bound" not in refused.text
    assert file.read_text() == held and _reads(world) == asked


@KINDS
def test_another_dataset_s_source_is_refused(world: SimpleNamespace, kind: str) -> None:
    made = _register(world, "ds-a", _connection(world, kind), "author_a", kind).json()
    asked = _reads(world)

    def reply(dataset: str, source: str, read: bool) -> tuple[int, Any]:
        path = f"/v1/datasets/{dataset}/sources/{source}" + ("/read" if read else "")
        answer = (world.client.post if read else world.client.get)(path, headers=_as("author_b"))
        return answer.status_code, answer.json()

    # Each reply pinned whole to the one a thing that does not exist gets (rules 3 and 4; the
    # orchestrator's review of L1.9, round 1, item 5), never only its status.
    for read in (True, False):
        # Through author B's own dataset: as a source that does not exist.
        assert reply("ds-b", made["id"], read) == reply("ds-b", "no-such-source", read)
        assert reply("ds-b", made["id"], read)[0] == 404
        # Through dataset A's route, which author B does not author: as a dataset that does not.
        assert reply("ds-a", made["id"], read) == reply("ds-nowhere", made["id"], read)
        assert reply("ds-a", made["id"], read)[0] == 404
    assert _reads(world) == asked


@KINDS
def test_only_an_administrator_may_test_a_cloud_connection(
    world: SimpleNamespace, kind: str
) -> None:
    connection_id = _connection(world, kind)
    for person in ("author_a", "author_b"):
        refused = world.client.post(f"/v1/admin/connections/{connection_id}/test",
                                    headers=_as(person))  # fmt: skip
        assert refused.status_code == 403
    assert _reads(world) == 0
    tested = world.client.post(f"/v1/admin/connections/{connection_id}/test", headers=_as("admin"))
    assert tested.status_code == 200 and tested.json()["ok"] is True, tested.text


@KINDS
def test_a_cloud_connection_is_listed_only_to_its_datasets_authors(
    world: SimpleNamespace, kind: str
) -> None:
    _connection(world, kind)

    def listed(person: str) -> list[dict[str, Any]]:
        reply = world.client.get("/v1/ingest/connections", headers=_as(person))
        assert reply.status_code == 200, reply.text
        return [c for c in reply.json() if c["kind"] != "files"]

    assert listed("author_b") == []
    mine = listed("author_a")
    assert [c["kind"] for c in mine] == [kind]
    assert all(c.get("settings") is None and not c.get("datasets") for c in mine)


@KINDS
def test_a_host_off_the_egress_allow_list_is_never_reached(
    world: SimpleNamespace, kind: str
) -> None:
    connection_id = _connection(world, kind)
    world.readers.allowed_hosts = []
    refused = _register(world, "ds-a", connection_id, "author_a", kind)
    assert refused.status_code == 422
    assert refused.json()["detail"]["detail"] == READ_REFUSED_FOR_AUTHORS  # never the host
    assert _reads(world) == 0
    assert list((world.root / "uploaded" / "ds-a").iterdir()) == []
    tested = world.client.post(f"/v1/admin/connections/{connection_id}/test", headers=_as("admin"))
    assert tested.json()["ok"] is False and "egress allow-list" in tested.json()["words"]
    assert _reads(world) == 0


@KINDS
def test_a_read_past_the_byte_cap_is_refused_with_its_typed_error_and_writes_nothing(
    world: SimpleNamespace, kind: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    connection_id = _connection(world, kind)
    monkeypatch.setattr(reads, "MAX_BYTES", 100)
    refused = _register(world, "ds-a", connection_id, "author_a", kind)
    assert refused.status_code == 422
    # Its own type, rule 2's, and words that say so to an author (never the settings).
    assert refused.json()["detail"] == {"error": "read_over_cap",
                                        "detail": READ_OVER_CAP_FOR_AUTHORS}  # fmt: skip
    assert list((world.root / "uploaded" / "ds-a").iterdir()) == []
    assert world.sources._sources == {}
    why = [e["resolved_query"]["why"] for e in world.audit.entries
           if e["action"] == "connector_read_refused"]  # fmt: skip
    assert len(why) == 1 and "more than 100 bytes" in why[0] and "rule 2" in why[0]
    # A refusal that is not a cap keeps the general type: the two are told apart.
    monkeypatch.setattr(reads, "MAX_BYTES", 256 * 1024 * 1024)
    world.readers.allowed_hosts = []
    other = _register(world, "ds-a", connection_id, "author_a", kind)
    assert other.json()["detail"]["error"] == "read_refused"


def test_test_connection_tells_a_missing_bucket(world: SimpleNamespace) -> None:
    """The lane review, finding 3: the read's missing-bucket fix had not reached Test connection."""
    body = {"kind": "s3", "name": "Nowhere", "datasets": ["ds-a"],
            "settings": {**SETTINGS["s3"], "bucket": "synthetic-nowhere"}}  # fmt: skip
    made = world.client.post("/v1/admin/connections", json=body, headers=_as("admin")).json()
    world.readers.allowed_hosts = ["synthetic-nowhere.s3.eu-west-2.amazonaws.com"]
    tested = world.client.post(f"/v1/admin/connections/{made['id']}/test", headers=_as("admin"))
    assert tested.json() == {"ok": False, "words": "the bucket does not exist; nothing was read"}
