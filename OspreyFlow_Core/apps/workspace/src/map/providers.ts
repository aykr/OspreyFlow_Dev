// Fetches `GET /v1/map/providers` (`services/api/app.py`) — the basemap
// registry the layer control reads (`spec/02_GLASS_FRONTEND.md` §3.5),
// mirroring `ontology/schema.ts`'s `fetchOntologyRegistry` pattern
// exactly: one fetch per session, no client-side duplication of what
// `osprey.yaml` already declares.
import type { PublicMapConfig, PublicMapProvider } from "../../../../packages/schemas/generated";

export async function fetchMapConfig(baseUrl: string, bearerToken: string): Promise<PublicMapConfig> {
  const response = await fetch(`${baseUrl}/v1/map/providers`, {
    headers: { Authorization: `Bearer ${bearerToken}` },
  });
  if (!response.ok) {
    throw new Error(`GET /v1/map/providers failed: ${response.status}`);
  }
  return (await response.json()) as PublicMapConfig;
}

/** The provider the map should open on — `PublicMapConfig.default`, or
 * `undefined` if that id somehow isn't among the returned providers
 * (never assumed; a caller decides what "no default resolvable" means to
 * it, e.g. falling back to the first provider or showing an error). */
export function defaultProvider(config: PublicMapConfig): PublicMapProvider | undefined {
  return config.providers.find((p) => p.id === config.default);
}

/** The providers the basemap switch offers (P4, `02_GLASS_FRONTEND.md` §3.5's "Basemap switching"):
 * every provider `GET /v1/map/providers` returns that this map can draw, in the deployment's own
 * order. Drawable means a style the Glass builds (`style.ts`'s `resolveBundledStyle`): a vector
 * PMTiles source under the bundled style, or a raster under the raster overlay (its tiles straight
 * from its `source` when the browser fetches it, else through the Conduit's tile proxy, which holds
 * any key). An image, a terrain model or a style not built here is a layer, not a basemap, and is not
 * offered. Nothing in the answer carries a key or a key-bearing address (`public_view`), so neither
 * does the switch. */
export function switchableProviders(config: PublicMapConfig): PublicMapProvider[] {
  return config.providers.filter(
    (p) =>
      (p.kind === "vector" && p.style === "bundled:osprey-dark" && Boolean(p.source)) ||
      (p.kind === "raster" && p.style === "bundled:osprey-raster-overlay"),
  );
}
