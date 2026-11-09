import { describe, expect, it } from "vitest";

import type { PublicMapConfig, PublicMapProvider } from "../../../../packages/schemas/generated";
import { defaultProvider, switchableProviders } from "./providers";

function provider(id: string): PublicMapProvider {
  return {
    id,
    label: id,
    kind: "vector",
    style: "bundled:osprey-dark",
    attribution: "© OpenStreetMap contributors",
    licence_id: "ODbL",
    licence_note: null,
    client_scope: "open",
    source: `file:///data/tiles/${id}.pmtiles`,
  };
}

describe("defaultProvider", () => {
  it("returns the provider named by default", () => {
    const config: PublicMapConfig = {
      default: "osm-local",
      providers: [provider("osm-local"), provider("os-zoomstack")],
    };
    expect(defaultProvider(config)?.id).toBe("osm-local");
  });

  it("returns undefined when the default id is not among the providers", () => {
    const config: PublicMapConfig = { default: "missing", providers: [provider("osm-local")] };
    expect(defaultProvider(config)).toBeUndefined();
  });
});

describe("switchableProviders", () => {
  it("offers every provider the map can draw, in the deployment's order, and nothing else", () => {
    const raster: PublicMapProvider = {
      ...provider("hosted-raster"),
      kind: "raster",
      style: "bundled:osprey-raster-overlay",
      client_scope: "per-deployment",
      source: null, // proxied: the Conduit holds its address and any key
    };
    const image: PublicMapProvider = { ...provider("site-image"), kind: "image", style: null };
    const unbuiltStyle: PublicMapProvider = { ...provider("light"), style: "bundled:osprey-light" };
    const noSource: PublicMapProvider = { ...provider("proxied-vector"), source: null };
    const config: PublicMapConfig = {
      default: "osm-local",
      providers: [provider("osm-local"), image, raster, unbuiltStyle, noSource],
    };
    expect(switchableProviders(config).map((p) => p.id)).toEqual(["osm-local", "hosted-raster"]);
  });
});
