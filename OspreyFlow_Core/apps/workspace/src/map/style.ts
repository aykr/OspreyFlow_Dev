// The bundled dark MapLibre style — `spec/00_ARCHITECTURE.md` §1.2's
// tier-1 "Two MapLibre styles ship with it, dark and light, built
// against `design/tokens.css`".
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

import { activePalette, type Palette } from "../color/palette";
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

/** `provider.source` is a Conduit-relative path (e.g. `/v1/map/local-source/osm-local`) for a
 * tier-1/2 provider backed by a local `file://` source — `services/api/mapconfig_loader.py`'s
 * own `public_view()` rewrites it there, since a browser cannot fetch `file://` at all (Stage
 * 3a's own rehearsal finding, 23 September 2026). Any other shape (an absolute `https://...` —
 * no such case ships today, but the schema does not forbid it) passes through unchanged. */
export function resolvePmtilesSourceUrl(source: string, apiBaseUrl: string): string {
  return source.startsWith("/") ? `${apiBaseUrl}${source}` : source;
}

/** Whether the style draws place labels. MapLibre fails a whole vector tile whose label layer
 * cannot have its glyphs, so without them the map drew nothing (8 October 2026); `glyphsServed`
 * says whether they are there. */
export interface StyleOptions {
  labels: boolean;
  /** The theme's palette (ADR-070); the theme shown now when absent. The style once painted the
   * dark theme's constants in either theme, its land and sea barely apart, and the map read as a
   * black rectangle in the light theme and in the deck (9 October 2026). */
  palette?: Palette;
}

export function buildBundledDarkStyle(
  provider: PublicMapProvider,
  apiBaseUrl: string,
  options: StyleOptions = { labels: true },
): StyleSpecification {
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
  const sourceUrl = resolvePmtilesSourceUrl(provider.source, apiBaseUrl);
  const palette = options.palette ?? activePalette();
  // Land is the raised surface and water the sequential ramp's second step, so the coast reads in
  // either theme; lines and labels are the theme's border and text.
  const land = palette.surfaceRaised;
  const water = palette.seq[1];
  const style: StyleSpecification = {
    version: 8,
    name: "osprey-dark",
    sources: {
      [source]: { type: "vector", url: `pmtiles://${sourceUrl}` },
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
        paint: { "background-color": land },
      },
      {
        id: "landcover",
        type: "fill",
        source,
        "source-layer": "landcover",
        paint: { "fill-color": palette.surfaceHover, "fill-opacity": 0.5 },
      },
      {
        id: "water",
        type: "fill",
        source,
        "source-layer": "water",
        paint: { "fill-color": water },
      },
      {
        id: "boundary",
        type: "line",
        source,
        "source-layer": "boundary",
        paint: {
          "line-color": palette.borderStrong,
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
          "line-color": palette.borderStrong,
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
        paint: { "fill-color": palette.surfaceHover, "fill-opacity": 0.4 },
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
          "text-color": palette.textPrimary,
          "text-halo-color": palette.surfaceApp,
          "text-halo-width": 1,
        },
      },
    ],
  };
  if (options.labels) return style;
  const unlabelled: StyleSpecification = {
    ...style,
    layers: style.layers.filter((layer) => layer.type !== "symbol"),
  };
  delete unlabelled.glyphs;
  return unlabelled;
}

/** The glyph file for the labels' font, as the style names it; the first range is enough to know. */
export const GLYPH_PROBE_PATH = "/fonts/Noto%20Sans%20Regular/0-255.pbf";

/** Whether the label glyphs are served. Not built yet by `scripts/build_local_basemap.py`, and the
 * workspace's nginx answers an unknown path with the Glass's own page, so a 200 alone is not proof:
 * an HTML answer is no glyph. */
export async function glyphsServed(fetchImpl: typeof fetch = fetch): Promise<boolean> {
  try {
    const response = await fetchImpl(GLYPH_PROBE_PATH);
    const type = response.headers.get("content-type") ?? "";
    return response.ok && !type.includes("text/html");
  } catch {
    return false;
  }
}

/** A `kind: raster` provider's style. One XYZ `raster` source/layer;
 * `tileUrl` is either the
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
        paint: { "background-color": activePalette().surfaceApp },
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
  options: StyleOptions = { labels: true },
): StyleSpecification {
  switch (styleId) {
    case BUNDLED_DARK_STYLE_ID:
      return buildBundledDarkStyle(provider, apiBaseUrl, options);
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
