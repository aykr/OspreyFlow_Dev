import { describe, expect, it } from "vitest";

import { isWorkingSetDelta } from "./deltaClient";

describe("isWorkingSetDelta", () => {
  it("accepts every step the server can send, including a replaced link (ADR-080)", () => {
    for (const op of ["add", "remove", "replace_edge", "reproject", "snapshot"]) {
      expect(isWorkingSetDelta({ op, seq: 1 })).toBe(true);
    }
  });

  it("no longer counts an update as a step: nothing produces one and it named node ids", () => {
    expect(isWorkingSetDelta({ op: "update", seq: 1 })).toBe(false);
  });

  it("no longer counts a notice as a step to apply (ADR-124); the client drops it quietly", () => {
    expect(isWorkingSetDelta({ op: "notice", seq: 1 })).toBe(false);
  });

  it("refuses a step it does not know, and one with no sequence number", () => {
    expect(isWorkingSetDelta({ op: "teleport", seq: 1 })).toBe(false);
    expect(isWorkingSetDelta({ op: "add" })).toBe(false);
    expect(isWorkingSetDelta(null)).toBe(false);
  });
});
