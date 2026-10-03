import { describe, expect, it } from "vitest";
import {
  FORCE_LAYOUT_MAX_NODES,
  IDEAL_EDGE_LENGTH,
  settleLayout,
  type LayoutNode,
} from "./forceLayout";

/**
 * A network drawn from a seeded scatter reads as a hairball. These pin what the layout promises:
 * nodes spread apart, linked nodes sit closer than unlinked ones, the result is repeatable, a
 * pinned node does not move, and a graph too big to settle quickly is left alone, said so.
 */

function dist(
  a: { x: number; y: number },
  b: { x: number; y: number },
): number {
  return Math.hypot(a.x - b.x, a.y - b.y);
}

function chain(
  n: number,
  at = { x: 0, y: 0 },
): { nodes: LayoutNode[]; edges: [string, string][] } {
  const nodes = Array.from({ length: n }, (_, i) => ({
    id: `n${i}`,
    x: at.x + (i % 3),
    y: at.y + (i % 2),
  }));
  const edges = nodes
    .slice(1)
    .map((node, i): [string, string] => [nodes[i]!.id, node.id]);
  return { nodes, edges };
}

describe("settleLayout", () => {
  it("pushes nodes that start on top of each other apart", () => {
    const { nodes, edges } = chain(30);
    const out = settleLayout(nodes, edges)!;
    let nearest = Infinity;
    for (let i = 0; i < nodes.length; i++)
      for (let j = i + 1; j < nodes.length; j++)
        nearest = Math.min(
          nearest,
          dist(out.get(nodes[i]!.id)!, out.get(nodes[j]!.id)!),
        );
    expect(nearest).toBeGreaterThan(IDEAL_EDGE_LENGTH * 0.3);
  });

  it("keeps linked nodes closer together than unlinked ones, on average", () => {
    const { nodes, edges } = chain(24);
    const out = settleLayout(nodes, edges)!;
    const linked = edges.map(([a, b]) => dist(out.get(a)!, out.get(b)!));
    const all: number[] = [];
    for (let i = 0; i < nodes.length; i++)
      for (let j = i + 1; j < nodes.length; j++)
        all.push(dist(out.get(nodes[i]!.id)!, out.get(nodes[j]!.id)!));
    const mean = (xs: number[]) => xs.reduce((s, x) => s + x, 0) / xs.length;
    expect(mean(linked)).toBeLessThan(mean(all));
  });

  it("gives the same answer for the same input", () => {
    const { nodes, edges } = chain(20);
    expect([...settleLayout(nodes, edges)!]).toEqual([
      ...settleLayout(nodes, edges)!,
    ]);
  });

  it("does not move a pinned node", () => {
    const { nodes, edges } = chain(12);
    nodes[3] = { ...nodes[3]!, x: 500, y: -250, pinned: true };
    const out = settleLayout(nodes, edges)!;
    expect(out.get("n3")).toEqual({ x: 500, y: -250 });
  });

  it("keeps separate groups from flying off to infinity", () => {
    const a = chain(8, { x: 0, y: 0 });
    const b = chain(8, { x: 5, y: 5 });
    const nodes = [
      ...a.nodes,
      ...b.nodes.map((n) => ({ ...n, id: `m${n.id}` })),
    ];
    const edges = [
      ...a.edges,
      ...b.edges.map(([s, t]): [string, string] => [`m${s}`, `m${t}`]),
    ];
    const out = settleLayout(nodes, edges)!;
    for (const p of out.values())
      expect(Math.hypot(p.x, p.y)).toBeLessThan(IDEAL_EDGE_LENGTH * 40);
  });

  it("pulls two linked nodes to about one ideal edge length apart", () => {
    const out = settleLayout(
      [
        { id: "a", x: 0, y: 0 },
        { id: "b", x: 3, y: 1 },
      ],
      [["a", "b"]],
    )!;
    const gap = dist(out.get("a")!, out.get("b")!);
    expect(gap).toBeGreaterThan(IDEAL_EDGE_LENGTH * 0.7);
    expect(gap).toBeLessThan(IDEAL_EDGE_LENGTH * 1.3);
  });

  it("settles a pinned node's neighbours around where it is pinned, not where it would drift", () => {
    const out = settleLayout(
      [
        { id: "p", x: 500, y: -250, pinned: true },
        { id: "q", x: 0, y: 0 },
      ],
      [["p", "q"]],
    )!;
    expect(dist(out.get("p")!, out.get("q")!)).toBeLessThan(
      IDEAL_EDGE_LENGTH * 1.3,
    );
  });

  it("holds two unlinked nodes within a screenful, not drifting ever further apart", () => {
    const out = settleLayout(
      [
        { id: "a", x: 0, y: 0 },
        { id: "b", x: 3, y: 1 },
      ],
      [],
    )!;
    expect(dist(out.get("a")!, out.get("b")!)).toBeLessThan(
      IDEAL_EDGE_LENGTH * 10,
    );
  });

  it("ignores an edge to a node that is not in the list", () => {
    const { nodes } = chain(3);
    expect(() => settleLayout(nodes, [["n0", "ghost"]])).not.toThrow();
  });

  it("returns null for a graph too large to settle quickly, rather than freezing the page", () => {
    const nodes = Array.from(
      { length: FORCE_LAYOUT_MAX_NODES + 1 },
      (_, i) => ({ id: `n${i}`, x: i, y: 0 }),
    );
    expect(settleLayout(nodes, [])).toBeNull();
  });
});
