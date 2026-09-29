import { describe, expect, it } from "vitest";

import type { PublicMapConfig, PublicMapProvider } from "../../../../packages/schemas/generated";
import { defaultProvider } from "./providers";

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
