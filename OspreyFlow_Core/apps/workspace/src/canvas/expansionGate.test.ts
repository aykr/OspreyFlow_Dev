import { describe, expect, it } from "vitest";
import {
  EXPANSION_CONFIRM_ABOVE,
  gateExpansion,
  narrowingOptions,
} from "./expansionGate";

/**
 * Seen 3 October 2026: a double-click on a busy Enron address added all 1,090 of its neighbours at
 * once and left an unreadable disc. An expansion that would add more than `EXPANSION_CONFIRM_ABOVE`
 * nodes asks first, and so does one whose size could not be counted.
 */

describe("gateExpansion", () => {
  it("lets an expansion up to the limit go ahead", () => {
    expect(gateExpansion(0)).toEqual({ kind: "proceed" });
    expect(gateExpansion(EXPANSION_CONFIRM_ABOVE)).toEqual({ kind: "proceed" });
  });

  it("asks first above the limit, and says how many", () => {
    expect(gateExpansion(EXPANSION_CONFIRM_ABOVE + 1)).toEqual({
      kind: "ask",
      wouldAdd: EXPANSION_CONFIRM_ABOVE + 1,
    });
  });

  it("asks first when the size could not be counted, rather than guessing it is small", () => {
    expect(gateExpansion("unavailable")).toEqual({
      kind: "ask",
      wouldAdd: "unavailable",
    });
  });
});

describe("narrowingOptions", () => {
  it("lists relationship types largest first and leaves out those that add nothing", () => {
    expect(
      narrowingOptions({
        MENTIONED_IN: 12,
        COMMUNICATED_WITH: 1090,
        SAME_AS: 0,
      }),
    ).toEqual([
      { edgeType: "COMMUNICATED_WITH", wouldAdd: 1090 },
      { edgeType: "MENTIONED_IN", wouldAdd: 12 },
    ]);
  });

  it("keeps a type whose count failed, last, so it can still be tried", () => {
    expect(narrowingOptions({ A: "unavailable", B: 3 })).toEqual([
      { edgeType: "B", wouldAdd: 3 },
      { edgeType: "A", wouldAdd: "unavailable" },
    ]);
  });
});
