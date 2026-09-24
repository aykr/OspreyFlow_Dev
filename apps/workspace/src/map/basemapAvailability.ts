// Preflight check for a tier-1/2 local PMTiles source — Stage 3a's own rehearsal finding, 23
// September 2026: when `scripts/build_local_basemap.py` has never been run, the pmtiles source
// file does not exist, and the map view rendered a silent blank canvas rather than telling the
// operator what was wrong. `services/api/app.py`'s `get_map_local_source_route` 404s with a
// named `detail` in exactly this case; this module is the one place that shape is read, so
// `MapView.tsx` never has to parse a response body itself.
//
// A ranged `GET` (`Range: bytes=0-0`), not a `HEAD` — `FileResponse`'s own Range handling
// (`services/api/app.py`'s docstring) answers a ranged `GET` unconditionally, while a bare `GET`
// route registered with FastAPI's `@app.get(...)` does not automatically also answer `HEAD` the
// way a raw Starlette `Route` would, so a `HEAD` preflight would be a shakier proxy for "can the
// pmtiles library actually read this file" than the ranged request it will make for real.
export class BasemapUnavailableError extends Error {}

export async function checkBasemapAvailable(
  sourceUrl: string,
  bearerToken: string | undefined,
  fetchImpl: typeof fetch = fetch,
): Promise<void> {
  const headers: Record<string, string> = { Range: "bytes=0-0" };
  if (bearerToken) headers.Authorization = `Bearer ${bearerToken}`;
  const response = await fetchImpl(sourceUrl, { headers });
  if (response.status === 404) {
    let detail = "basemap not built";
    try {
      const body = (await response.json()) as { detail?: unknown };
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      // Keep the default detail — the route always sends JSON, but a non-JSON 404 from
      // somewhere else in front of it (a proxy, a misconfigured base URL) shouldn't crash here.
    }
    throw new BasemapUnavailableError(detail);
  }
  if (!response.ok && response.status !== 206) {
    throw new Error(`GET ${sourceUrl} failed: ${response.status}`);
  }
}
