// ADR-100: the Explore panel's two reads, under the case. The figures are the Conduit's (each the
// analyst's own, computed in the store); these prove the client asks the case's routes with what
// it was given and says a refusal in words.
import { afterEach, describe, expect, it, vi } from "vitest";

import { loadMostConnected, loadTypeCounts } from "./exploreApi";

afterEach(() => vi.unstubAllGlobals());

function serve(status: number, body: unknown) {
  const calls: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      calls.push(url);
      expect((init?.headers as Record<string, string>).Authorization).toBe("Bearer t");
      return new Response(JSON.stringify(body), { status });
    }),
  );
  return calls;
}

describe("exploreApi", () => {
  it("reads the case's counts", async () => {
    const calls = serve(200, { nodes: { Person: 3 }, edges: {} });
    expect(await loadTypeCounts("http://api", "t", "case/1")).toEqual({ nodes: { Person: 3 }, edges: {} });
    expect(calls).toEqual(["http://api/v1/investigations/case%2F1/explore/counts"]);
  });

  it("asks for one page of the ranking, of one type when named", async () => {
    const calls = serve(200, { nodes: [], total: 0, offset: 10 });
    await loadMostConnected("http://api", "t", "c1", { entityType: "Person", limit: 5, offset: 10 });
    await loadMostConnected("http://api", "t", "c1", {});
    expect(calls).toEqual([
      "http://api/v1/investigations/c1/explore/most-connected?limit=5&offset=10&entity_type=Person",
      "http://api/v1/investigations/c1/explore/most-connected?limit=10&offset=0",
    ]);
  });

  it("says a refusal in words, never a bare status", async () => {
    serve(403, { detail: "insufficient access" });
    await expect(loadTypeCounts("http://api", "t", "c1")).rejects.toThrow(
      "What this case holds could not be read (403).",
    );
    serve(500, {});
    await expect(loadMostConnected("http://api", "t", "c1", {})).rejects.toThrow(
      "The most connected could not be read (500).",
    );
  });
});
