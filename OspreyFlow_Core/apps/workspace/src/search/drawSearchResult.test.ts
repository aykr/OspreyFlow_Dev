import { describe, expect, it, vi } from "vitest";

import type { Node } from "../../../../packages/schemas/generated";
import { drawSearchResult, SEARCH_DRAW_DEPTH } from "./drawSearchResult";

const NODE = { id: "n9", type: "Person", properties: {} } as unknown as Node;

describe("drawSearchResult", () => {
  it("is three steps, the figure the owner chose (ADR-070)", () => {
    expect(SEARCH_DRAW_DEPTH).toBe(3);
  });

  // Build order step 18c (the 3 November rehearsal's D5): the chosen node was put on the canvas by a
  // local add alone. When the three-step draw was too large and was cancelled, the node stayed on
  // screen but was never in the case's working set, so "Show links among these" could not see it and
  // said "No routes within 6 degrees" for a pair Find connections joins at 2. It goes to the working
  // set through `/seed` first, as Explore's adds do, and the draw follows once it is there.
  it("puts the chosen node in the case's working set first, then draws three steps out from it", async () => {
    const order: string[] = [];
    const seed = vi.fn(async () => {
      order.push("seeded");
      return true;
    });
    const canvas = { expandFrom: vi.fn(() => order.push("expanded")) };
    await drawSearchResult(seed, NODE, canvas);
    expect(seed).toHaveBeenCalledWith([NODE]);
    expect(canvas.expandFrom).toHaveBeenCalledWith("n9", 3);
    expect(order).toEqual(["seeded", "expanded"]);
  });

  it("draws nothing out when the node could not be put in the working set", async () => {
    const canvas = { expandFrom: vi.fn() };
    await drawSearchResult(async () => false, NODE, canvas);
    expect(canvas.expandFrom).not.toHaveBeenCalled();
  });

  it("still puts the node in the working set when the canvas is not on screen (the map view)", async () => {
    const seed = vi.fn(async () => true);
    await drawSearchResult(seed, NODE, null);
    expect(seed).toHaveBeenCalledTimes(1);
  });
});
