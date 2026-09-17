"""`services/api/prefetch.py` — `docs/07_BUILD_PLAN.md`'s Phase 5
known-gaps closure's scheduled AOI pre-warm job. Against a live MinIO
instance, not a mock —
the same reasoning `test_tile_cache.py`'s own module docstring gives, and
this module reuses `tile_cache.py`'s `read_cached_tile`/`write_cached_tile`
directly. `make dev-up`'s stack required; `make test-all`'s explicit list,
mirroring `test_tile_cache.py`'s own placement.

The upstream tile fetch is injected (`build_upstream_url`/`fetch_tile`'s
own "no third-party network dependency in CI" convention) — only the
cache round-trip is real.
"""

from __future__ import annotations

import uuid

import duckdb
import pytest
from services.api.prefetch import prefetch_area
from services.api.tile_cache import cache_key_for, read_cached_tile, tile_cache_storage_config

from schemas.analytics import GeometryKind, GeometryRecord
from schemas.domain import Handling, Principal
from schemas.mapconfig import MapProvider

PRINCIPAL = Principal(id="prefetch-job", clearance="SECRET", org_unit="unit-1")


def _handling() -> Handling:
    return Handling(classification="OFFICIAL", handling_code="P", owning_unit="unit-1",
                     originator="unit-1")


def _square_wkb() -> bytes:
    con = duckdb.connect(":memory:")
    try:
        con.install_extension("spatial")
        con.load_extension("spatial")
        wkt = "POLYGON((-0.13 51.50, -0.13 51.51, -0.11 51.51, -0.11 51.50, -0.13 51.50))"
        return con.execute("SELECT ST_AsWKB(ST_GeomFromText(?))", [wkt]).fetchone()[0]
    finally:
        con.close()


class _FakeAnalyticsPort:
    """Implements only what `prefetch_area` calls — a fake, not a mock:
    `get_geometry` really does look the record up by ref."""

    def __init__(self, records: dict[str, GeometryRecord]) -> None:
        self._records = records

    async def get_geometry(
        self, geometry_ref: str, principal: Principal, *, version: int | None = None
    ) -> GeometryRecord | None:
        return self._records.get(geometry_ref)


def _wmts_provider(**overrides: object) -> MapProvider:
    """A real, persistent MinIO instance (not a mock) means cache keys
    must be unique per test *run*, not just per test name — a previous
    run's tiles are still sitting there, already fresh, and would make a
    "freshly fetched" assertion pass or fail depending on history rather
    than this run's own behaviour. Every id gets its own UUID suffix,
    regardless of the caller-supplied `id` label."""
    label = overrides.pop("id", "default")
    base: dict[str, object] = {
        "id": f"prefetch-test-{label}-{uuid.uuid4().hex[:8]}",
        "label": "Prefetch test provider",
        "kind": "raster",
        "service": "wmts",
        "endpoint": "http://127.0.0.1:9/wmts",
        "layer": "test-layer",
        "tile_matrix_set": "GoogleMapsCompatible",
        "format": "image/png",
        "wmts_style": "default",
        "zoom_min": 14,
        "zoom_max": 14,
        "cache": {"ttl_days": 30, "prefetch_areas": ["boundary-1"]},
        "proxy": "required",
        "attribution": "Test",
        "licence": {"id": "test", "redistributable": True, "client_scope": "open"},
    }
    base.update(overrides)
    return MapProvider.model_validate(base)


async def test_prefetch_area_fetches_every_tile_covering_the_boundary() -> None:
    boundary = GeometryRecord(
        geometry_ref="boundary-1", version=1, kind=GeometryKind.POLYGON,
        geometry_wkb=_square_wkb(), handling=_handling(),
    )
    analytics = _FakeAnalyticsPort({"boundary-1": boundary})
    provider = _wmts_provider(id="fetch-all")
    storage = tile_cache_storage_config()
    fetched_urls: list[str] = []

    async def fake_http_get(url: str) -> bytes:
        fetched_urls.append(url)
        return b"fake-tile-bytes"

    report = await prefetch_area(
        provider, "boundary-1", PRINCIPAL, analytics, storage=storage, http_get=fake_http_get
    )

    assert report.tiles_fetched > 0
    assert report.tiles_fetched == len(fetched_urls)
    assert all("TILEMATRIX=14" in url for url in fetched_urls)


async def test_prefetch_area_writes_tiles_into_the_read_through_cache() -> None:
    boundary = GeometryRecord(
        geometry_ref="boundary-1", version=1, kind=GeometryKind.POLYGON,
        geometry_wkb=_square_wkb(), handling=_handling(),
    )
    analytics = _FakeAnalyticsPort({"boundary-1": boundary})
    provider = _wmts_provider(id="cache-write", zoom_min=13, zoom_max=13)
    storage = tile_cache_storage_config()

    async def fake_http_get(url: str) -> bytes:
        return b"prefetched-bytes"

    report = await prefetch_area(
        provider, "boundary-1", PRINCIPAL, analytics, storage=storage, http_get=fake_http_get
    )
    assert report.tiles_fetched >= 1

    # At least one tile at zoom 13 covering this bbox must now be cached —
    # re-derive the same tile the job itself would have computed and check
    # it directly, rather than trusting the report alone.
    from services.api.tile_math import tile_range_for_bbox

    x_min, x_max, y_min, y_max = tile_range_for_bbox(-0.13, 51.50, -0.11, 51.51, zoom=13)
    key = cache_key_for(provider.id, 13, x_min, y_min)
    cached = read_cached_tile(storage=storage, object_key=key, ttl_days=30)
    assert cached == b"prefetched-bytes"


async def test_prefetch_area_skips_a_tile_already_fresh_in_cache() -> None:
    boundary = GeometryRecord(
        geometry_ref="boundary-1", version=1, kind=GeometryKind.POLYGON,
        geometry_wkb=_square_wkb(), handling=_handling(),
    )
    analytics = _FakeAnalyticsPort({"boundary-1": boundary})
    provider = _wmts_provider(id="skip-cached", zoom_min=12, zoom_max=12)
    storage = tile_cache_storage_config()

    call_count = 0

    async def fake_http_get(url: str) -> bytes:
        nonlocal call_count
        call_count += 1
        return b"first-run-bytes"

    first = await prefetch_area(
        provider, "boundary-1", PRINCIPAL, analytics, storage=storage, http_get=fake_http_get
    )
    assert first.tiles_fetched >= 1
    calls_after_first_run = call_count

    second = await prefetch_area(
        provider, "boundary-1", PRINCIPAL, analytics, storage=storage, http_get=fake_http_get
    )

    assert second.tiles_fetched == 0
    assert second.tiles_already_cached == first.tiles_fetched
    assert call_count == calls_after_first_run  # no new upstream calls on the second run


async def test_prefetch_area_raises_for_a_provider_with_no_cache_config() -> None:
    provider = _wmts_provider(id="no-cache", cache=None)
    analytics = _FakeAnalyticsPort({})
    storage = tile_cache_storage_config()

    with pytest.raises(ValueError, match="no cache"):
        await prefetch_area(provider, "boundary-1", PRINCIPAL, analytics, storage=storage)


async def test_prefetch_area_raises_for_a_provider_with_no_zoom_range() -> None:
    provider = _wmts_provider(id="no-zoom", zoom_min=None, zoom_max=None)
    analytics = _FakeAnalyticsPort({})
    storage = tile_cache_storage_config()

    with pytest.raises(ValueError, match="zoom_min"):
        await prefetch_area(provider, "boundary-1", PRINCIPAL, analytics, storage=storage)


async def test_prefetch_area_raises_for_an_unknown_geometry_ref() -> None:
    provider = _wmts_provider(id="unknown-ref")
    analytics = _FakeAnalyticsPort({})
    storage = tile_cache_storage_config()

    with pytest.raises(ValueError, match="not found"):
        await prefetch_area(provider, "does-not-exist", PRINCIPAL, analytics, storage=storage)


async def test_prefetch_area_raises_for_a_point_geometry_ref() -> None:
    point = GeometryRecord(
        geometry_ref="point-1", version=1, kind=GeometryKind.POINT,
        lon=-0.12, lat=51.5, handling=_handling(),
    )
    analytics = _FakeAnalyticsPort({"point-1": point})
    provider = _wmts_provider(id="point-ref")
    storage = tile_cache_storage_config()

    with pytest.raises(ValueError, match="not a polygon"):
        await prefetch_area(provider, "point-1", PRINCIPAL, analytics, storage=storage)
