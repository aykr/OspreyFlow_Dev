import { describe, expect, it } from "vitest";

import { settledAnchors } from "./settledAnchor";

describe("settledAnchors: where an arriving node starts", () => {
  it("is the first settled neighbour in link order, on either end of the link", () => {
    const edges: [string, string][] = [
      ["new", "loose"],
      ["old-b", "new"],
      ["new", "old-a"],
    ];
    const anchors = settledAnchors(["new", "loose"], edges, new Set(["old-a", "old-b"]));
    expect(anchors.get("new")).toBe("old-b");
    expect(anchors.has("loose")).toBe(false);
  });

  it("gives a settled node no anchor of its own", () => {
    const anchors = settledAnchors(["old"], [["old", "older"]], new Set(["old", "older"]));
    expect(anchors.size).toBe(0);
  });

  it("is linear in the links: the perf fixture's 50,000 nodes and 250,000 links take well under a second", () => {
    // Found by the perf gate (`perf/perf.spec.ts`): a scan of every link for every node held the
    // first layout of the fixture for over two minutes.
    const n = 50_000;
    const nodes = Array.from({ length: n }, (_, i) => `n${i}`);
    const edges: [string, string][] = Array.from({ length: 250_000 }, (_, i) => [
      `n${i % n}`,
      `n${(i * 7919 + 1) % n}`,
    ]);
    const settled = new Set(nodes.slice(0, 10));
    const start = performance.now();
    settledAnchors(nodes, edges, settled);
    expect(performance.now() - start).toBeLessThan(1000);
  });
});
