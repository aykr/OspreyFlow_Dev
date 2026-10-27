import { describe, expect, it, vi } from "vitest";

import type { FirstSeenResult } from "../../../../packages/schemas/generated";
import { LIT_ANSWER_LATE, readLit, selectionChangedSince } from "./selectLit";

// ADR-128 decision 2 (B3): Select what is lit asks the server which links have an event in the
// window, for the window alone: a selection already on the canvas must not narrow what is lit.

const window = { validFrom: "2026-01-05T00:00:00Z", validTo: "2026-05-01T00:00:00Z" };
const links = [
  { id: "ab", source: "a", target: "b" },
  { id: "bc", source: "b", target: "c" },
];

describe("readLit", () => {
  it("asks for the window alone, in the case's own scope, with no node restriction", async () => {
    const ask = vi.fn(
      async (): Promise<FirstSeenResult> => ({ nodes: {}, edges: { ab: "2026-02-01T00:00:00Z" } }),
    );
    const read = await readLit(ask, "inv-1", window, links);
    expect(ask).toHaveBeenCalledTimes(1);
    expect(ask).toHaveBeenCalledWith({
      investigation_scope: "inv-1",
      window: { valid_from: window.validFrom, valid_to: window.validTo },
      node_ids: [],
      edge_types: [],
    });
    expect(read).toEqual({ ok: true, lit: { nodeIds: ["a", "b"], edgeIds: ["ab"] }, window });
  });

  it("is a result, not an error, when nothing is lit", async () => {
    const read = await readLit(async () => ({ nodes: {}, edges: {} }), "inv-1", window, links);
    expect(read).toEqual({ ok: true, lit: { nodeIds: [], edgeIds: [] }, window });
  });

  it("reports a failed read instead of throwing, and selects nothing", async () => {
    const read = await readLit(
      async () => {
        throw new Error("offline");
      },
      "inv-1",
      window,
      links,
    );
    expect(read.ok).toBe(false);
    if (!read.ok) expect(read.message).toContain("offline");
  });
});

// A lit answer that arrives after the analyst changed the selection must not replace it, and an
// undo must go back to what the answer replaced. The shapes are the ones the canvas holds: the
// selection at the press is an array (Array.from of its Set), the selection now is the live Set.
describe("selectionChangedSince", () => {
  it("is false when the live selection is exactly what it was at the press, in any order", () => {
    expect(selectionChangedSince(["a", "b"], new Set(["b", "a"]))).toBe(false);
    expect(selectionChangedSince([], new Set<string>())).toBe(false);
  });

  it("is true when a node was added, removed or swapped while the read was in flight", () => {
    expect(selectionChangedSince(["a"], new Set(["a", "b"]))).toBe(true);
    expect(selectionChangedSince(["a", "b"], new Set(["a"]))).toBe(true);
    expect(selectionChangedSince(["a"], new Set(["c"]))).toBe(true);
    expect(selectionChangedSince([], new Set(["c"]))).toBe(true);
  });

  it("has a status message that says the answer was dropped and the selection kept", () => {
    expect(LIT_ANSWER_LATE).toMatch(/selection changed/i);
    expect(LIT_ANSWER_LATE).toMatch(/unchanged|kept/i);
  });
});
