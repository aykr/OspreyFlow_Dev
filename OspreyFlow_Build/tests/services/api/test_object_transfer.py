"""The object store's contents as plain files and back (ADR-114 Amendment 9 point 3a): what backup,
restore and the move from MinIO to SeaweedFS use, so no store's private data folder is ever copied.

Against a real S3 store — the one `MINIO_ENDPOINT` names (SeaweedFS in CI's `conformance` job and on
the throwaway test stack). Each case works in buckets of its own, so it touches nothing else there.
"""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from pyarrow import fs
from services.api.object_transfer import (
    TransferRefused,
    export_objects,
    import_objects,
    manifest_of,
    store_from_env,
)


@pytest.fixture
def store() -> fs.S3FileSystem:
    # The cases empty their own buckets; the product's connection may not delete a bucket.
    return store_from_env(allow_bucket_deletion=True)


@pytest.fixture
def buckets(store: fs.S3FileSystem) -> Iterator[list[str]]:
    names = [f"transfer-{uuid.uuid4().hex[:10]}" for _ in range(3)]
    yield names
    for name in names:
        try:
            store.delete_dir(name)
        except OSError:
            pass


def _put(store: fs.S3FileSystem, path: str, data: bytes) -> None:
    with store.open_output_stream(path) as out:
        out.write(data)


def _fill(store: fs.S3FileSystem, buckets: list[str]) -> dict[str, bytes]:
    a, b, empty = buckets
    content = {
        f"{a}/staging/2026/10/part-0.parquet": os.urandom(70_000),
        f"{a}/staging/2026/10/part-1.parquet": b"second",
        f"{b}/tiles/12/2046/1361": b"\x89PNG tile",
        f"{b}/top-level.json": b"{}",
    }
    for path, data in content.items():
        _put(store, path, data)
    store.create_dir(empty)
    return content


def test_every_object_goes_out_as_a_file_with_its_size_and_checksum(
    store: fs.S3FileSystem, buckets: list[str], tmp_path: Path
) -> None:
    content = _fill(store, buckets)
    manifest = export_objects(store, tmp_path, buckets=buckets)
    assert sorted(manifest["buckets"]) == sorted(buckets)  # the empty one too
    by_path = {f"{o['bucket']}/{o['key']}": o for o in manifest["objects"]}
    assert set(by_path) == set(content)
    for path, data in content.items():
        assert (tmp_path / "objects" / path).read_bytes() == data
        assert by_path[path]["size"] == len(data)
        assert by_path[path]["sha256"] == hashlib.sha256(data).hexdigest()
    assert json.loads((tmp_path / "manifest.json").read_text()) == manifest


def test_a_round_trip_puts_back_exactly_what_was_there(
    store: fs.S3FileSystem, buckets: list[str], tmp_path: Path
) -> None:
    _fill(store, buckets)
    before = manifest_of(store, buckets=buckets)
    export_objects(store, tmp_path, buckets=buckets)
    for name in buckets:
        store.delete_dir(name)
    assert manifest_of(store, buckets=buckets)["objects"] == []
    imported = import_objects(store, tmp_path)
    assert imported == len(before["objects"])
    assert manifest_of(store, buckets=buckets) == before


def test_an_altered_file_is_refused_before_anything_is_written(
    store: fs.S3FileSystem, buckets: list[str], tmp_path: Path
) -> None:
    _fill(store, buckets)
    export_objects(store, tmp_path, buckets=buckets)
    for name in buckets:
        store.delete_dir(name)
    (tmp_path / "objects" / buckets[1] / "top-level.json").write_bytes(b'{"altered": true}')
    with pytest.raises(TransferRefused, match=f"{buckets[1]}/top-level.json"):
        import_objects(store, tmp_path)
    assert manifest_of(store, buckets=buckets)["objects"] == []


def test_a_missing_file_is_refused(
    store: fs.S3FileSystem, buckets: list[str], tmp_path: Path
) -> None:
    _fill(store, buckets)
    export_objects(store, tmp_path, buckets=buckets)
    (tmp_path / "objects" / buckets[1] / "tiles" / "12" / "2046" / "1361").unlink()
    with pytest.raises(TransferRefused, match="1361"):
        import_objects(store, tmp_path)


def test_a_store_that_refuses_the_credentials_is_said_in_words(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MINIO_SECRET_KEY", "not-the-secret")
    with pytest.raises(TransferRefused, match="refused"):
        export_objects(store_from_env(), tmp_path, buckets=None)
