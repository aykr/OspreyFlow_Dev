import { describe, expect, it } from "vitest";

import type { PublicMapProvider } from "../../../../packages/schemas/generated";
import { oklabLightness } from "../color/oklab";
import { paletteFor } from "../color/palette";
import {
  BUNDLED_DARK_STYLE_ID,
  BUNDLED_RASTER_OVERLAY_STYLE_ID,
  buildBundledDarkStyle,
  glyphsServed,
  buildRasterStyle,
  resolveBundledStyle,
} from "./style";

function provider(
  overrides: Partial<PublicMapProvider> = {},
): PublicMapProvider {
  return {
    id: "osm-local",
    label: "OpenStreetMap",
    kind: "vector",
    style: BUNDLED_DARK_STYLE_ID,
    attribution: "© OpenStreetMap contributors",
    licence_id: "ODbL",
    licence_note: null,
    client_scope: "open",
    // Realistic post-fix shape — `services/api/mapconfig_loader.py`'s `public_view()` rewrites a
    // local `file://` source to this Conduit-relative route (Stage 3a's own rehearsal finding,
    // 23 September 2026: a browser cannot fetch `file://` at all).
    source: "/v1/map/local-source/osm-local",
    ...overrides,
  };
}

describe("buildBundledDarkStyle", () => {
  it("builds a valid style-8 spec with a pmtiles:// source url, prefixed with apiBaseUrl", () => {
    const style = buildBundledDarkStyle(provider(), "http://127.0.0.1:8000");
    expect(style.version).toBe(8);
    expect(style.sources["osm-local"]).toEqual({
      type: "vector",
      url: "pmtiles://http://127.0.0.1:8000/v1/map/local-source/osm-local",
    });
  });

  it("passes an absolute source url through unchanged", () => {
    const style = buildBundledDarkStyle(
      provider({ source: "https://example.test/osm-local.pmtiles" }),
      "http://127.0.0.1:8000",
    );
    expect(style.sources["osm-local"]).toEqual({
      type: "vector",
      url: "pmtiles://https://example.test/osm-local.pmtiles",
    });
  });

  it("names a source-layer for every declared layer, matching the OpenMapTiles schema", () => {
    const style = buildBundledDarkStyle(provider(), "http://api");
    const sourceLayers = style.layers
      .map((l) => ("source-layer" in l ? l["source-layer"] : undefined))
      .filter((l): l is string => l !== undefined);
    expect(new Set(sourceLayers)).toEqual(
      new Set([
        "landcover",
        "water",
        "boundary",
        "transportation",
        "building",
        "place",
      ]),
    );
  });

  it("references only design-token hex values, never a literal off-token colour", () => {
    // Every colour of both themed palettes, which `tokens.test.ts` holds to `tokens.css`; the style
    // takes its colours from them (9 October 2026), so a literal hex here would be off-token.
    const KNOWN_HEX = new Set(
      (["light", "dark"] as const).flatMap((theme) =>
        Object.values(paletteFor(theme)).flatMap((v) =>
          typeof v === "string" ? [v] : Array.isArray(v) ? [...v] : [],
        ),
      ),
    );
    for (const theme of ["light", "dark"] as const) {
      const style = buildBundledDarkStyle(provider(), "http://api", {
        labels: true,
        palette: paletteFor(theme),
      });
      for (const layer of style.layers) {
        const paint =
          (layer as { paint?: Record<string, unknown> }).paint ?? {};
        for (const [key, value] of Object.entries(paint)) {
          if (typeof value === "string" && value.startsWith("#")) {
            expect(KNOWN_HEX.has(value), `${layer.id}.${key} = ${value}`).toBe(
              true,
            );
          }
        }
      }
    }
  });

  it("rejects a non-vector provider", () => {
    expect(() =>
      buildBundledDarkStyle(provider({ kind: "raster" }), "http://api"),
    ).toThrow(/vector/);
  });

  it("rejects a provider with no directly-fetchable source", () => {
    expect(() =>
      buildBundledDarkStyle(provider({ source: null }), "http://api"),
    ).toThrow(/directly-fetchable/);
  });
});

describe("the dark style's labels", () => {
  // 8 October 2026: the glyph files are not built, so `/fonts/...` came back as the Glass's own
  // page; MapLibre fails a whole tile whose label layer cannot have its glyphs, and the map drew
  // nothing at all. Without glyphs the style has no label layer, so the map draws unlabelled.
  it("has a label layer and its glyphs when the glyphs are served", () => {
    const style = buildBundledDarkStyle(provider(), "http://api", {
      labels: true,
    });
    expect(style.layers.some((l) => l.type === "symbol")).toBe(true);
    expect(style.glyphs).toBeDefined();
  });

  it("has neither when they are not", () => {
    const style = buildBundledDarkStyle(provider(), "http://api", {
      labels: false,
    });
    expect(style.layers.some((l) => l.type === "symbol")).toBe(false);
    expect(style.glyphs).toBeUndefined();
    expect(style.layers.map((l) => l.id)).toContain("water");
  });
});

describe("glyphsServed", () => {
  const answer = (status: number, type: string) =>
    (async () =>
      new Response("x", {
        status,
        headers: { "content-type": type },
      })) as typeof fetch;

  it("is true for a glyph file", async () => {
    expect(await glyphsServed(answer(200, "application/x-protobuf"))).toBe(
      true,
    );
  });

  it("is false for the Glass's own page answering an unknown path", async () => {
    expect(await glyphsServed(answer(200, "text/html"))).toBe(false);
  });

  it("is false when missing or unreachable", async () => {
    expect(await glyphsServed(answer(404, "text/plain"))).toBe(false);
    expect(
      await glyphsServed((async () => {
        throw new TypeError("offline");
      }) as typeof fetch),
    ).toBe(false);
  });
});

describe("buildRasterStyle", () => {
  function rasterProvider(
    overrides: Partial<PublicMapProvider> = {},
  ): PublicMapProvider {
    return provider({
      id: "usgs-national-map",
      kind: "raster",
      style: BUNDLED_RASTER_OVERLAY_STYLE_ID,
      source: null,
      ...overrides,
    });
  }

  it("builds a raster source using the given tile url", () => {
    const style = buildRasterStyle(
      rasterProvider(),
      "http://api/v1/map/tiles/usgs/{z}/{x}/{y}",
    );
    expect(style.sources["usgs-national-map"]).toEqual({
      type: "raster",
      tiles: ["http://api/v1/map/tiles/usgs/{z}/{x}/{y}"],
      tileSize: 256,
    });
  });

  it("rejects a non-raster provider", () => {
    expect(() =>
      buildRasterStyle(rasterProvider({ kind: "vector" }), "http://x"),
    ).toThrow(/raster/);
  });
});

describe("resolveBundledStyle", () => {
  it("resolves the dark style id", () => {
    const style = resolveBundledStyle(
      BUNDLED_DARK_STYLE_ID,
      provider(),
      "http://api",
    );
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
    const style = resolveBundledStyle(
      BUNDLED_RASTER_OVERLAY_STYLE_ID,
      provided,
      "http://api",
    );
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
    const style = resolveBundledStyle(
      BUNDLED_RASTER_OVERLAY_STYLE_ID,
      provided,
      "http://api",
    );
    expect(style.sources["usgs-national-map"]).toEqual({
      type: "raster",
      tiles: ["http://api/v1/map/tiles/usgs-national-map/{z}/{x}/{y}"],
      tileSize: 256,
    });
  });
});

// 9 October 2026: the map rendered as a black rectangle in the deck. The bundled style painted with
// the dark theme's constants in either theme, and even in dark its land (#101314) and sea (#090d0e)
// were barely apart, so the coast hardly showed. It is built from the themed palette (ADR-070), and
// land and water stand apart in either theme.
describe("the bundled basemap's colours", () => {
  const paintOf = (
    style: ReturnType<typeof buildBundledDarkStyle>,
    id: string,
    key: string,
  ) =>
    (style.layers.find((l) => l.id === id) as unknown as { paint: Record<string, string> })
      .paint[key] as string;

  it.each(["light", "dark"] as const)(
    "in the %s theme, uses that theme's palette, land and water apart",
    (theme) => {
      const palette = paletteFor(theme);
      const style = buildBundledDarkStyle(provider(), "", {
        labels: true,
        palette,
      });
      const land = paintOf(style, "background", "background-color");
      const water = paintOf(style, "water", "fill-color");
      expect(land).toBe(palette.surfaceRaised);
      expect(
        Math.abs(oklabLightness(land) - oklabLightness(water)),
      ).toBeGreaterThanOrEqual(0.08);
      expect(paintOf(style, "place-label", "text-color")).toBe(
        palette.textPrimary,
      );
    },
  );
});
