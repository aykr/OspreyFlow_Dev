import { describe, expect, it } from "vitest";

import { judgementCountsByNode } from "./judgementCounts";

const j = (id: string, supporting: string[], contradicting: string[] = []) =>
  ({ id, supporting, contradicting }) as { id: string; supporting: string[]; contradicting: string[] };

describe("judgementCountsByNode", () => {
  it("counts each judgement once for every node it rests on, for or against", () => {
    const counts = judgementCountsByNode([
      j("j1", ["n1", "n2"], ["n3"]),
      j("j2", ["n1"]),
    ]);
    expect(counts.get("n1")).toBe(2);
    expect(counts.get("n2")).toBe(1);
    expect(counts.get("n3")).toBe(1);
  });

  it("counts a judgement once for a node it both supports and contradicts", () => {
    expect(judgementCountsByNode([j("j1", ["n1", "n1"], ["n1"])]).get("n1")).toBe(1);
  });

  it("has no entry for a node with no judgement, and none at all for no judgements", () => {
    expect(judgementCountsByNode([j("j1", ["n1"])]).has("n9")).toBe(false);
    expect(judgementCountsByNode([]).size).toBe(0);
  });

  it("copes with a judgement whose lists are missing", () => {
    expect(judgementCountsByNode([{ id: "j1" } as never]).size).toBe(0);
  });
});
