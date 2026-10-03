import { describe, expect, it, vi } from "vitest";

import type { Node } from "../../../../packages/schemas/generated";
import { drawSearchResult, SEARCH_DRAW_DEPTH } from "./drawSearchResult";

const NODE = { id: "n9", type: "Person", properties: {} } as unknown as Node;

function fakeStore(seq = 7) {
  const applyDelta = vi.fn();
  return { applyDelta, store: { getState: () => ({ seq, applyDelta }) } };
}

describe("drawSearchResult", () => {
  it("is three steps, the figure the owner chose (ADR-070)", () => {
    expect(SEARCH_DRAW_DEPTH).toBe(3);
  });

  it("puts the chosen node on the canvas first, then draws three steps out from it", () => {
    const { store, applyDelta } = fakeStore();
    const order: string[] = [];
    applyDelta.mockImplementation(() => order.push("added"));
    const canvas = { expandFrom: vi.fn(() => order.push("expanded")) };
    drawSearchResult(store as never, NODE, canvas);
    expect(applyDelta).toHaveBeenCalledWith({ seq: 7, op: "add", nodes: [NODE], edges: [] });
    expect(canvas.expandFrom).toHaveBeenCalledWith("n9", 3);
    expect(order).toEqual(["added", "expanded"]);
  });

  it("still adds the node when the canvas is not on screen (the map view), and draws nothing out", () => {
    const { store, applyDelta } = fakeStore();
    drawSearchResult(store as never, NODE, null);
    expect(applyDelta).toHaveBeenCalledTimes(1);
  });
});
