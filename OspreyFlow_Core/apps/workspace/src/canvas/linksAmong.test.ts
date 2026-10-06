import { afterEach, describe, expect, it, vi } from "vitest";

import { expansionLinksNotice, linksAmongNotice, showLinksAmong } from "./linksAmong";

// ADR-098 decision 1: the links among nodes already in the view.
describe("showLinksAmong", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("asks for the named nodes, or for the whole view when none is named", async () => {
    const bodies: unknown[] = [];
    vi.stubGlobal("fetch", async (url: string, init: RequestInit) => {
      expect(url).toBe("http://api.test/v1/investigations/inv-1/links-among");
      bodies.push(JSON.parse(String(init.body)));
      return new Response(JSON.stringify({ added: 2, delta: { seq: 4, op: "add", nodes: [], edges: [] } }), { status: 200 });
    });
    const one = await showLinksAmong("http://api.test", "tok", "inv-1", ["a", "b"]);
    await showLinksAmong("http://api.test", "tok", "inv-1", null);
    expect(one.added).toBe(2);
    expect(bodies).toEqual([{ node_ids: ["a", "b"] }, { node_ids: null }]);
  });

  it("says by how much past the cap, never adding some of them (rule 2)", async () => {
    vi.stubGlobal(
      "fetch",
      async () =>
        new Response(JSON.stringify({ error: "limit_exceeded", cap_kind: "edges", cap: 250000, would_be: 251000 }), {
          status: 409,
        }),
    );
    await expect(showLinksAmong("http://api.test", "tok", "inv-1", null)).rejects.toThrow(
      "Too many for the canvas: 251,000 edges against a limit of 250,000. Select fewer nodes and try again.",
    );
  });
});

describe("the notices", () => {
  it("says how many links were added, or that there were none to add", () => {
    expect(linksAmongNotice(0)).toBe("No more links among these.");
    expect(linksAmongNotice(1)).toBe("1 link added among these.");
    expect(linksAmongNotice(1234)).toBe("1,234 links added among these.");
  });

  it("says when an expansion's links among the view were left out because it was full", () => {
    expect(expansionLinksNotice("view_full")).toBe(
      "The links among these and the rest of the view were not added: there would be too many. Select fewer and use Show links among these.",
    );
    expect(expansionLinksNotice("added")).toBeNull();
    expect(expansionLinksNotice("not_asked")).toBeNull();
    expect(expansionLinksNotice(undefined)).toBeNull();
  });
});
