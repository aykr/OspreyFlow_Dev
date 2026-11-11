"""The S3 connector against a real S3 server: SeaweedFS, the stand-in the build already runs as its
object store (L1.9 part 1; rule 15). Its golden files are the offline suite's, so the same reader
lands the same file from a real S3 API; and its refusals are the server's own, not a fixture's: a
principal the bucket does not grant, a bucket that does not exist.

Skipped unless `OSPREY_S3_STANDIN` names the stand-in's address (`127.0.0.1:58333`), started with
`golden/seaweedfs_s3.json` as its identities, for example:

    docker run -d --name studio-b-seaweedfs -p 127.0.0.1:58333:8333 \
      -v $PWD/tests/connectors/golden/seaweedfs_s3.json:/etc/seaweedfs/s3.json:ro \
      chrislusf/seaweedfs:4.48 server -s3 -dir=/data -s3.port=8333 \
      -s3.config=/etc/seaweedfs/s3.json -volume.max=10 -master.volumePreallocate=false

The credentials are the stand-in's own synthetic ones, from that file (rule 9); no connection's
settings ever hold one (`test_s3_connector.test_neither_cloud_connection_takes_a_key_or_a_secret`).
Every object this file writes is removed in teardown, even when a case fails.
"""

from __future__ import annotations

import asyncio
import io
import json
import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pyarrow.fs as pa_fs
import pyarrow.parquet as pq
import pytest
from services.ingest.connectors import reads
from services.ingest.connectors.reads import ConnectorRefused, write_snapshot
from services.ingest.connectors.s3_connector import read_s3

from schemas.sources import S3ConnectionSettings, S3Read

from .test_s3_connector import BUCKET, EXPORTS, GOLDEN, _calls

STANDIN = os.environ.get("OSPREY_S3_STANDIN", "")
pytestmark = pytest.mark.skipif(not STANDIN, reason="OSPREY_S3_STANDIN names no S3 stand-in")
IDENTITIES = {i["name"]: i["credentials"][0]
              for i in json.loads((GOLDEN / "seaweedfs_s3.json").read_text())["identities"]}  # fmt: skip


def _as(name: str, **kwargs: object) -> pa_fs.S3FileSystem:
    key = IDENTITIES[name]
    return pa_fs.S3FileSystem(
        endpoint_override=STANDIN, scheme="http", region="eu-west-2",
        access_key=key["accessKey"], secret_key=key["secretKey"], **kwargs,
    )  # fmt: skip


@pytest.fixture(scope="module")
def bucket() -> Iterator[None]:
    setup = _as("setup", allow_bucket_creation=True, allow_bucket_deletion=True)
    setup.create_dir(BUCKET)
    try:
        for path in sorted(EXPORTS.rglob("*")):
            if path.is_file():
                with setup.open_output_stream(
                    f"{BUCKET}/{path.relative_to(EXPORTS / BUCKET)}"
                ) as out:
                    out.write(path.read_bytes())
        calls = _calls()
        for number, part in enumerate((calls.slice(0, 2), calls.slice(2))):
            body = io.BytesIO()
            pq.write_table(part, body)
            with setup.open_output_stream(f"{BUCKET}/client-a/calls/part-{number}.parquet") as out:
                out.write(body.getvalue())
        yield
    finally:
        setup.delete_dir(BUCKET)


def _settings() -> S3ConnectionSettings:
    return S3ConnectionSettings(region="eu-west-2", bucket=BUCKET, prefix="client-a/")


@pytest.mark.usefixtures("bucket")
@pytest.mark.parametrize(
    ("folder", "fmt", "golden"),
    [("visits/2026/", "csv", "s3_visits.csv"), ("calls/", "parquet", "s3_parquet.csv")],
)
def test_the_stand_in_s_objects_land_as_the_golden_files(
    folder: str, fmt: str, golden: str, tmp_path: Path
) -> None:
    rows = read_s3(_as("reader"), _settings(), S3Read(folder=folder, format=fmt))  # type: ignore[arg-type]
    landed = write_snapshot(rows, tmp_path, "source").read_text(encoding="utf-8")
    assert landed == (GOLDEN / golden).read_text(encoding="utf-8")


@pytest.mark.usefixtures("bucket")
def test_a_principal_the_bucket_does_not_grant_is_refused_as_access_denied() -> None:
    with pytest.raises(ConnectorRefused) as refused:
        read_s3(_as("other"), _settings(), S3Read(folder="visits/2026/", format="csv"))
    assert str(refused.value).startswith("the bucket refused the read (access denied)")
    assert IDENTITIES["other"]["accessKey"] not in str(refused.value)


@pytest.mark.usefixtures("bucket")
def test_a_bucket_that_does_not_exist_is_refused_in_words() -> None:
    missing = S3ConnectionSettings(region="eu-west-2", bucket="synthetic-nowhere", prefix="")
    with pytest.raises(ConnectorRefused) as refused:
        read_s3(_as("setup"), missing, S3Read(folder="", format="csv"))
    # Not "no CSV object": the folder's listing answers a missing bucket as empty, so the bucket
    # is asked for first (found here, the first run against the stand-in).
    assert str(refused.value) == "the bucket does not exist; nothing was read"


@pytest.mark.usefixtures("bucket")
def test_test_connection_lists_as_the_granted_role_and_is_refused_as_another() -> None:
    from datetime import UTC, datetime

    from services.api.connector_reads import Readers, check_connection

    from schemas.sources import Connection

    connection = Connection(id="c-s3", kind="s3", name="Synthetic exports", created_by="adm-1",
                            created_at=datetime(2026, 11, 11, tzinfo=UTC), settings=_settings(),
                            datasets=["ds-a"])  # fmt: skip

    def tested(identity: str, of: Connection = connection) -> Any:
        # The stand-in is on this machine, which the deployment's own check never admits: a
        # fixture's check stands in for it, named here (as the SQL live tests do).
        readers = Readers(s3_store=lambda _s: _as(identity), host_check=lambda *_a: None)
        return asyncio.run(check_connection(of, readers))

    assert tested("reader").ok is True
    refused = tested("other")
    assert refused.ok is False and refused.words.startswith("the bucket refused the read")
    # The lane review, finding 3: a missing bucket is told so at Test, as at a read.
    nowhere = connection.model_copy(update={"settings": S3ConnectionSettings(
        region="eu-west-2", bucket="synthetic-nowhere")})  # fmt: skip
    missing = tested("setup", nowhere)
    assert (missing.ok, missing.words) == (False, "the bucket does not exist; nothing was read")


@pytest.mark.usefixtures("bucket")
def test_the_byte_cap_refuses_a_real_listing_whole(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(reads, "MAX_BYTES", 120)
    with pytest.raises(ConnectorRefused, match=r"more than 120 bytes.*rule 2"):
        read_s3(_as("reader"), _settings(), S3Read(folder="visits/2026/", format="csv"))
