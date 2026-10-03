import { describe, expect, it } from "vitest";

import { arrange, MIN_NODE_GAP, type ArrangeInput } from "./layoutModes";

type N = ArrangeInput["nodes"][number];
const n = (id: string, type = "Endpoint"): N => ({ id, type, x: 0, y: 0 });
const chain = (count: number): ArrangeInput => ({
  nodes: Array.from({ length: count }, (_, i) => n(`n${String(i).padStart(3, "0")}`)),
  edges: Array.from({ length: count - 1 }, (_, i) => [
    `n${String(i).padStart(3, "0")}`,
    `n${String(i + 1).padStart(3, "0")}`,
  ]),
});
const at = (m: Map<string, { x: number; y: number }> | null, id: string) => m!.get(id)!;
const dist = (a: { x: number; y: number }, b: { x: number; y: number }) => Math.hypot(a.x - b.x, a.y - b.y);

function minGap(m: Map<string, { x: number; y: number }>): number {
  const pts = [...m.values()];
  let best = Infinity;
  for (let i = 0; i < pts.length; i++)
    for (let j = i + 1; j < pts.length; j++) best = Math.min(best, dist(pts[i]!, pts[j]!));
  return best;
}

const MODES = ["radial", "hierarchical", "circular", "group"] as const;

describe.each(MODES)("%s: what every arrangement promises", (mode) => {
  it("places every node, at a finite position", () => {
    const input = chain(20);
    const placed = arrange(mode, input)!;
    expect(placed.size).toBe(20);
    for (const node of input.nodes) {
      expect(Number.isFinite(at(placed, node.id).x)).toBe(true);
      expect(Number.isFinite(at(placed, node.id).y)).toBe(true);
    }
  });

  it("gives the same answer for the same graph", () => {
    const a = arrange(mode, chain(15))!;
    const b = arrange(mode, chain(15))!;
    expect([...a]).toEqual([...b]);
  });

  it("copes with no nodes and with one", () => {
    expect(arrange(mode, { nodes: [], edges: [] })!.size).toBe(0);
    expect(arrange(mode, { nodes: [n("only")], edges: [] })!.size).toBe(1);
  });

  it("never stacks two nodes on one spot", () => {
    const input: ArrangeInput = {
      nodes: Array.from({ length: 40 }, (_, i) => n(`k${i}`, i % 2 ? "Person" : "Endpoint")),
      edges: [],
    };
    expect(minGap(arrange(mode, input)!)).toBeGreaterThanOrEqual(MIN_NODE_GAP - 1e-6);
  });

  it("ignores an edge to a node that is not there", () => {
    const input: ArrangeInput = { nodes: [n("a"), n("b")], edges: [["a", "ghost"], ["a", "b"]] };
    expect(arrange(mode, input)!.size).toBe(2);
  });
});

describe("circular", () => {
  it("puts every node the same distance from the middle", () => {
    const input = chain(30);
    const placed = arrange("circular", input)!;
    const radii = input.nodes.map((node) => Math.hypot(at(placed, node.id).x, at(placed, node.id).y));
    expect(Math.max(...radii) - Math.min(...radii)).toBeLessThan(1e-6);
  });

  it("keeps nodes of one type next to each other round the ring", () => {
    // Ids interleave the types, so only a sort by type can keep each type together.
    const nodes = [n("1", "A"), n("2", "B"), n("3", "A"), n("4", "B"), n("5", "A")];
    const placed = arrange("circular", { nodes, edges: [] })!;
    const order = nodes
      .map((node) => ({ node, angle: Math.atan2(at(placed, node.id).y, at(placed, node.id).x) }))
      .sort((p, q) => p.angle - q.angle)
      .map((p) => p.node.type);
    const changes = order.filter((t, i) => t !== order[(i + 1) % order.length]).length;
    expect(changes).toBe(2);
  });
});

describe("radial", () => {
  const star: ArrangeInput = {
    nodes: ["hub", "a", "b", "c", "d", "a1", "a2", "far"].map((id) => n(id)),
    edges: [["hub", "a"], ["hub", "b"], ["hub", "c"], ["hub", "d"], ["a", "a1"], ["a", "a2"]],
  };

  it("puts the chosen node in the middle", () => {
    const placed = arrange("radial", star, { centre: "a" })!;
    expect(at(placed, "a")).toEqual({ x: 0, y: 0 });
  });

  it("puts each step further out on its own ring", () => {
    const placed = arrange("radial", star, { centre: "hub" })!;
    const r = (id: string) => Math.hypot(at(placed, id).x, at(placed, id).y);
    expect(r("hub")).toBe(0);
    expect(Math.abs(r("a") - r("b"))).toBeLessThan(1e-6);
    expect(Math.abs(r("a") - r("c"))).toBeLessThan(1e-6);
    expect(r("a1")).toBeGreaterThan(r("a") + 1);
    expect(Math.abs(r("a1") - r("a2"))).toBeLessThan(1e-6);
  });

  it("puts nodes that cannot be reached from the centre outside every reached ring", () => {
    const placed = arrange("radial", star, { centre: "hub" })!;
    const r = (id: string) => Math.hypot(at(placed, id).x, at(placed, id).y);
    expect(r("far")).toBeGreaterThan(Math.max(r("a1"), r("a2"), r("a"), r("b"), r("c")));
  });

  it("falls back to the most connected node when none is chosen or the choice is not on screen", () => {
    const none = arrange("radial", star)!;
    const missing = arrange("radial", star, { centre: "not-there" })!;
    expect(at(none, "hub")).toEqual({ x: 0, y: 0 });
    expect(at(missing, "hub")).toEqual({ x: 0, y: 0 });
  });

  it("makes a ring wide enough for the nodes on it", () => {
    const many: ArrangeInput = {
      nodes: [n("hub"), ...Array.from({ length: 60 }, (_, i) => n(`s${i}`))],
      edges: Array.from({ length: 60 }, (_, i) => ["hub", `s${i}`] as [string, string]),
    };
    expect(minGap(arrange("radial", many, { centre: "hub" })!)).toBeGreaterThanOrEqual(MIN_NODE_GAP - 1e-6);
  });
});

describe("hierarchical", () => {
  it("puts the target of every edge below its source", () => {
    const input: ArrangeInput = {
      nodes: ["a", "b", "c", "d"].map((id) => n(id)),
      edges: [["a", "b"], ["a", "c"], ["b", "d"], ["c", "d"]],
    };
    const placed = arrange("hierarchical", input)!;
    for (const [s, t] of input.edges) expect(at(placed, t).y).toBeGreaterThan(at(placed, s).y);
  });

  it("puts a node on the layer of its longest path", () => {
    const input: ArrangeInput = {
      nodes: ["a", "b", "c"].map((id) => n(id)),
      edges: [["a", "b"], ["b", "c"], ["a", "c"]],
    };
    const placed = arrange("hierarchical", input)!;
    expect(at(placed, "c").y).toBeGreaterThan(at(placed, "b").y);
  });

  it("copes with a cycle: every node placed, and the other edges still point down", () => {
    const input: ArrangeInput = {
      nodes: ["a", "b", "c", "d"].map((id) => n(id)),
      edges: [["a", "b"], ["b", "c"], ["c", "a"], ["c", "d"]],
    };
    const placed = arrange("hierarchical", input)!;
    expect(placed.size).toBe(4);
    expect(at(placed, "d").y).toBeGreaterThan(at(placed, "c").y);
  });

  it("orders each layer to follow the layer above, so edges cross less", () => {
    // Ids sort opposite to the parents' order: a plain id sort would cross the two edges.
    const input: ArrangeInput = {
      nodes: ["p1", "p2", "z-child-of-p1", "a-child-of-p2"].map((id) => n(id)),
      edges: [["p1", "z-child-of-p1"], ["p2", "a-child-of-p2"], ["p1", "p2x"]].slice(0, 2) as [string, string][],
    };
    const placed = arrange("hierarchical", input)!;
    const leftParent = at(placed, "p1").x < at(placed, "p2").x ? "p1" : "p2";
    const leftChild = leftParent === "p1" ? "z-child-of-p1" : "a-child-of-p2";
    const rightChild = leftParent === "p1" ? "a-child-of-p2" : "z-child-of-p1";
    expect(at(placed, leftChild).x).toBeLessThan(at(placed, rightChild).x);
  });

  it("lays out separate pieces side by side, none lost", () => {
    const input: ArrangeInput = {
      nodes: ["a", "b", "x", "y"].map((id) => n(id)),
      edges: [["a", "b"], ["x", "y"]],
    };
    expect(arrange("hierarchical", input)!.size).toBe(4);
  });

  it("handles a long chain without running out of stack", () => {
    expect(arrange("hierarchical", chain(3000))!.size).toBe(3000);
  });
});

describe("group by type", () => {
  const typed: ArrangeInput = {
    nodes: [
      ...Array.from({ length: 12 }, (_, i) => n(`e${i}`, "Endpoint")),
      ...Array.from({ length: 7 }, (_, i) => n(`p${i}`, "Person")),
      ...Array.from({ length: 3 }, (_, i) => n(`o${i}`, "Org")),
    ],
    edges: [["e0", "p0"], ["p1", "o1"]],
  };

  it("keeps each type together: every node is nearer its own type's centre than any other's", () => {
    const placed = arrange("group", typed)!;
    const centre = (type: string) => {
      const pts = typed.nodes.filter((x) => x.type === type).map((x) => at(placed, x.id));
      return { x: pts.reduce((s, p) => s + p.x, 0) / pts.length, y: pts.reduce((s, p) => s + p.y, 0) / pts.length };
    };
    const types = ["Endpoint", "Person", "Org"];
    for (const node of typed.nodes) {
      const own = dist(at(placed, node.id), centre(node.type));
      for (const other of types.filter((t) => t !== node.type))
        expect(own).toBeLessThan(dist(at(placed, node.id), centre(other)));
    }
  });

  it("leaves a clear gap between one type's group and the next", () => {
    const placed = arrange("group", typed)!;
    const within = (type: string) => typed.nodes.filter((x) => x.type === type).map((x) => at(placed, x.id));
    const gap = (a: { x: number; y: number }[], b: { x: number; y: number }[]) =>
      Math.min(...a.flatMap((p) => b.map((q) => dist(p, q))));
    expect(gap(within("Endpoint"), within("Person"))).toBeGreaterThan(MIN_NODE_GAP);
    expect(gap(within("Person"), within("Org"))).toBeGreaterThan(MIN_NODE_GAP);
    expect(gap(within("Endpoint"), within("Org"))).toBeGreaterThan(MIN_NODE_GAP);
  });
});

describe("a graph too large to arrange quickly", () => {
  it("returns null rather than freezing the page", () => {
    const input: ArrangeInput = {
      nodes: Array.from({ length: 6001 }, (_, i) => n(`m${i}`)),
      edges: [],
    };
    for (const mode of MODES) expect(arrange(mode, input)).toBeNull();
  });
});
