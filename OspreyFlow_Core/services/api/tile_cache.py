"""Caches proxied tiles to object storage — `spec/00_ARCHITECTURE.md` §1.2's
tile proxy: "caches tiles to object storage, keeping usage within licence
limits and making the map usable offline/slow-link." Mirrors `services/api/
site_images.py`'s exact shape: reuses `services/ingest/staging.py`'s
`ObjectStorageConfig`/`filesystem` (the house `pyarrow.fs.S3FileSystem`
convention) rather than a second, near-identical dataclass — the only
thing this module needs of its own is a different bucket and a
staleness-aware read.

`PrefetchCache.prefetch_areas` (pre-warming a named area of operations
ahead of time, not just caching on read) is a real, separate scheduled-job
feature this module does not build — flagged, not silently assumed done;
this is the read-through cache half only.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pyarrow.fs as pa_fs
from services.ingest.staging import ObjectStorageConfig, filesystem


def tile_cache_storage_config() -> ObjectStorageConfig:
    return ObjectStorageConfig.named("MINIO_TILE_CACHE_BUCKET", "tile-cache")


def cache_key_for(provider_id: str, z: int, x: int, y: int) -> str:
    return f"tiles/{provider_id}/{z}/{x}/{y}"


def read_cached_tile(
    *, storage: ObjectStorageConfig, object_key: str, ttl_days: int
) -> bytes | None:
    """`None` for both a cache miss and a stale entry — either way the
    caller re-fetches and calls `write_cached_tile`, so the two cases need
    no separate handling."""
    fs = filesystem(storage)
    path = f"{storage.bucket}/{object_key}"
    info = fs.get_file_info([path])[0]
    if info.type == pa_fs.FileType.NotFound:
        return None
    if datetime.now(UTC) - info.mtime > timedelta(days=ttl_days):
        return None
    with fs.open_input_file(path) as source:
        data: bytes = source.read()
    return data


def write_cached_tile(data: bytes, *, storage: ObjectStorageConfig, object_key: str) -> None:
    fs = filesystem(storage)
    fs.create_dir(storage.bucket)
    path = f"{storage.bucket}/{object_key}"
    with fs.open_output_stream(path) as sink:
        sink.write(data)
