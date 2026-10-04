// Fetch wrappers for `/v1/analytics/*` (`services/api/app.py`) — mirrors
// `map/providers.ts`/`site/api.ts`'s conventions exactly: one bare `fetch`
// per call, a bearer header, throw on a non-OK response.
import type {
  CrossFilterRequest,
  EventFilter,
  FirstSeenRequest,
  FirstSeenResult,
  GeoBin,
  GeoBinRequest,
  GeometryRecord,
  Histogram,
  HistogramRequest,
  Sighting,
  SightingRequest,
} from "../../../../packages/schemas/generated";

function authHeaders(bearerToken: string): HeadersInit {
  return { Authorization: `Bearer ${bearerToken}`, "Content-Type": "application/json" };
}

async function postJson<T>(
  apiBaseUrl: string,
  bearerToken: string,
  path: string,
  body: unknown,
  action: string,
): Promise<T> {
  const response = await fetch(`${apiBaseUrl}${path}`, {
    method: "POST",
    headers: authHeaders(bearerToken),
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    throw new Error(`${action} failed: ${response.status}`);
  }
  return (await response.json()) as T;
}

export async function fetchHistogram(
  apiBaseUrl: string,
  bearerToken: string,
  request: HistogramRequest,
): Promise<Histogram> {
  return postJson(apiBaseUrl, bearerToken, "/v1/analytics/histogram", request, "POST .../histogram");
}

export async function fetchCrossFilter(
  apiBaseUrl: string,
  bearerToken: string,
  request: CrossFilterRequest,
): Promise<Record<string, Histogram>> {
  return postJson(
    apiBaseUrl,
    bearerToken,
    "/v1/analytics/cross-filter",
    request,
    "POST .../cross-filter",
  );
}

/** When each node and link first appears under the filter (ADR-087), for the timeline's dimming and
 * its playback. */
export async function fetchFirstSeen(
  apiBaseUrl: string,
  bearerToken: string,
  request: FirstSeenRequest,
): Promise<FirstSeenResult> {
  return postJson(apiBaseUrl, bearerToken, "/v1/analytics/first-seen", request, "POST .../first-seen");
}

export async function fetchGeoBins(
  apiBaseUrl: string,
  bearerToken: string,
  request: GeoBinRequest,
): Promise<GeoBin[]> {
  return postJson(apiBaseUrl, bearerToken, "/v1/analytics/geobins", request, "POST .../geobins");
}

export async function fetchGeometries(
  apiBaseUrl: string,
  bearerToken: string,
  geometryRefs: string[],
): Promise<GeometryRecord[]> {
  if (geometryRefs.length === 0) return [];
  return postJson(
    apiBaseUrl,
    bearerToken,
    "/v1/analytics/geometries",
    { geometry_refs: geometryRefs },
    "POST .../geometries",
  );
}

/** B18's own snail-trail data source, ordered by `occurred_at` server-side
 * (`packages/ports/analytics.py::AnalyticsPort.list_sightings`'s own
 * docstring) — Phase 8 Stage 4f, a real backend gap found and closed while
 * building this, not assumed to already exist. */
export async function fetchSightings(
  apiBaseUrl: string,
  bearerToken: string,
  request: SightingRequest,
): Promise<Sighting[]> {
  return postJson(apiBaseUrl, bearerToken, "/v1/analytics/sightings", request, "POST .../sightings");
}

export type { EventFilter };
