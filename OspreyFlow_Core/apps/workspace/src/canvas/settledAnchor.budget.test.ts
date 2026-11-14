// Timed, so it runs in the budget run, alone (`vitest.config.ts`'s `exclude` has why): in `make
// test`'s parallel run on a loaded server it read 1535 ms where it reads well under a second alone
// (14 November 2026, case-b's gates at 1231898). The limit is unchanged.
import { describe, expect, it } from "vitest";

import { settledAnchors } from "./settledAnchor";

describe("settledAnchors at the perf fixture's size", () => {
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
