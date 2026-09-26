// The test that fails if the basemap's tile reads stop carrying the bearer token — the defect
// `pmtilesAuth.ts`'s own header describes, found on 26 September 2026 when a real PMTiles build
// was opened in the Glass for the first time and every tile read came back 401.
//
// Asserted here, in a unit test, and *also* end to end in `apps/workspace/live/basemap.spec.ts`.
// Both, deliberately, because neither is sufficient on its own: this one runs in `make ci` and
// would catch a regression on any pull request, but it can only prove the header is attached to
// the source object, not that the tile pipeline uses that source; the live spec proves the
// pipeline but needs a stack nobody has up in CI. The failure this pair exists for got through
// precisely because the project had the second kind of coverage only in prose.
import { describe, expect, it } from "vitest";

import { authorisedPmtilesSource, registerAuthorisedPmtilesSource } from "./pmtilesAuth";

const SOURCE_URL = "http://127.0.0.1:8000/v1/map/local-source/osm-local-berkshire";
const TOKEN = "eyJhbGciOiJSUzI1NiJ9.test-token";

/** Reads the headers back off the `FetchSource` the module built. Deliberately reaching into
 * the library's own object rather than asserting on a mock of it: the thing under test is what
 * `pmtiles` will actually send, and a hand-written double of `FetchSource` would prove only that
 * this file agrees with itself — the exact shape `CLAUDE.md` rule 15's second worked example
 * names. */
function headersOf(source: ReturnType<typeof authorisedPmtilesSource>): Headers {
  return (source.source as unknown as { customHeaders: Headers }).customHeaders;
}

describe("authorisedPmtilesSource", () => {
  it("attaches the bearer token the Conduit requires on /v1/map/local-source", () => {
    const headers = headersOf(authorisedPmtilesSource(SOURCE_URL, TOKEN));

    expect(
      headers.get("Authorization"),
      "the basemap's tile reads carry no Authorization header — the Conduit answers " +
        "/v1/map/local-source/{id} with 401 for these, and the Map view renders an empty " +
        "canvas with no error shown, because the availability preflight (which uses fetch " +
        "directly, and does send the token) still succeeds",
    ).toBe(`Bearer ${TOKEN}`);
  });

  it("points at the URL it was given, so the protocol handler resolves this source", () => {
    // `Protocol.add` keys by the source's own URL: a mismatch here means MapLibre falls back to
    // constructing its own unauthenticated `FetchSource` and the token never travels, which
    // looks identical to the bug above from the outside.
    const source = authorisedPmtilesSource(SOURCE_URL, TOKEN);
    expect(source.source.getKey()).toBe(SOURCE_URL);
  });

  it("sends no Authorization header at all when there is no token", () => {
    // Not the same as an empty one: `Authorization: Bearer undefined` would turn a working
    // anonymous read (an unauthenticated tier-3/4 source) into a 401.
    const headers = headersOf(authorisedPmtilesSource(SOURCE_URL, undefined));
    expect(headers.get("Authorization")).toBeNull();
  });
});

describe("registerAuthorisedPmtilesSource", () => {
  it("registers the authorised source against the protocol handler", () => {
    const added: { key: string; authorization: string | null }[] = [];
    const protocol = {
      add: (p: { source: { getKey(): string; customHeaders?: Headers } }) =>
        added.push({
          key: p.source.getKey(),
          authorization: p.source.customHeaders?.get("Authorization") ?? null,
        }),
    };

    registerAuthorisedPmtilesSource(
      protocol as unknown as Parameters<typeof registerAuthorisedPmtilesSource>[0],
      SOURCE_URL,
      TOKEN,
    );

    expect(added).toEqual([{ key: SOURCE_URL, authorization: `Bearer ${TOKEN}` }]);
  });
});
