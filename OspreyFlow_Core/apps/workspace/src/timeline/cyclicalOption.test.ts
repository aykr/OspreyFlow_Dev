// ADR-115 Amendment 2: the weekly view's colour key sits beside the hour axis, never over it. Found in
// the signed-in sitting, 14 October 2026: centred along the bottom, it covered the 10–12 o'clock labels.
import { describe, expect, it } from "vitest";

import { KEY_WIDTH, cyclicalOption } from "./cyclicalOption";

describe("the weekly view's colour key", () => {
  const option = cyclicalOption({ data: [[9, 1, 4]], max: 4, colours: ["#eee", "#055"], text: "#555" });

  it("stands upright at the right-hand side, not along the bottom", () => {
    expect(option.visualMap.orient).toBe("vertical");
    expect(option.visualMap.right).toBe(0);
    expect(option.visualMap).not.toHaveProperty("bottom");
  });

  it("has room of its own: the grid stops short of it", () => {
    expect(option.grid.right).toBeGreaterThanOrEqual(KEY_WIDTH);
  });
});
