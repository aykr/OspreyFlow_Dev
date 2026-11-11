"""The S3 store and Athena client a deployment builds (`connector_reads.cloud_s3_store`,
`cloud_athena_client`), built here as a deployment builds them (the orchestrator's review of L1.9,
round 1, item 6: no executing test had built either, so the endpoint, the addressing and "no key"
were stated in prose and exercised by nothing; rule 12). The network is the recorded S3 or Athena
behind the client's own serialiser and parser (`s3_fixture.py`, `athena_fixture.py`).

What a mistake would do, and the case that catches it:
- a client sent to a host other than the one the egress allow-list names (an endpoint taken from
  the environment, path-style addressing, a region redirect followed) —
  `test_the_s3_store_reaches_the_bucket_s_own_host_virtual_hosted_with_no_key`,
  `test_the_athena_client_reaches_athena_s_own_host_with_no_key`,
  `test_a_request_bound_for_another_host_is_never_sent`;
- a key given to either client, so a connection's settings could carry one — the same two cases,
  which find the deployment's own identity (botocore's chain) signing each request;
- a folder past the object cap listed whole before it is counted (rule 2; round 1, item 8) —
  `test_a_listing_stops_at_the_object_cap_and_one`;
- S3's refusals read as an empty folder, or a bucket in another region followed there —
  `test_s3_s_refusals_are_refused_in_words_and_never_followed`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from services.api import connector_reads
from services.api.connector_reads import CloudS3Store, cloud_athena_client, cloud_s3_store
from services.ingest.connectors import s3_connector
from services.ingest.connectors.athena_connector import read_athena
from services.ingest.connectors.reads import ConnectorRefused, ReadOverCap
from services.ingest.connectors.s3_connector import read_s3

from schemas.sources import AthenaConnectionSettings, AthenaRead, S3ConnectionSettings, S3Read

from .athena_fixture import GRANTED_KEY, RecordedAthena
from .s3_fixture import RecordedS3
from .test_athena_connector import BOOKINGS, COLUMNS

S3 = S3ConnectionSettings(region="eu-west-2", bucket="synthetic-exports", prefix="client-a/")
ATHENA = AthenaConnectionSettings(region="eu-west-2", databases=["visits"])
#: The deployment's own identity, as botocore's chain finds it: here, the environment's (synthetic).
OWN_KEY = GRANTED_KEY


@pytest.fixture(autouse=True)
def own_identity(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    """The deployment's identity in the environment, and an environment that would send a careless
    client elsewhere: an endpoint for every service, and one for each of these two."""
    for name in ("AWS_PROFILE", "AWS_SESSION_TOKEN", "AWS_ROLE_ARN", "AWS_WEB_IDENTITY_TOKEN_FILE"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", OWN_KEY)
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "synthetic-secret-not-a-real-key")
    monkeypatch.setenv("AWS_CONFIG_FILE", str(tmp_path / "none"))
    monkeypatch.setenv("AWS_SHARED_CREDENTIALS_FILE", str(tmp_path / "none"))
    monkeypatch.setenv("AWS_EC2_METADATA_DISABLED", "true")
    monkeypatch.setenv("AWS_ENDPOINT_URL", "https://elsewhere.synthetic.example")
    monkeypatch.setenv("AWS_ENDPOINT_URL_S3", "https://elsewhere.synthetic.example")
    monkeypatch.setenv("AWS_ENDPOINT_URL_ATHENA", "https://elsewhere.synthetic.example")


def _keys(count: int, folder: str = "client-a/visits/") -> list[tuple[str, int]]:
    return [(f"{folder}part-{n:05d}.csv", 10) for n in range(count)]


def test_the_s3_store_reaches_the_bucket_s_own_host_virtual_hosted_with_no_key() -> None:
    store = cloud_s3_store(S3)
    # pyarrow's filesystem, by the arguments it was built with (its own record of them).
    made = store.fs.__reduce__()[1][0]
    assert made["endpoint_override"] == "s3.eu-west-2.amazonaws.com"
    assert made["scheme"] == "https" and made["force_virtual_addressing"] is True
    assert f"{S3.bucket}.{made['endpoint_override']}" == S3.host()
    assert (made["access_key"], made["secret_key"], made["session_token"]) == (None, None, None)
    assert made["anonymous"] is False and made["role_arn"] == ""
    assert made["allow_bucket_creation"] is False and made["allow_bucket_deletion"] is False
    # botocore's listing client, by the requests it really sends.
    assert store.client.meta.endpoint_url == "https://s3.eu-west-2.amazonaws.com"
    assert store.client.meta.config.s3["addressing_style"] == "virtual"
    recorded = RecordedS3(buckets={S3.bucket: _keys(3)})
    recorded.attach(store.client)
    store.list_objects(f"{S3.bucket}/client-a/visits", recursive=True, limit=10)
    assert [r["host"] for r in recorded.requests] == [S3.host()]
    assert {r["key"] for r in recorded.requests} == {OWN_KEY}  # botocore's chain, no key given


def test_the_athena_client_reaches_athena_s_own_host_with_no_key() -> None:
    client = cloud_athena_client(ATHENA)
    assert client.meta.endpoint_url == f"https://{ATHENA.host()}"
    hosts: list[str] = []
    client.meta.events.register(
        "before-send.athena", lambda request, **_: hosts.append(request.url) and None
    )
    athena = RecordedAthena(tables={"visits": {"visit_bookings": (COLUMNS, BOOKINGS)}}, polls=0)
    athena.attach(client)
    rows = read_athena(client, ATHENA, AthenaRead(table="visits.visit_bookings"))
    assert len(rows.rows) == len(BOOKINGS)
    assert {h.split("/")[2] for h in hosts} == {ATHENA.host()}
    # Signed as the deployment's own identity: the fixture refuses any key it does not know.
    assert athena.asked == ["StartQueryExecution", "GetQueryExecution", "GetQueryResults"]


@pytest.mark.parametrize("service", ["s3", "athena"])
def test_a_request_bound_for_another_host_is_never_sent(service: str) -> None:
    """Whatever moves a request (a region redirect, an endpoint resolver), it is refused before it
    is sent: planted as the request itself rewritten, after signing, to another region's host."""
    if service == "s3":
        client = cloud_s3_store(S3).client
        recorded: Any = RecordedS3(buckets={S3.bucket: _keys(1)})
    else:
        client = cloud_athena_client(ATHENA)
        recorded = RecordedAthena(tables={"visits": {"visit_bookings": (COLUMNS, BOOKINGS)}})
    recorded.attach(client)

    def elsewhere(request: Any, **_: Any) -> None:
        request.url = request.url.replace("eu-west-2", "eu-west-1")

    client.meta.events.register(f"request-created.{service}", elsewhere)
    with pytest.raises(ConnectorRefused, match="the host the egress allow-list names"):
        if service == "s3":
            client.list_objects_v2(Bucket=S3.bucket, Prefix="client-a/")
        else:
            client.get_work_group(WorkGroup="primary")
    assert getattr(recorded, "requests", getattr(recorded, "asked", None)) == []


def test_a_listing_stops_at_the_object_cap_and_one(monkeypatch: pytest.MonkeyPatch) -> None:
    """5,000 objects under the folder: the listing asks for no more than the cap and one, and is
    refused whole; nothing is opened."""
    store = cloud_s3_store(S3)
    recorded = RecordedS3(buckets={S3.bucket: _keys(5_000)})
    recorded.attach(store.client)
    opened: list[str] = []
    monkeypatch.setattr(store, "open_input_stream", lambda path: opened.append(path))
    with pytest.raises(ReadOverCap, match=r"more than 1000 objects.*rule 2"):
        read_s3(store, S3, S3Read(folder="visits/", format="csv"))
    assert [r["query"]["max-keys"] for r in recorded.requests] == ["1000", "1"]
    assert recorded.keys_listed == 1_001 and opened == []
    # And with the cap at 1,500, the second page asks for 501.
    recorded.requests.clear()
    monkeypatch.setattr(s3_connector, "MAX_OBJECTS", 1_500)
    with pytest.raises(ReadOverCap, match="more than 1500 objects"):
        read_s3(store, S3, S3Read(folder="visits/", format="csv"))
    assert [r["query"]["max-keys"] for r in recorded.requests] == ["1000", "501"]


def test_folder_markers_count_so_a_listing_of_them_stops_at_the_cap() -> None:
    """Own lane-reviewer, round 1: markers took up each page but were never counted, so a folder of
    them was listed page after page, unbounded by the cap, and then read as empty."""
    store = cloud_s3_store(S3)
    markers = [(f"client-a/visits/dir-{n:05d}/", 0) for n in range(5_000)]
    recorded = RecordedS3(buckets={S3.bucket: markers})
    recorded.attach(store.client)
    with pytest.raises(ReadOverCap, match="more than 1000 objects"):
        read_s3(store, S3, S3Read(folder="visits/", format="csv"))
    assert recorded.keys_listed == 1_001


def test_a_listing_cut_short_with_nowhere_to_go_on_is_refused_in_words() -> None:
    """Own lane-reviewer, round 1: a page marked cut short with no token was a KeyError (a 500)."""
    store = cloud_s3_store(S3)
    recorded = RecordedS3(buckets={S3.bucket: _keys(1_500)}, no_token=True)
    recorded.attach(store.client)
    with pytest.raises(ConnectorRefused, match="could not be followed"):
        store.list_objects(f"{S3.bucket}/client-a/visits", recursive=True, limit=2_000)
    assert len(recorded.requests) == 1


def test_a_store_that_cannot_be_made_is_refused_in_words_at_a_read_and_at_test() -> None:
    """Own lane-reviewer, round 1: pyarrow's OSError while making the filesystem was a 500."""
    import asyncio
    from datetime import UTC, datetime
    from types import SimpleNamespace

    from schemas.sources import Connection

    def broken(_settings: S3ConnectionSettings) -> Any:
        raise OSError("synthetic: the SDK could not start")

    readers = connector_reads.Readers(s3_store=broken, host_check=lambda *_a: None)
    connection = Connection(id="c-s3", kind="s3", name="Synthetic", created_by="adm-1",
                            created_at=datetime(2026, 11, 11, tzinfo=UTC), settings=S3,
                            datasets=["ds-a"])  # fmt: skip
    tested = asyncio.run(connector_reads.check_connection(connection, readers))
    assert (tested.ok, tested.words.startswith("the bucket's client could not be made")) == (
        False, True)  # fmt: skip
    source = SimpleNamespace(read=S3Read(folder="visits/", format="csv"))
    with pytest.raises(ConnectorRefused, match="the bucket's client could not be made"):
        asyncio.run(connector_reads.read_rows(source, connection, dataset_id="ds-a", cursor=None,
                                              readers=readers, root=Path("/nonexistent")))  # fmt: skip


def test_a_listing_under_the_cap_is_whole_and_in_key_order() -> None:
    store = cloud_s3_store(S3)
    keys = _keys(2_400) + [("client-a/visits/_temporary/0/part-x.csv", 5)]
    recorded = RecordedS3(buckets={S3.bucket: keys})
    recorded.attach(store.client)
    found = store.list_objects(f"{S3.bucket}/client-a/visits", recursive=True, limit=2_500)
    assert [f.path for f in found] == [f"{S3.bucket}/{k}" for k, _ in sorted(keys)]
    assert len(recorded.requests) == 3  # 1,000 a page, S3's most


@pytest.mark.parametrize(
    ("refusal", "words"),
    [
        ("missing", s3_connector.MISSING_BUCKET),
        ("denied", "the bucket refused the read (access denied)"),
        ("moved", s3_connector.OTHER_REGION),
        ("wrong_region", s3_connector.OTHER_REGION),
    ],
)
def test_s3_s_refusals_are_refused_in_words_and_never_followed(refusal: str, words: str) -> None:
    store = cloud_s3_store(S3)
    recorded = RecordedS3(buckets={}, refusing={S3.bucket: refusal})
    recorded.attach(store.client)
    with pytest.raises(ConnectorRefused) as refused:
        read_s3(store, S3, S3Read(folder="visits/", format="csv"))
    assert str(refused.value).startswith(words)
    assert {r["host"] for r in recorded.requests} == {S3.host()}  # never another region's host
    assert "eu-west-1" not in str(refused.value) and S3.bucket not in str(refused.value)


def test_readers_build_the_deployment_s_own_clients_by_default() -> None:
    readers = connector_reads.Readers()
    assert readers.s3_store is cloud_s3_store and readers.athena_client is cloud_athena_client
    assert isinstance(readers.s3_store(S3), CloudS3Store)
