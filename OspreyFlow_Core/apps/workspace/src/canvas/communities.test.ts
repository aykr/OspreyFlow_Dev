import { describe, expect, it } from "vitest";

import {
  boxAt,
  collapseView,
  communityBoxes,
  communityOf,
  findCommunities,
  groupLabel,
  reconcileCollapsed,
  type Community,
} from "./communities";

type Edge = readonly [string, string];

/** A clique of `size` nodes named `<prefix>0` … */
function clique(prefix: string, size: number): { nodes: string[]; edges: Edge[] } {
  const nodes = Array.from({ length: size }, (_, i) => `${prefix}${i}`);
  const edges: Edge[] = [];
  for (let i = 0; i < size; i++) for (let j = i + 1; j < size; j++) edges.push([nodes[i]!, nodes[j]!]);
  return { nodes, edges };
}

function twoGroups() {
  const a = clique("a", 5);
  const b = clique("b", 5);
  return {
    nodes: [...a.nodes, ...b.nodes],
    edges: [...a.edges, ...b.edges, ["a0", "b0"] as Edge],
  };
}

describe("findCommunities", () => {
  it("separates two dense groups joined by a single link", () => {
    const { nodes, edges } = twoGroups();
    const found = findCommunities(nodes, edges);
    expect(found).toHaveLength(2);
    const sets = found.map((c) => [...c.members].sort().join(","));
    expect(sets).toContain("a0,a1,a2,a3,a4");
    expect(sets).toContain("b0,b1,b2,b3,b4");
  });

  it("names a community after its smallest member, so the name survives a re-run", () => {
    const { nodes, edges } = twoGroups();
    const ids = findCommunities(nodes, edges).map((c) => c.id).sort();
    expect(ids).toEqual(["c:a0", "c:b0"]);
  });

  it("gives the same answer every time for the same graph", () => {
    const { nodes, edges } = twoGroups();
    const again = findCommunities(nodes, edges);
    expect(JSON.stringify(again)).toBe(JSON.stringify(findCommunities(nodes, edges)));
  });

  it("does not report a node with no neighbours as a community of one", () => {
    const { nodes, edges } = twoGroups();
    const found = findCommunities([...nodes, "loner"], edges);
    expect(found.flatMap((c) => c.members)).not.toContain("loner");
  });

  it("lists the largest community first", () => {
    const a = clique("a", 6);
    const b = clique("b", 3);
    const found = findCommunities([...a.nodes, ...b.nodes], [...a.edges, ...b.edges]);
    expect(found.map((c) => c.members.length)).toEqual([6, 3]);
  });

  it("ignores links to nodes that are not on screen, links to self, and repeated links", () => {
    const { nodes, edges } = twoGroups();
    const noisy: Edge[] = [...edges, ["a1", "ghost"], ["a2", "a2"], ["a1", "a2"], ["a2", "a1"]];
    const found = findCommunities(nodes, noisy);
    expect(found).toHaveLength(2);
    expect(found.flatMap((c) => c.members)).not.toContain("ghost");
  });

  it("returns nothing for an empty view or one with no links", () => {
    expect(findCommunities([], [])).toEqual([]);
    expect(findCommunities(["a", "b", "c"], [])).toEqual([]);
  });

  it("puts each node in at most one community", () => {
    const { nodes, edges } = twoGroups();
    const members = findCommunities(nodes, edges).flatMap((c) => c.members);
    expect(new Set(members).size).toBe(members.length);
  });
});

describe("communityOf", () => {
  const communities: Community[] = [{ id: "c:a0", members: ["a0", "a1"] }];
  it("finds the community a node is in, and nothing for a node in none", () => {
    expect(communityOf(communities, "a1")?.id).toBe("c:a0");
    expect(communityOf(communities, "z")).toBeNull();
  });
});

describe("communityBoxes and boxAt", () => {
  const communities: Community[] = [
    { id: "c:a", members: ["a", "b", "c"] },
    { id: "c:d", members: ["d", "e"] },
  ];
  const positions = new Map([
    ["a", { x: 0, y: 0 }],
    ["b", { x: 10, y: 0 }],
    ["c", { x: 10, y: 20 }],
    ["d", { x: 100, y: 100 }],
    ["e", { x: 110, y: 100 }],
  ]);

  it("draws a box round the members, with the padding on every side", () => {
    const [first] = communityBoxes(communities, positions, 5);
    expect(first).toMatchObject({ id: "c:a", count: 3, x0: -5, y0: -5, x1: 15, y1: 25 });
  });

  it("skips members that have no position and a community left with fewer than two", () => {
    const partial = new Map([["a", { x: 0, y: 0 }], ["d", { x: 1, y: 1 }], ["e", { x: 2, y: 2 }]]);
    const boxes = communityBoxes(communities, partial, 0);
    expect(boxes.map((b) => b.id)).toEqual(["c:d"]);
  });

  it("finds the box under a point, and the smaller one when two overlap", () => {
    const big = { id: "big", count: 4, x0: 0, y0: 0, x1: 100, y1: 100 };
    const small = { id: "small", count: 2, x0: 10, y0: 10, x1: 30, y1: 30 };
    expect(boxAt([big, small], 20, 20)?.id).toBe("small");
    expect(boxAt([big, small], 80, 80)?.id).toBe("big");
    expect(boxAt([big, small], 200, 200)).toBeNull();
  });

  it("counts a point on the edge of a box as inside it", () => {
    const box = { id: "b", count: 2, x0: 0, y0: 0, x1: 10, y1: 10 };
    expect(boxAt([box], 10, 10)?.id).toBe("b");
  });
});

describe("collapseView", () => {
  const communities: Community[] = [
    { id: "c:a", members: ["a", "b", "c"] },
    { id: "c:d", members: ["d", "e"] },
  ];
  const positions = new Map([
    ["a", { x: 0, y: 0 }],
    ["b", { x: 30, y: 0 }],
    ["c", { x: 0, y: 30 }],
    ["d", { x: 100, y: 100 }],
    ["e", { x: 110, y: 100 }],
  ]);
  const degree = (id: string) => ({ a: 1, b: 5, c: 2, d: 3, e: 3 })[id] ?? 0;
  const type = (id: string) => (id === "c" ? "Account" : "Person");
  const view = (collapsed: string[]) =>
    collapseView(communities, new Set(collapsed), positions, degree, type);

  it("changes nothing when nothing is collapsed", () => {
    const v = view([]);
    expect(v.groups.size).toBe(0);
    expect(v.hidden.size).toBe(0);
    expect(v.groupedNodeCount).toBe(0);
  });

  it("stands the most connected member in for the group, at the members' centre", () => {
    const v = view(["c:a"]);
    expect([...v.groups.keys()]).toEqual(["b"]);
    expect(v.groups.get("b")).toMatchObject({ communityId: "c:a", count: 3, x: 10, y: 10 });
  });

  it("names a group by its own label when it has one, and by its types when it has none", () => {
    const named: Community[] = [
      { id: "s:d|e", members: ["d", "e"], label: "Same entity: 2 nodes" },
      { id: "c:a", members: ["a", "b", "c"] },
    ];
    const v = collapseView(named, new Set(["s:d|e", "c:a"]), positions, degree, type);
    expect(v.groups.get("d")?.label).toBe("Same entity: 2 nodes");
    expect(v.groups.get("b")?.label).toBe("Group of 3 nodes: Person 2, Account 1");
  });

  it("folds a group once: a later group sharing a member with a folded one is left open", () => {
    const overlapping: Community[] = [
      { id: "s:a|b", members: ["a", "b"], label: "Same entity: 2 nodes" },
      { id: "c:a", members: ["a", "b", "c"] },
    ];
    const v = collapseView(
      overlapping,
      new Set(["s:a|b", "c:a"]),
      positions,
      degree,
      type,
    );
    expect([...v.groups.values()].map((g) => g.communityId)).toEqual(["s:a|b"]);
    expect(v.hidden.has("c")).toBe(false);
    expect(v.groupedNodeCount).toBe(2);
  });

  it("breaks a tie in connectedness by the smaller id, so the choice is stable", () => {
    expect([...view(["c:d"]).groups.keys()]).toEqual(["d"]);
  });

  it("hides the other members and leaves untouched communities alone", () => {
    const v = view(["c:a"]);
    expect([...v.hidden].sort()).toEqual(["a", "c"]);
    expect(v.hidden.has("d")).toBe(false);
    expect(v.groups.has("d")).toBe(false);
  });

  it("counts every node inside a collapsed group, the stand-in included", () => {
    expect(view(["c:a"]).groupedNodeCount).toBe(3);
    expect(view(["c:a", "c:d"]).groupedNodeCount).toBe(5);
  });

  it("hides a link between two members of the same collapsed group, and no other", () => {
    const v = view(["c:a"]);
    expect(v.hidesLink("a", "b")).toBe(true);
    expect(v.hidesLink("b", "c")).toBe(true);
    expect(v.hidesLink("a", "d")).toBe(false);
    expect(v.hidesLink("d", "e")).toBe(false);
  });

  it("draws each hidden member at its group's centre, so a link from outside still reaches the group", () => {
    const v = view(["c:a"]);
    expect(v.anchorOf("a")).toEqual({ x: 10, y: 10 });
    expect(v.anchorOf("c")).toEqual({ x: 10, y: 10 });
  });

  it("has no anchor for the stand-in, for a member of a group that is not folded, or for a stranger", () => {
    const v = view(["c:a"]);
    expect(v.anchorOf("b")).toBeNull();
    expect(v.anchorOf("d")).toBeNull();
    expect(v.anchorOf("nobody")).toBeNull();
  });

  it("ignores a collapsed id that names no community", () => {
    const v = view(["c:gone"]);
    expect(v.groups.size).toBe(0);
  });

  it("labels the group with its size and what is in it", () => {
    const v = view(["c:a"]);
    expect(v.groups.get("b")!.label).toBe("Group of 3 nodes: Person 2, Account 1");
  });
});

describe("groupLabel", () => {
  it("lists the commonest type first and says nodes in the plural", () => {
    expect(groupLabel(["Person", "Account", "Account", "Account"])).toBe(
      "Group of 4 nodes: Account 3, Person 1",
    );
  });
  it("keeps to three types and counts the rest together", () => {
    expect(groupLabel(["A", "A", "B", "B", "C", "D", "E"])).toBe(
      "Group of 7 nodes: A 2, B 2, C 1, 2 other",
    );
  });
});

describe("reconcileCollapsed", () => {
  const communities: Community[] = [{ id: "c:a", members: ["a", "b"] }];
  it("drops a collapsed id whose community no longer exists", () => {
    const out = reconcileCollapsed(new Set(["c:a", "c:gone"]), communities);
    expect([...out]).toEqual(["c:a"]);
  });
  it("hands back the same set when nothing needed dropping, so no needless redraw", () => {
    const same = new Set(["c:a"]);
    expect(reconcileCollapsed(same, communities)).toBe(same);
  });
});
