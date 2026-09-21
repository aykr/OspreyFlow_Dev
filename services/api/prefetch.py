"""Scheduled area-of-operations tile pre-warm — `docs/00_ARCHITECTURE.md`
§1.2's tile proxy, `docs/05_DEPLOYMENT.md` §2.2's "Prefetch area of
operations" (tier 3's own harness offer: "a drawn or uploaded boundary"),
`docs/07_BUILD_PLAN.md`'s Phase 5 known-gaps list. Distinct from `services/api/tile_cache.py`'s
read-through cache: that module caches a tile the first time it is
requested; this module warms a named area's tiles *before* anyone asks,
so routine work over that area makes zero live upstream requests
(`docs/00_ARCHITECTURE.md` §1.2: "a prefetched area makes no live requests
during routine work" — the whole reason tier 3's harness offers this at
all, since a live tile request to a hosted API discloses where an analyst
is looking).

Each `PrefetchCache.prefetch_areas` entry is a `geometry_ref` into
`AnalyticsPort`'s polygon-capable geometry store (Phase 5's known-gaps closure) — matching
`docs/05_DEPLOYMENT.md` §2.2's "drawn or uploaded boundary" language,
which is a real (possibly non-rectangular) shape, not a bare bounding-box
string a deployer types by hand.

**No in-process scheduler.** This is a plain, directly-invokable batch
entrypoint, mirroring `services/ingest/__main__.py`'s own documented
convention exactly: "invoked directly by whatever schedules the batch (a
Kubernetes Job, `docker run`, cron) — not an `osprey` unified CLI." A
deployment's own external scheduler (cron, a Kubernetes CronJob) is what
actually calls this on a schedule — no APScheduler/Celery/task-queue
dependency is introduced (ADR-005: no orchestration framework in the
extraction core; ADR-013: batch/micro-batch only).
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import duckdb

from adapters.analytics_duckdb.schema import load_spatial_extension
from ports.analytics import AnalyticsPort
from schemas.domain import Principal
from schemas.mapconfig import MapConfig, MapProvider
from services.ingest.staging import ObjectStorageConfig

from .mapconfig_loader import load_map_config
from .tile_cache import (
    cache_key_for,
    read_cached_tile,
    tile_cache_storage_config,
    write_cached_tile,
)
from .tile_math import tile_range_for_bbox, tiles_in_range
from .tile_proxy import build_upstream_url, fetch_tile


@dataclass(frozen=True)
class PrefetchReport:
    provider_id: str
    geometry_ref: str
    tiles_fetched: int
    tiles_already_cached: int


def _bbox_from_wkb(geometry_wkb: bytes) -> tuple[float, float, float, float]:
    """`(min_lon, min_lat, max_lon, max_lat)` — a small, dedicated
    connection rather than a new `AnalyticsPort` method: this is pure
    geometry math over WKB bytes `analytics.get_geometry` already fetched
    (and already access-filtered), not a second data-access step."""
    con = duckdb.connect(":memory:")
    try:
        load_spatial_extension(con)
        # A one-row-literal subquery with no WHERE/JOIN to filter it out always produces exactly
        # one row — `fetchone()`'s `| None` in DuckDB's own stub is for the general case, not
        # this query; the `cast` says so rather than adding an `if row is None: raise` branch
        # that can never run.
        row = cast(
            "tuple[float, float, float, float]",
            con.execute(
                "SELECT ST_XMin(g), ST_YMin(g), ST_XMax(g), ST_YMax(g) "
                "FROM (SELECT ST_GeomFromWKB(?) AS g)",
                [geometry_wkb],
            ).fetchone(),
        )
        return (row[0], row[1], row[2], row[3])
    finally:
        con.close()


async def prefetch_area(
    provider: MapProvider,
    geometry_ref: str,
    principal: Principal,
    analytics: AnalyticsPort,
    *,
    storage: ObjectStorageConfig,
    http_get: Callable[[str], Awaitable[bytes]] | None = None,
) -> PrefetchReport:
    """Warms every tile covering `geometry_ref`'s stored polygon, across
    `provider.zoom_min..provider.zoom_max`. Raises naming what is missing
    if the provider has no cache config or no discovered zoom range — the
    same "flag rather than guess" discipline `tile_proxy.py`'s own WMTS
    KVP builder already follows for its own missing-field case."""
    if provider.cache is None:
        raise ValueError(f"provider {provider.id!r} declares no cache — nothing to prefetch into")
    if provider.zoom_min is None or provider.zoom_max is None:
        raise ValueError(
            f"provider {provider.id!r} has no zoom_min/zoom_max — required to know which "
            "zoom levels to prefetch (register_tier4_provider discovers these)"
        )

    record = await analytics.get_geometry(geometry_ref, principal)
    if record is None:
        raise ValueError(f"geometry_ref {geometry_ref!r} not found or not visible to principal")
    if record.geometry_wkb is None:
        raise ValueError(f"geometry_ref {geometry_ref!r} is not a polygon — nothing to bound")

    min_lon, min_lat, max_lon, max_lat = _bbox_from_wkb(record.geometry_wkb)

    fetch = fetch_tile if http_get is None else (
        lambda url: fetch_tile(url, http_get=http_get)  # noqa: E731
    )

    tiles_fetched = 0
    tiles_already_cached = 0
    for zoom in range(provider.zoom_min, provider.zoom_max + 1):
        x_min, x_max, y_min, y_max = tile_range_for_bbox(min_lon, min_lat, max_lon, max_lat, zoom)
        for x, y in tiles_in_range(x_min, x_max, y_min, y_max):
            cache_key = cache_key_for(provider.id, zoom, x, y)
            if read_cached_tile(
                storage=storage, object_key=cache_key, ttl_days=provider.cache.ttl_days
            ) is not None:
                tiles_already_cached += 1
                continue
            url = build_upstream_url(provider, zoom, x, y)
            tile_bytes = await fetch(url)
            write_cached_tile(tile_bytes, storage=storage, object_key=cache_key)
            tiles_fetched += 1

    return PrefetchReport(
        provider_id=provider.id,
        geometry_ref=geometry_ref,
        tiles_fetched=tiles_fetched,
        tiles_already_cached=tiles_already_cached,
    )


async def prefetch_all(
    config: MapConfig, principal: Principal, analytics: AnalyticsPort
) -> list[PrefetchReport]:
    """Every `prefetch_areas` entry of every provider that declares a
    cache — what an external cron/CronJob actually invokes via this
    module's own CLI entrypoint below."""
    storage = tile_cache_storage_config()
    reports: list[PrefetchReport] = []
    for provider in config.providers:
        if provider.cache is None:
            continue
        for geometry_ref in provider.cache.prefetch_areas:
            reports.append(
                await prefetch_area(provider, geometry_ref, principal, analytics, storage=storage)
            )
    return reports


# --- CLI entrypoint, mirroring scripts/verify_map.py's exact shape ----------


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m services.api.prefetch",
        description="Pre-warms every provider's declared prefetch_areas into the tile cache.",
    )
    parser.add_argument("config_path", type=Path)
    return parser.parse_args(argv)


async def _run(args: argparse.Namespace) -> int:
    from adapters.analytics_duckdb.adapter import AnalyticsDuckDBAdapter
    from adapters.analytics_duckdb.schema import create_events_table, create_geometries_table
    from ontology.handling import load_uk_le_scheme

    config = load_map_config(args.config_path)
    scheme = load_uk_le_scheme()
    # A system principal, the same category `AnalyticsPort.load_geometries`
    # itself is (`packages/ports/analytics.py`'s own "not principal-scoped
    # writes" note) — a scheduled pre-warm job is a backend operation
    # attributed by its own run, not by an analyst's session. Cleared to
    # the scheme's own highest declared classification, not a value this
    # module invents — `evaluate_handling` raises for a clearance the
    # active scheme does not declare at all.
    principal = Principal(
        id="prefetch-job", clearance=scheme.classification[-1], org_unit="system"
    )

    con = duckdb.connect(str(Path(args.config_path).parent / "analytics.duckdb"))
    create_events_table(con)
    create_geometries_table(con)
    analytics = AnalyticsDuckDBAdapter(con, scheme)

    reports = await prefetch_all(config, principal, analytics)
    for report in reports:
        print(
            f"prefetch: {report.provider_id}/{report.geometry_ref}: "
            f"{report.tiles_fetched} fetched, {report.tiles_already_cached} already cached"
        )
    con.close()
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
