// Timed, so it runs in the budget run, alone (`vitest.config.ts`'s `exclude` has why). The limit is
// unchanged.
import { describe, expect, it } from "vitest";

import { communityGroupOf } from "./communityLinks";
import { packBubbles } from "./layoutModes";

describe("packBubbles at the size of a large working set (ADR-119)", () => {
  it("places 50,000 nodes in 40 communities, each node once, quickly", () => {
    const nodes = Array.from({ length: 50_000 }, (_, i) => ({ id: `n${i}`, x: 0, y: 0, type: "Person" }));
    const assignment = new Map(nodes.map((node, i) => [node.id, i % 40]));
    const started = performance.now();
    const placed = packBubbles({ nodes, edges: [] }, communityGroupOf(assignment));
    expect(placed.size).toBe(50_000);
    expect(performance.now() - started).toBeLessThan(2000);
  });
});
