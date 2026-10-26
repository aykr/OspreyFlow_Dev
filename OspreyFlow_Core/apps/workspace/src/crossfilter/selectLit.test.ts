import { describe, expect, it, vi } from "vitest";

import type { FirstSeenResult } from "../../../../packages/schemas/generated";
import { readLit } from "./selectLit";

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
