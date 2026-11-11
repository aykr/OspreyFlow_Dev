"""The S3 connector, offline (L1.9 part 1; ADR-148 decisions 4 and 7; `09_INGEST_STUDIO.md` §2's
"S3 and Athena"). The bucket here is pyarrow's own local filesystem under a folder of synthetic
exports (rule 9), reached through the same `pyarrow.fs.FileSystem` interface the real S3 filesystem
gives, so the reader under test is the one a deployment runs. What the real S3 refuses (a bucket
the role may not read, a bucket that does not exist) is proved against SeaweedFS in
`test_s3_connector_live.py`.

What a mistake would do, and the case that catches it:
- the source's file not what the objects hold (a row lost, a column dropped, the wrong order) —
  `test_csv_objects_under_a_folder_land_as_the_golden_file`,
  `test_parquet_objects_land_as_the_golden_file`;
- an object outside the connection's prefix read (another client's folder) —
  `test_nothing_outside_the_connection_s_prefix_is_read`;
- a half-written or hidden object, or a file of another format, read as rows —
  `test_hidden_objects_and_other_formats_are_never_read`;
- objects past the byte cap read and then cut (rule 2) —
  `test_objects_past_the_byte_cap_are_refused_before_any_is_opened`;
- an object that grew after listing read whole — `test_an_object_that_grew_is_stopped_while_read`;
- too many objects, or Parquet rows past the cap, read and then cut (rule 2) —
  `test_too_many_objects_are_refused_whole`, `test_parquet_rows_past_the_cap_are_refused_from_the_footer`;
- an empty folder read as an empty table — `test_an_empty_folder_is_refused_in_words`;
- a CSV whose header names a column twice silently losing one —
  `test_a_header_naming_a_column_twice_is_refused`;
- a key or secret held in the connection's settings —
  `test_neither_cloud_connection_takes_a_key_or_a_secret`.
"""

from __future__ import annotations

import datetime as dt
import shutil
from typing import Any
from decimal import Decimal
from pathlib import Path

import pyarrow as pa
import pyarrow.fs as pa_fs
import pyarrow.parquet as pq
import pytest
from pydantic import ValidationError
from services.ingest.connectors import reads, s3_connector
from services.ingest.connectors.reads import ConnectorRefused, ReadOverCap, write_snapshot
from services.ingest.connectors.s3_connector import read_s3

from schemas.sources import (
    AthenaConnectionSettings,
    ConnectionInput,
    S3ConnectionSettings,
    S3Read,
)

GOLDEN = Path(__file__).parent / "golden"
EXPORTS = GOLDEN / "s3"
BUCKET = "synthetic-exports"


@pytest.fixture
def bucket(tmp_path: Path) -> pa_fs.FileSystem:
    """The synthetic exports as a bucket: `<bucket>/<key>`, as the S3 filesystem names objects."""
    shutil.copytree(EXPORTS, tmp_path / "store")
    return pa_fs.SubTreeFileSystem(str(tmp_path / "store"), pa_fs.LocalFileSystem())


def _settings(prefix: str = "client-a/") -> S3ConnectionSettings:
    return S3ConnectionSettings(region="eu-west-2", bucket=BUCKET, prefix=prefix)


def _landed(rows: reads.ReadRows, tmp_path: Path) -> str:
    return write_snapshot(rows, tmp_path / "landed", "source").read_text(encoding="utf-8")


def test_csv_objects_under_a_folder_land_as_the_golden_file(
    bucket: pa_fs.FileSystem, tmp_path: Path
) -> None:
    rows = read_s3(bucket, _settings(), S3Read(folder="visits/2026/", format="csv"))
    assert _landed(rows, tmp_path) == (GOLDEN / "s3_visits.csv").read_text(encoding="utf-8")


def _calls() -> pa.Table:
    utc = dt.UTC
    return pa.table({
        "call_id": ["C-001", "C-002", "C-003"],
        "caller": ["07700900001", "07700900002", "07700900003"],
        "duration_s": pa.array([62, 0, 3601], pa.int64()),
        "charged": [True, False, True],
        "cost": pa.array([Decimal("0.25"), Decimal("0.00"), Decimal("12.50")], pa.decimal128(6, 2)),
        "started_at": pa.array([dt.datetime(2026, 10, 1, 9, 30, tzinfo=utc),
                                dt.datetime(2026, 10, 1, 10, 0, 5, tzinfo=utc),
                                dt.datetime(2026, 10, 2, 23, 59, 59, tzinfo=utc)],
                               pa.timestamp("us", tz="UTC")),
        "call_date": pa.array([dt.date(2026, 10, 1), dt.date(2026, 10, 1), dt.date(2026, 10, 2)]),
        "tags": [["night", "roaming"], [], ["long"]],
        "note": [None, "Synthetic, quoted", None],
    })  # fmt: skip


def _put(bucket: pa_fs.FileSystem, key: str) -> pa.NativeFile:
    """An object written into the bucket (the local stand-in needs the folder made; S3 does not)."""
    bucket.create_dir(f"{BUCKET}/{key}".rsplit("/", 1)[0], recursive=True)
    return bucket.open_output_stream(f"{BUCKET}/{key}")


def _put_parquet(bucket: pa_fs.FileSystem, key: str, table: pa.Table) -> None:
    with _put(bucket, key) as out:
        pq.write_table(table, out)


def test_parquet_objects_land_as_the_golden_file(bucket: pa_fs.FileSystem, tmp_path: Path) -> None:
    calls = _calls()
    _put_parquet(bucket, "client-a/calls/part-0.parquet", calls.slice(0, 2))
    _put_parquet(bucket, "client-a/calls/part-1.parquet", calls.slice(2))
    rows = read_s3(bucket, _settings(), S3Read(folder="calls/", format="parquet"))
    assert _landed(rows, tmp_path) == (GOLDEN / "s3_parquet.csv").read_text(encoding="utf-8")


def test_nothing_outside_the_connection_s_prefix_is_read(bucket: pa_fs.FileSystem) -> None:
    rows = read_s3(bucket, _settings(), S3Read(folder="", format="csv"))
    ids = {r["visit_id"] for r in rows.rows}
    assert "V-0001" in ids
    assert "V-9999" not in ids  # client-b's own export, beside client-a's prefix
    # A folder is a name under the prefix; it cannot climb out of it.
    with pytest.raises(ValidationError):
        S3Read(folder="../client-b/", format="csv")
    with pytest.raises(ValidationError):
        S3Read(folder="/client-b/", format="csv")


def test_hidden_objects_and_other_formats_are_never_read(bucket: pa_fs.FileSystem) -> None:
    rows = read_s3(bucket, _settings(), S3Read(folder="visits/2026/", format="csv"))
    ids = {r["visit_id"] for r in rows.rows}
    assert "V-HALF" not in ids
    assert all(set(r) <= set(rows.columns) for r in rows.rows)
    with pytest.raises(ConnectorRefused, match="no Parquet object"):
        read_s3(bucket, _settings(), S3Read(folder="visits/2026/", format="parquet"))


class _Watched:
    """The bucket, its opens recorded and, with `listed_size`, its listing claiming that size for
    every object (as an object rewritten larger after it was listed would look)."""

    def __init__(self, inner: pa_fs.FileSystem, listed_size: int | None = None) -> None:
        self.inner, self.listed_size = inner, listed_size
        self.opened: list[str] = []
        self.infos: list[str] = []

    def get_file_info(self, selector: Any) -> Any:
        self.infos.append("selector" if isinstance(selector, pa_fs.FileSelector) else selector)
        found = self.inner.get_file_info(selector)
        if self.listed_size is None or not isinstance(selector, pa_fs.FileSelector):
            return found
        return [pa_fs.FileInfo(i.path, i.type, size=self.listed_size) for i in found]

    def open_input_stream(self, path: str) -> pa.NativeFile:
        self.opened.append(path)
        return self.inner.open_input_stream(path)


def test_objects_past_the_byte_cap_are_refused_before_any_is_opened(
    bucket: pa_fs.FileSystem, monkeypatch: pytest.MonkeyPatch
) -> None:
    watched = _Watched(bucket)
    monkeypatch.setattr(reads, "MAX_BYTES", 120)
    with pytest.raises(ConnectorRefused, match=r"more than 120 bytes.*rule 2"):
        read_s3(watched, _settings(), S3Read(folder="visits/2026/", format="csv"))
    assert watched.opened == []


def test_an_object_that_grew_is_stopped_while_read(
    bucket: pa_fs.FileSystem, monkeypatch: pytest.MonkeyPatch
) -> None:
    watched = _Watched(bucket, listed_size=1)
    monkeypatch.setattr(reads, "MAX_BYTES", 150)
    with pytest.raises(ConnectorRefused, match="rule 2"):
        read_s3(watched, _settings(), S3Read(folder="visits/2026/", format="csv"))
    assert len(watched.opened) == 2  # stopped at the second object, never read past the cap


def test_too_many_objects_are_refused_whole(
    bucket: pa_fs.FileSystem, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(s3_connector, "MAX_OBJECTS", 2)
    with pytest.raises(ConnectorRefused, match=r"more than 2 objects.*rule 2"):
        read_s3(bucket, _settings(), S3Read(folder="visits/2026/", format="csv"))


def test_csv_rows_past_the_cap_are_refused_whole(
    bucket: pa_fs.FileSystem, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(reads, "MAX_ROWS", 3)
    with pytest.raises(ConnectorRefused, match="rule 2"):
        read_s3(bucket, _settings(), S3Read(folder="visits/2026/", format="csv"))


def test_parquet_rows_past_the_cap_are_refused_from_the_footer(
    bucket: pa_fs.FileSystem, monkeypatch: pytest.MonkeyPatch
) -> None:
    _put_parquet(bucket, "client-a/calls/part-0.parquet", _calls())
    monkeypatch.setattr(reads, "MAX_ROWS", 2)
    read_rows: list[object] = []
    monkeypatch.setattr(s3_connector, "_parquet_rows", lambda *a: read_rows.append(a) or ([], 0))
    with pytest.raises(ConnectorRefused, match=r"more than 2 rows.*rule 2"):
        read_s3(bucket, _settings(), S3Read(folder="calls/", format="parquet"))
    assert read_rows == []  # refused from the footer's count, before a row was read


def test_a_job_s_underscore_files_are_never_read(bucket: pa_fs.FileSystem) -> None:
    """A Spark job's `_temporary/…/part-*.csv` (the lane review of L1.9, finding 16)."""
    rows = read_s3(bucket, _settings(), S3Read(folder="visits/2026/", format="csv"))
    assert "V-TEMP" not in {r["visit_id"] for r in rows.rows}


def test_a_missing_bucket_is_told_so_not_read_as_an_empty_folder(bucket: pa_fs.FileSystem) -> None:
    missing = S3ConnectionSettings(region="eu-west-2", bucket="synthetic-nowhere")
    with pytest.raises(ConnectorRefused, match="^the bucket does not exist; nothing was read$"):
        read_s3(bucket, missing, S3Read(folder="", format="csv"))


def test_the_bucket_is_asked_for_only_when_the_folder_is_empty(bucket: pa_fs.FileSystem) -> None:
    """Asking for the bucket needs ListBucket on all of it, which a role limited to a prefix may not
    hold (the lane review, finding 5): a folder with objects never asks."""
    watched = _Watched(bucket)
    read_s3(watched, _settings(), S3Read(folder="visits/2026/", format="csv"))
    assert watched.infos == ["selector"]


@pytest.mark.parametrize(
    ("message", "words"),
    [
        ("When listing objects under key 'forbidden/' in bucket 'b': AWS Error NETWORK_CONNECTION "
         "during ListObjectsV2 operation", "the bucket could not be read"),
        ("When listing objects under key 'nosuchbucket/': AWS Error ACCESS_DENIED during "
         "ListObjectsV2 operation: Access Denied.", "the bucket refused the read (access denied)"),
        ("When reading information for key '' in bucket 'b': AWS Error NO_SUCH_BUCKET during "
         "HeadBucket operation", "the bucket does not exist"),
    ],
)  # fmt: skip
def test_a_store_s_refusal_is_judged_by_its_code_not_by_a_key_s_words(
    message: str, words: str
) -> None:
    assert str(s3_connector.refused_by_store(OSError(message))).startswith(words)


def test_parquet_past_the_byte_cap_decoded_is_refused_before_its_rows_are_made(
    bucket: pa_fs.FileSystem, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A small file whose values repeat unpacks to far more than the cap (finding 11): refused at
    the row group that passes it, decoded, before any Python row is made."""
    many = pa.table({"note": ["the same synthetic words, again and again"] * 20_000})
    _put_parquet(bucket, "client-a/calls/part-0.parquet", many)
    compressed = bucket.get_file_info(f"{BUCKET}/client-a/calls/part-0.parquet").size
    monkeypatch.setattr(reads, "MAX_BYTES", compressed * 4)
    made: list[object] = []
    monkeypatch.setattr(s3_connector, "cell", lambda v: made.append(v) or v)
    with pytest.raises(ReadOverCap, match="rule 2"):
        read_s3(bucket, _settings(), S3Read(folder="calls/", format="parquet"))
    assert made == []


def test_an_empty_folder_is_refused_in_words(bucket: pa_fs.FileSystem) -> None:
    with pytest.raises(ConnectorRefused, match="no CSV object under"):
        read_s3(bucket, _settings(), S3Read(folder="nothing-here/", format="csv"))


def test_a_header_naming_a_column_twice_is_refused(
    bucket: pa_fs.FileSystem, tmp_path: Path
) -> None:
    with _put(bucket, "client-a/twice/a.csv") as out:
        out.write(b"ref,name,ref\nR1,N1,R2\n")
    with pytest.raises(ConnectorRefused, match="names the column 'ref' twice"):
        read_s3(bucket, _settings(), S3Read(folder="twice/", format="csv"))


def test_neither_cloud_connection_takes_a_key_or_a_secret() -> None:
    for kind, settings in (
        ("s3", {"kind": "s3", "region": "eu-west-2", "bucket": BUCKET}),
        ("athena", {"kind": "athena", "region": "eu-west-2", "databases": ["visits"]}),
    ):
        for field in ("secret", "access_key", "secret_key", "aws_secret_access_key",
                      "session_token", "endpoint"):  # fmt: skip
            with pytest.raises(ValidationError):
                ConnectionInput(kind=kind, name="c", datasets=["ds-a"],  # type: ignore[arg-type]
                                settings={**settings, field: "AKIAEXAMPLE"})  # fmt: skip
    assert "secret" not in S3ConnectionSettings.model_fields
    assert "secret" not in AthenaConnectionSettings.model_fields


@pytest.mark.parametrize(
    "bucket_name",
    ["with.dot", "UPPER", "xn--encoded", "a", "ends-s3alias", "127.0.0.1", "-lead"],
)
def test_a_bucket_named_otherwise_is_refused(bucket_name: str) -> None:
    with pytest.raises(ValidationError):
        S3ConnectionSettings(region="eu-west-2", bucket=bucket_name)


def test_the_host_is_made_from_the_region_and_bucket_never_typed() -> None:
    assert _settings().host() == "synthetic-exports.s3.eu-west-2.amazonaws.com"
    with pytest.raises(ValidationError):
        S3ConnectionSettings(region="eu-west-2.evil.example", bucket=BUCKET)
    athena = AthenaConnectionSettings(region="eu-west-2", databases=["visits"])
    assert athena.host() == "athena.eu-west-2.amazonaws.com"
