// The bearer token on MapLibre's own reads of the Conduit (a site's aerial image), and on nothing
// else. Found 8 October 2026: the deployed image's address is `""` (this origin, through nginx), and
// `MapView` took an empty address for no Conduit, so a site image went unauthorised and failed.
// Fixing that by matching `url.startsWith(apiBaseUrl)` would match every URL with `""`, a tile
// server's included, and send it the analyst's token: the second case below is the one that stops it.
import { describe, expect, it } from "vitest";

import { conduitRequest } from "./conduitRequest";

const ORIGIN = "http://localhost:8080";
const TOKEN = "eyJhbGciOiJSUzI1NiJ9.test-token";
const IMAGE = "/v1/investigations/case-1/sites/site-1/image";

describe("conduitRequest", () => {
  it("authorises the Conduit's own read at the deployed same-origin address", () => {
    expect(conduitRequest(`${ORIGIN}${IMAGE}`, "", TOKEN, ORIGIN)).toEqual({
      url: `${ORIGIN}${IMAGE}`,
      headers: { Authorization: `Bearer ${TOKEN}` },
    });
  });

  it("never sends the token to another host, whatever the address", () => {
    for (const base of ["", "http://localhost:8000"]) {
      expect(conduitRequest("https://tiles.example.org/1/2/3.png", base, TOKEN, ORIGIN)).toBeUndefined();
    }
  });

  it("never sends it to this origin outside the Conduit's own paths", () => {
    expect(conduitRequest(`${ORIGIN}/fonts/a.pbf`, "", TOKEN, ORIGIN)).toBeUndefined();
  });

  it("authorises an explicit address's reads, and only that address's", () => {
    const base = "http://localhost:8000";
    expect(conduitRequest(`${base}${IMAGE}`, base, TOKEN, ORIGIN)?.headers).toEqual({
      Authorization: `Bearer ${TOKEN}`,
    });
    expect(conduitRequest(`${ORIGIN}${IMAGE}`, base, TOKEN, ORIGIN)).toBeUndefined();
  });

  it("adds no header without a token", () => {
    expect(conduitRequest(`${ORIGIN}${IMAGE}`, "", "", ORIGIN)).toBeUndefined();
  });
});
