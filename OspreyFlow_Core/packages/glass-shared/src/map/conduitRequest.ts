// Which of MapLibre's own reads carry the analyst's bearer token: the Conduit's, and nothing else's.
// Split out of `MapView.tsx` (8 October 2026) because it had tested `apiBaseUrl` for truth, and the
// deployed image's address is `""`, this origin through nginx, so a site's aerial image went
// unauthorised there. Matching by prefix alone cannot be the fix: every URL starts with `""`, a
// third-party tile server's included. The address is resolved against this page's origin and a
// read is the Conduit's only when it is under that origin's `/v1/`.

/** The request MapLibre should send for `url`, with the token, when it is the Conduit's own read;
 * `undefined` (MapLibre's own request, unchanged) otherwise. */
export function conduitRequest(
  url: string,
  apiBaseUrl: string,
  bearerToken: string,
  origin: string,
): { url: string; headers: Record<string, string> } | undefined {
  if (!bearerToken) return undefined;
  const conduit = new URL(`${apiBaseUrl.replace(/\/+$/, "")}/v1/`, `${origin}/`).href;
  return url.startsWith(conduit)
    ? { url, headers: { Authorization: `Bearer ${bearerToken}` } }
    : undefined;
}
