import { describe, expect, it } from "vitest";

import { PlaceSearchFailed, searchPlaces } from "./places";

function answering(status: number, body: unknown, asked: Request[] = []): typeof fetch {
  return (async (input: RequestInfo | URL, init?: RequestInit) => {
    asked.push(new Request(String(input), init));
    return new Response(JSON.stringify(body), { status });
  }) as typeof fetch;
}

describe("searchPlaces", () => {
  it("asks the case's place route alone, with the token, and returns its answer", async () => {
    const asked: Request[] = [];
    const answer = { places: [{ id: "p1", name: "Cranford", lon: -0.459, lat: 51.488 }], more: false };
    const result = await searchPlaces("http://conduit", "t0k", "case/1", "cran", answering(200, answer, asked));
    expect(result).toEqual(answer);
    expect(asked).toHaveLength(1);
    expect(asked[0]!.url).toBe("http://conduit/v1/investigations/case%2F1/map/places");
    expect(asked[0]!.method).toBe("POST");
    expect(asked[0]!.headers.get("Authorization")).toBe("Bearer t0k");
    expect(await asked[0]!.json()).toEqual({ query: "cran" });
  });

  it("says a refusal and a failure in its own words, never the Conduit's", async () => {
    await expect(searchPlaces("http://conduit", "t", "c", "cran", answering(403, { detail: "internal words" })))
      .rejects.toThrow(new PlaceSearchFailed("You may not search this case's places."));
    await expect(searchPlaces("http://conduit", "t", "c", "cran", answering(500, { detail: "internal words" })))
      .rejects.toThrow("The place search failed (HTTP 500). Try again.");
    const unreachable = (async () => {
      throw new TypeError("network down at 10.0.0.1");
    }) as typeof fetch;
    await expect(searchPlaces("http://conduit", "t", "c", "cran", unreachable)).rejects.toThrow(
      "The place search could not reach the Conduit. Try again.",
    );
  });
});
