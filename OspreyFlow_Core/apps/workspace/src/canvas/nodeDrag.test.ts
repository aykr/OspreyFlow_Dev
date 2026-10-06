import { describe, expect, it } from "vitest";

import { dragTargets, keepPinned, nudgeFor, NUDGE_PX } from "./nodeDrag";

// Owner, 6 October 2026: "When I select a node I need the ability to move it around, it seems fixed".

describe("dragTargets", () => {
  it("moves every dragged node by how far the pointer has moved, keeping their shape", () => {
    const start = new Map([
      ["a", { x: 1, y: 1 }],
      ["b", { x: 3, y: 2 }],
    ]);
    const moved = dragTargets(start, { x: 10, y: 10 }, { x: 12, y: 7 });
    expect(Object.fromEntries(moved)).toEqual({ a: { x: 3, y: -2 }, b: { x: 5, y: -1 } });
  });
});

describe("nudgeFor", () => {
  it("is a small screen step for Shift with an arrow key, larger with Alt too, and nothing otherwise", () => {
    expect(nudgeFor("ArrowRight", false)).toEqual({ dx: NUDGE_PX, dy: 0 });
    expect(nudgeFor("ArrowUp", false)).toEqual({ dx: 0, dy: -NUDGE_PX });
    expect(nudgeFor("ArrowLeft", true)).toEqual({ dx: -NUDGE_PX * 4, dy: 0 });
    expect(nudgeFor("Enter", false)).toBeNull();
  });
});

describe("keepPinned", () => {
  it("leaves a node the analyst placed where they put it when a layout runs for added nodes", () => {
    const settled = new Map([
      ["placed", { x: 0, y: 0 }],
      ["new", { x: 5, y: 5 }],
    ]);
    const kept = keepPinned(settled, new Set(["placed"]), (id) => (id === "placed" ? { x: 40, y: 2 } : { x: 9, y: 9 }));
    expect(kept.get("placed")).toEqual({ x: 40, y: 2 });
    expect(kept.get("new")).toEqual({ x: 5, y: 5 });
  });
});
