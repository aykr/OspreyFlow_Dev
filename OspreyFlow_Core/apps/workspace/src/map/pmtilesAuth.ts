// **The bearer token on the basemap's own tile reads.** Found 26 September 2026, the first time
// a real PMTiles basemap was built and opened in the Glass (round 12, Stage 3a's residual).
//
// `MapView.tsx` passes MapLibre a `transformRequest` that attaches the bearer token to any URL
// under this deployment's own API, and its own comment already recorded that this is "inert for
// the PMTiles basemap (fetched through the `pmtiles://` protocol handler, never this callback)".
// That was accurate; what nobody had noticed is what it costs. The basemap's source is
// `/v1/map/local-source/{provider_id}` on the Conduit, and the Conduit requires a bearer token on
// it like every other route — so every tile read the pmtiles protocol issued came back 401 and
// the map drew nothing at all.
//
// It failed *silently*, which is why it survived. `basemapAvailability.ts`'s preflight uses
// `fetch` directly and does pass the token, so it got its 206 and the "Basemap not built" alert —
// added for exactly this class of blank map — correctly stayed hidden. Everything observable said
// the basemap was fine except the map itself, which was empty.
//
// The fix is the `pmtiles` library's own supported shape: register a `PMTiles` instance built on
// a `FetchSource` carrying the header, so the protocol handler resolves `pmtiles://<url>` to that
// instance instead of constructing an unauthenticated source of its own.
import { FetchSource, PMTiles, type Protocol } from "pmtiles";

/** Builds the authorised source for one provider's PMTiles URL.
 *
 * Split out of `MapView.tsx` and given its own name so it can be asserted without a browser,
 * a MapLibre instance or a real tile server — `pmtilesAuth.test.ts` is the test that fails if
 * the header stops being attached, which is the whole of this module's reason to exist. */
export function authorisedPmtilesSource(url: string, bearerToken: string | undefined): PMTiles {
  // No token is a legitimate configuration (an unauthenticated tier-3/4 source, or a Conduit
  // running without auth in a test), and is not the same thing as an empty header: sending
  // `Authorization: Bearer undefined` would turn a working anonymous read into a 401.
  const headers = new Headers();
  if (bearerToken) headers.set("Authorization", `Bearer ${bearerToken}`);
  return new PMTiles(new FetchSource(url, headers));
}

/** Registers that source with the shared protocol handler, keyed by its own URL.
 *
 * Idempotent per URL in the sense that matters: `Protocol.add` overwrites the entry for a given
 * source key, so re-mounting the Map view, or switching provider and switching back, replaces the
 * registration rather than accumulating handlers. A token that has been refreshed since the last
 * mount therefore takes effect on the next one, which is the behaviour a long session needs. */
export function registerAuthorisedPmtilesSource(
  protocol: Protocol,
  url: string,
  bearerToken: string | undefined,
): PMTiles {
  const source = authorisedPmtilesSource(url, bearerToken);
  protocol.add(source);
  return source;
}
