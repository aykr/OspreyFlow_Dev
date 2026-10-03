import { describe, expect, it } from "vitest";

import { isWorkingSetDelta } from "./deltaClient";

describe("isWorkingSetDelta", () => {
  it("accepts every step the server can send, including a replaced link (ADR-080)", () => {
    for (const op of ["add", "update", "remove", "replace_edge", "reproject", "notice", "snapshot"]) {
      expect(isWorkingSetDelta({ op, seq: 1 })).toBe(true);
    }
  });

  it("refuses a step it does not know, and one with no sequence number", () => {
    expect(isWorkingSetDelta({ op: "teleport", seq: 1 })).toBe(false);
    expect(isWorkingSetDelta({ op: "add" })).toBe(false);
    expect(isWorkingSetDelta(null)).toBe(false);
  });
});
