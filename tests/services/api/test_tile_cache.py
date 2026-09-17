"""`services/api/tile_cache.py` — against a live MinIO instance, not a
mock, the same reasoning `tests/ingest/test_staging.py`'s own module
docstring gives: "the data that comes back out of object storage is the
data that went in" is not a property a mock can prove.
`services/ingest/staging.filesystem()` always builds a real
`pyarrow.fs.S3FileSystem` (no local-filesystem escape hatch), so every
test here needs the `make dev-up` stack — this file is outside `make
test`'s boundary, in `make test-all`'s explicit list, mirroring
`test_staging.py`'s own placement.
"""

from __future__ import annotations

from services.api.tile_cache import (
    cache_key_for,
    read_cached_tile,
    tile_cache_storage_config,
    write_cached_tile,
)


def test_cache_key_is_stable_and_readable() -> None:
    assert cache_key_for("usgs-national-map", 5, 10, 15) == "tiles/usgs-national-map/5/10/15"


async def test_a_tile_round_trips_through_the_cache_unchanged() -> None:
    storage = tile_cache_storage_config()
    key = cache_key_for("test-provider", 1, 2, 3)

    write_cached_tile(b"fake-tile-bytes", storage=storage, object_key=key)
    loaded = read_cached_tile(storage=storage, object_key=key, ttl_days=1)

    assert loaded == b"fake-tile-bytes"


async def test_a_missing_key_is_a_cache_miss_not_an_error() -> None:
    storage = tile_cache_storage_config()

    loaded = read_cached_tile(
        storage=storage, object_key="tiles/never-written/0/0/0", ttl_days=1
    )

    assert loaded is None


async def test_an_entry_older_than_its_ttl_is_treated_as_a_miss() -> None:
    storage = tile_cache_storage_config()
    key = cache_key_for("test-provider-stale", 1, 1, 1)
    write_cached_tile(b"fake-tile-bytes", storage=storage, object_key=key)

    # `ttl_days=0` means "fresh only if written in the future" — any real,
    # already-elapsed write age counts as stale, without needing to sleep
    # past a real TTL boundary in a test.
    loaded = read_cached_tile(storage=storage, object_key=key, ttl_days=0)

    assert loaded is None
