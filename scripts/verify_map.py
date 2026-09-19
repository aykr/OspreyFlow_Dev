"""`osprey verify map` — `docs/00_ARCHITECTURE.md` §1.2.1's "Verify runs
after any provider change: it fetches a sample tile at three zoom levels,
asserts the CRS and the zoom range the platform expects, renders a fixture
graph over it and compares against a stored reference for contrast floor
compliance, and confirms attribution is present", `docs/07_BUILD_PLAN.md`
Phase 5's own "Verify parity check... CRS, zoom range, contrast floor over
a fixture graph, attribution presence" bullet.

No `osprey` CLI yet (`CLAUDE.md`'s own Conventions) — a plain,
directly-runnable script now, mirroring `scripts/build_local_basemap.py`'s
exact shape: named stage functions, an injectable `Callable` for the one
network-dependent stage, a frozen result dataclass, a
`_parse_args`/`_run`/`main` CLI entrypoint.

**Two checks live here; the third lives in Playwright, not this file.**
Attribution and CRS/zoom are plain Python checks against a `MapConfig` —
no browser needed. The contrast-floor check (§1.2.1's "renders a fixture
graph over it and compares... for contrast floor compliance") is a
rendered-pixel/reference-image comparison, genuinely different from
`a11y/a11y.spec.ts`'s axe-core DOM-rule check (component contrast, no map
involved) — it lives in `apps/workspace/map-verify/contrast.spec.ts`,
using Playwright's own `toHaveScreenshot()`, and is not wrapped by this
script (a Python process cannot drive a browser's rendering pipeline
itself without becoming a second Playwright integration, which already
exists for exactly this).

**CRS/zoom is checked only for a tier-4 provider with a live `endpoint`.**
Tier 1-3 providers are WGS84/Web Mercator by construction (a local PMTiles/
vector file, or `source_crs` reprojected at ingest) — there is no
`zoom_min`/`zoom_max` field on `MapProvider` to check them against, so
this is a documented no-op for those tiers rather than an invented check.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path

from services.api.mapconfig_loader import load_map_config, public_view
from services.api.tier4_registration import (
    DiscoveredCapabilities,
    UnsupportedProjectionError,
    register_tier4_provider,
)

from schemas.mapconfig import MapConfig, MapProvider


@dataclass(frozen=True)
class VerifyIssue:
    provider_id: str
    check: str
    detail: str


@dataclass(frozen=True)
class VerifyReport:
    issues: tuple[VerifyIssue, ...]

    @property
    def passed(self) -> bool:
        return not self.issues


def check_attribution(provider: MapProvider) -> VerifyIssue | None:
    """`public_view()` must carry `attribution` through unchanged — a
    regression guard against `mapconfig_loader.py`'s own projection ever
    silently dropping or altering it, not a check that could plausibly
    fail today given that function's current implementation."""
    view = public_view(provider)
    if not provider.attribution:
        return VerifyIssue(provider.id, "attribution", "provider declares no attribution")
    if view.attribution != provider.attribution:
        return VerifyIssue(
            provider.id, "attribution", "attribution changed between MapProvider and public_view()"
        )
    return None


async def check_crs_and_zoom(
    provider: MapProvider,
    *,
    register: Callable[[str], Awaitable[DiscoveredCapabilities]] = register_tier4_provider,
) -> VerifyIssue | None:
    """A no-op for anything but a tier-4 provider with a live `endpoint` —
    see this module's own docstring for why tiers 1-3 have nothing to
    check here."""
    if provider.service is None or provider.endpoint is None:
        return None
    try:
        await register(provider.endpoint)
    except UnsupportedProjectionError as exc:
        return VerifyIssue(provider.id, "crs", str(exc))
    return None


async def verify_map(
    config: MapConfig,
    *,
    register: Callable[[str], Awaitable[DiscoveredCapabilities]] = register_tier4_provider,
) -> VerifyReport:
    issues: list[VerifyIssue] = []
    for provider in config.providers:
        attribution_issue = check_attribution(provider)
        if attribution_issue is not None:
            issues.append(attribution_issue)
        crs_issue = await check_crs_and_zoom(provider, register=register)
        if crs_issue is not None:
            issues.append(crs_issue)
    return VerifyReport(issues=tuple(issues))


# --- CLI entrypoint, mirroring scripts/build_local_basemap.py's shape -------


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.verify_map",
        description="Verifies attribution and (for tier-4 providers) CRS/zoom for an osprey.yaml.",
    )
    parser.add_argument("config_path", type=Path)
    return parser.parse_args(argv)


async def _run(args: argparse.Namespace) -> int:
    config = load_map_config(args.config_path)
    report = await verify_map(config)
    if report.passed:
        print(f"verify map: {len(config.providers)} provider(s) passed.")
        return 0
    for issue in report.issues:
        print(f"verify map: {issue.provider_id}: {issue.check}: {issue.detail}", file=sys.stderr)
    return 1


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
