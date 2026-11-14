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
});
