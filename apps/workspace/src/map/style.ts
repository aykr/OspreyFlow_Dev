// The bundled dark MapLibre style — `docs/00_ARCHITECTURE.md` §1.2's
// tier-1 "Two MapLibre styles ship with it, dark and light, built
// against `design/tokens.css`", `docs/07_BUILD_PLAN.md` Phase 5.
//
// **Dark only for now.** Same deferral `color/tokens.ts`'s
// `SURFACE_PANEL_DARK_HEX` already states for node rendering: Checkpoint 2
// ships the dark theme as the working default; light-theme generation
// (and the contrast-floor CI check against it) is a named follow-up, not
// a silent gap.
//
// **A minimal OpenMapTiles-schema style, not an exhaustive cartographic
// one.** Assumes the PMTiles source was built with planetiler's default
// (OpenMapTiles-compatible) profile — `scripts/build_local_basemap.py`'s
// own doc records that this hasn't been run against real data yet. Seven
// layers (background, water, landcover, boundary, transportation,
// building, place labels) prove the mechanism and stay legible; a
// production-grade style would classify roads/places by `class`/`rank`
// with many more zoom-dependent rules. Recorded as a stated scope
// boundary, the same way `GlassCanvas.tsx` records straight (not curved)
// edges as a disclosed simplification rather than a silent one.
import type { StyleSpecification } from "maplibre-gl";

import {
  BORDER_STRONG_DARK_HEX,
  SURFACE_APP_DARK_HEX,
  SURFACE_RAISED_DARK_HEX,
  SURFACE_SUNKEN_DARK_HEX,
  TEXT_PRIMARY_DARK_HEX,
} from "../color/tokens";
import type { PublicMapProvider } from "../../../../packages/schemas/generated";

export const BUNDLED_DARK_STYLE_ID = "bundled:osprey-dark";
export const BUNDLED_LIGHT_STYLE_ID = "bundled:osprey-light";
// `00_ARCHITECTURE.md` §1.2's worked ESRI profile example uses this exact
// id for a tier-4 raster overlay's style — `providers/usgs-national-map.
// yaml` (Checkpoint 3a) already declares it as its own `style:` value.
export const BUNDLED_RASTER_OVERLAY_STYLE_ID = "bundled:osprey-raster-overlay";

/** The one PMTiles source every layer below reads from — named after the
 * provider itself so two providers active at once (a future layer-control
 * capability, not this checkpoint's) never collide. */
function sourceIdFor(provider: PublicMapProvider): string {
  return provider.id;
}

export function buildBundledDarkStyle(provider: PublicMapProvider): StyleSpecification {
  if (provider.kind !== "vector") {
    throw new Error(
      `buildBundledDarkStyle only supports a "vector" provider (planetiler PMTiles) — ` +
        `got ${JSON.stringify(provider.kind)} for provider ${provider.id}`,
    );
  }
  if (!provider.source) {
    throw new Error(
      `provider ${provider.id} has no directly-fetchable source (tier 3/4 proxied provider?) — ` +
        `bundled styles are tier-1/2 local-PMTiles only`,
    );
  }
  const source = sourceIdFor(provider);
  return {
    version: 8,
    name: "osprey-dark",
    sources: {
      [source]: { type: "vector", url: `pmtiles://${provider.source}` },
    },
    // Self-hosted, not a CDN — `05_DEPLOYMENT.md`'s air-gapped requirement
    // applies to map labels the same way it does to the UI's own fonts
    // (`00_ARCHITECTURE.md` §7: "self-host them; do not load from a CDN").
    // The glyph PBFs themselves are not produced by
    // `scripts/build_local_basemap.py` yet — a stated gap, not a silent
    // one; this path is where a deployment serves them from once it does.
    glyphs: "/fonts/{fontstack}/{range}.pbf",
    layers: [
      {
        id: "background",
        type: "background",
        paint: { "background-color": SURFACE_APP_DARK_HEX },
      },
      {
        id: "landcover",
        type: "fill",
        source,
        "source-layer": "landcover",
        paint: { "fill-color": SURFACE_RAISED_DARK_HEX, "fill-opacity": 0.5 },
      },
      {
        id: "water",
        type: "fill",
        source,
        "source-layer": "water",
        paint: { "fill-color": SURFACE_SUNKEN_DARK_HEX },
      },
      {
        id: "boundary",
        type: "line",
        source,
        "source-layer": "boundary",
        paint: {
          "line-color": BORDER_STRONG_DARK_HEX,
          "line-width": 0.5,
          "line-dasharray": [2, 2],
        },
      },
      {
        id: "transportation",
        type: "line",
        source,
        "source-layer": "transportation",
        paint: {
          "line-color": BORDER_STRONG_DARK_HEX,
          "line-width": ["interpolate", ["linear"], ["zoom"], 8, 0.3, 16, 2],
          "line-opacity": 0.6,
        },
      },
      {
        id: "building",
        type: "fill",
        source,
        "source-layer": "building",
        minzoom: 14,
        paint: { "fill-color": SURFACE_RAISED_DARK_HEX, "fill-opacity": 0.4 },
      },
      {
        id: "place-label",
        type: "symbol",
        source,
        "source-layer": "place",
        layout: {
          "text-field": ["get", "name"],
          "text-font": ["Noto Sans Regular"],
          "text-size": ["interpolate", ["linear"], ["zoom"], 4, 9, 14, 14],
        },
        paint: {
          "text-color": TEXT_PRIMARY_DARK_HEX,
          "text-halo-color": SURFACE_APP_DARK_HEX,
          "text-halo-width": 1,
        },
      },
    ],
  };
}

/** A `kind: raster` provider's style — `07_BUILD_PLAN.md` Phase 5
 * Checkpoint 3b. One XYZ `raster` source/layer; `tileUrl` is either the
 * provider's own direct `source` (an unproxied raster provider) or the
 * Conduit's tile-proxy route (`resolveBundledStyle`'s own caller builds
 * whichever applies — this function only renders the URL it's given). */
export function buildRasterStyle(
  provider: PublicMapProvider,
  tileUrl: string,
): StyleSpecification {
  if (provider.kind !== "raster") {
    throw new Error(
      `buildRasterStyle only supports a "raster" provider — ` +
        `got ${JSON.stringify(provider.kind)} for provider ${provider.id}`,
    );
  }
  const source = sourceIdFor(provider);
  return {
    version: 8,
    name: "osprey-raster-overlay",
    sources: {
      [source]: { type: "raster", tiles: [tileUrl], tileSize: 256 },
    },
    layers: [
      {
        id: "background",
        type: "background",
        paint: { "background-color": SURFACE_APP_DARK_HEX },
      },
      { id: "raster-overlay", type: "raster", source },
    ],
  };
}

/** `MapProvider.style`'s bundled ids (`00_ARCHITECTURE.md` §1.2's
 * `style: bundled:osprey-dark`) resolve here rather than to a static
 * asset file — a single tested source of truth against `color/tokens.ts`,
 * not a JSON file that can drift from it unnoticed. `apiBaseUrl` is only
 * used by the raster-overlay case, to build the tile-proxy fallback URL
 * when the provider has no direct `source` (any `proxy != "none"`
 * provider, per `mapconfig_loader.public_view()`'s existing logic). */
export function resolveBundledStyle(
  styleId: string | null,
  provider: PublicMapProvider,
  apiBaseUrl: string,
): StyleSpecification {
  switch (styleId) {
    case BUNDLED_DARK_STYLE_ID:
      return buildBundledDarkStyle(provider);
    case BUNDLED_LIGHT_STYLE_ID:
      throw new Error(
        "the light MapLibre style is a stated follow-up, not yet built (see this module's " +
          "own docstring) — bundled:osprey-light cannot resolve yet",
      );
    case BUNDLED_RASTER_OVERLAY_STYLE_ID: {
      const tileUrl =
        provider.source ?? `${apiBaseUrl}/v1/map/tiles/${provider.id}/{z}/{x}/{y}`;
      return buildRasterStyle(provider, tileUrl);
    }
    default:
      throw new Error(`unknown or unsupported bundled style id: ${JSON.stringify(styleId)}`);
  }
}
