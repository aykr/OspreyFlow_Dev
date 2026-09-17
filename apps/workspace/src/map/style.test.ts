import { describe, expect, it } from "vitest";

import type { PublicMapProvider } from "../../../../packages/schemas/generated";
import {
  BUNDLED_DARK_STYLE_ID,
  BUNDLED_RASTER_OVERLAY_STYLE_ID,
  buildBundledDarkStyle,
  buildRasterStyle,
  resolveBundledStyle,
} from "./style";

function provider(overrides: Partial<PublicMapProvider> = {}): PublicMapProvider {
  return {
    id: "osm-local",
    label: "OpenStreetMap",
    kind: "vector",
    style: BUNDLED_DARK_STYLE_ID,
    attribution: "© OpenStreetMap contributors",
    licence_id: "ODbL",
    licence_note: null,
    client_scope: "open",
    source: "file:///data/tiles/osm-local.pmtiles",
    ...overrides,
  };
}

describe("buildBundledDarkStyle", () => {
  it("builds a valid style-8 spec with a pmtiles:// source url", () => {
    const style = buildBundledDarkStyle(provider());
    expect(style.version).toBe(8);
    expect(style.sources["osm-local"]).toEqual({
      type: "vector",
      url: "pmtiles://file:///data/tiles/osm-local.pmtiles",
    });
  });

  it("names a source-layer for every declared layer, matching the OpenMapTiles schema", () => {
    const style = buildBundledDarkStyle(provider());
    const sourceLayers = style.layers
      .map((l) => ("source-layer" in l ? l["source-layer"] : undefined))
      .filter((l): l is string => l !== undefined);
    expect(new Set(sourceLayers)).toEqual(
      new Set(["landcover", "water", "boundary", "transportation", "building", "place"]),
    );
  });

  it("references only design-token hex values, never a literal off-token colour", () => {
    const style = buildBundledDarkStyle(provider());
    const KNOWN_HEX = new Set(["#090d0e", "#101314", "#202425", "#66696a", "#e8eced"]);
    for (const layer of style.layers) {
      const paint = (layer as { paint?: Record<string, unknown> }).paint ?? {};
      for (const [key, value] of Object.entries(paint)) {
        if (typeof value === "string" && value.startsWith("#")) {
          expect(KNOWN_HEX.has(value), `${layer.id}.${key} = ${value}`).toBe(true);
        }
      }
    }
  });

  it("rejects a non-vector provider", () => {
    expect(() => buildBundledDarkStyle(provider({ kind: "raster" }))).toThrow(/vector/);
  });

  it("rejects a provider with no directly-fetchable source", () => {
    expect(() => buildBundledDarkStyle(provider({ source: null }))).toThrow(/directly-fetchable/);
  });
});

describe("buildRasterStyle", () => {
  function rasterProvider(overrides: Partial<PublicMapProvider> = {}): PublicMapProvider {
    return provider({
      id: "usgs-national-map",
      kind: "raster",
      style: BUNDLED_RASTER_OVERLAY_STYLE_ID,
      source: null,
      ...overrides,
    });
  }

  it("builds a raster source using the given tile url", () => {
    const style = buildRasterStyle(rasterProvider(), "http://api/v1/map/tiles/usgs/{z}/{x}/{y}");
    expect(style.sources["usgs-national-map"]).toEqual({
      type: "raster",
      tiles: ["http://api/v1/map/tiles/usgs/{z}/{x}/{y}"],
      tileSize: 256,
    });
  });

  it("rejects a non-raster provider", () => {
    expect(() => buildRasterStyle(rasterProvider({ kind: "vector" }), "http://x")).toThrow(
      /raster/,
    );
  });
});

describe("resolveBundledStyle", () => {
  it("resolves the dark style id", () => {
    const style = resolveBundledStyle(BUNDLED_DARK_STYLE_ID, provider(), "http://api");
    expect(style.name).toBe("osprey-dark");
  });

  it("names the light style as a stated follow-up, not a silent failure", () => {
    expect(() =>
      resolveBundledStyle("bundled:osprey-light", provider(), "http://api"),
    ).toThrow(/follow-up/);
  });

  it("rejects an unknown style id", () => {
    expect(() =>
      resolveBundledStyle("bundled:something-else", provider(), "http://api"),
    ).toThrow(/unknown/);
  });

  it("uses the provider's own direct source when present (an unproxied raster provider)", () => {
    const provided = provider({
      id: "usgs-national-map",
      kind: "raster",
      style: BUNDLED_RASTER_OVERLAY_STYLE_ID,
      source: "https://example.test/tiles/{z}/{x}/{y}",
    });
    const style = resolveBundledStyle(BUNDLED_RASTER_OVERLAY_STYLE_ID, provided, "http://api");
    expect(style.sources["usgs-national-map"]).toEqual({
      type: "raster",
      tiles: ["https://example.test/tiles/{z}/{x}/{y}"],
      tileSize: 256,
    });
  });

  it("falls back to the tile-proxy route when the provider has no direct source (proxied)", () => {
    const provided = provider({
      id: "usgs-national-map",
      kind: "raster",
      style: BUNDLED_RASTER_OVERLAY_STYLE_ID,
      source: null,
    });
    const style = resolveBundledStyle(BUNDLED_RASTER_OVERLAY_STYLE_ID, provided, "http://api");
    expect(style.sources["usgs-national-map"]).toEqual({
      type: "raster",
      tiles: ["http://api/v1/map/tiles/usgs-national-map/{z}/{x}/{y}"],
      tileSize: 256,
    });
  });
});
