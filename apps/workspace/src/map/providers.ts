// Fetches `GET /v1/map/providers` (`services/api/app.py`) — the basemap
// registry the layer control reads (`docs/02_GLASS_FRONTEND.md` §3.5),
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
