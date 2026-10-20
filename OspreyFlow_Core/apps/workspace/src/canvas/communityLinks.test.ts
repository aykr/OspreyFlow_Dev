import { describe, expect, it } from "vitest";

import {
  COMMUNITY_LINKS_ABOVE,
  NODE_DOTS_ABOVE,
  communityGroupOf,
  communityLinks,
  communityLinkWidth,
  drawsCommunityLinks,
  dotImage,
  drawsNodeDots,
} from "./communityLinks";
import { packBubbles } from "./layoutModes";

// ADR-119: on a large working set the zoomed-out bands draw links between communities, and the
// individual links from the neighbourhood band in.
describe("drawsCommunityLinks", () => {
  it("is true only above the link count, and only zoomed out (overview and structure)", () => {
    const many = COMMUNITY_LINKS_ABOVE + 1;
    expect(drawsCommunityLinks("overview", many)).toBe(true);
    expect(drawsCommunityLinks("structure", many)).toBe(true);
    expect(drawsCommunityLinks("neighbourhood", many)).toBe(false);
    expect(drawsCommunityLinks("link-detail", many)).toBe(false);
  });

  it("never on a working set at or under the count, whatever the zoom", () => {
    for (const band of ["overview", "structure", "neighbourhood", "link-detail"] as const) {
      expect(drawsCommunityLinks(band, COMMUNITY_LINKS_ABOVE)).toBe(false);
      expect(drawsCommunityLinks(band, 10)).toBe(false);
    }
  });
});

describe("communityLinks", () => {
  const assignment = new Map([
    ["a1", 0],
    ["a2", 0],
    ["b1", 1],
    ["b2", 1],
    ["c1", 2],
  ]);

  it("counts the links between each pair of communities, in either direction, as one", () => {
    const links: [string, string][] = [
      ["a1", "b1"],
      ["b2", "a2"],
      ["a1", "b2"],
      ["c1", "a1"],
    ];
    expect(communityLinks(assignment, links)).toEqual([
      { a: 0, b: 1, count: 3 },
      { a: 0, b: 2, count: 1 },
    ]);
  });

  it("leaves out a link inside one community, and a link with an end not yet assigned", () => {
    const links: [string, string][] = [
      ["a1", "a2"],
      ["a1", "unknown"],
      ["b1", "c1"],
    ];
    expect(communityLinks(assignment, links)).toEqual([{ a: 1, b: 2, count: 1 }]);
  });
});

describe("communityLinkWidth", () => {
  it("is a pixel for one link, wider with more, and never more than six", () => {
    expect(communityLinkWidth(1)).toBe(1);
    expect(communityLinkWidth(10)).toBeGreaterThan(1);
    expect(communityLinkWidth(100)).toBeGreaterThan(communityLinkWidth(10));
    expect(communityLinkWidth(1_000)).toBe(6);
    expect(communityLinkWidth(1_000_000)).toBe(6);
  });
});

describe("communityGroupOf", () => {
  it("names a node's community, and puts every node alone in its community in one group", () => {
    const groupOf = communityGroupOf(
      new Map([
        ["a1", 0],
        ["a2", 0],
        ["loner1", 1],
        ["loner2", 2],
      ]),
    );
    expect(groupOf("a1")).toBe("community:0");
    expect(groupOf("a2")).toBe("community:0");
    expect(groupOf("loner1")).toBe("none");
    expect(groupOf("loner2")).toBe("none");
    expect(groupOf("unknown")).toBe("none");
  });
});

describe("packBubbles at the size of a large working set (ADR-119)", () => {
  it("places 50,000 nodes in 40 communities, each node once, quickly", () => {
    const nodes = Array.from({ length: 50_000 }, (_, i) => ({ id: `n${i}`, x: 0, y: 0, type: "Person" }));
    const assignment = new Map(nodes.map((node, i) => [node.id, i % 40]));
    const started = performance.now();
    const placed = packBubbles({ nodes, edges: [] }, communityGroupOf(assignment));
    expect(placed.size).toBe(50_000);
    expect(performance.now() - started).toBeLessThan(2000);
  });
});

describe("drawsNodeDots", () => {
  it("is true only above the node count, and only zoomed out (overview and structure)", () => {
    const many = NODE_DOTS_ABOVE + 1;
    expect(drawsNodeDots("overview", many)).toBe(true);
    expect(drawsNodeDots("structure", many)).toBe(true);
    expect(drawsNodeDots("neighbourhood", many)).toBe(false);
    expect(drawsNodeDots("link-detail", many)).toBe(false);
    for (const band of ["overview", "structure", "neighbourhood", "link-detail"] as const) {
      expect(drawsNodeDots(band, NODE_DOTS_ABOVE)).toBe(false);
    }
  });
});

// Under Sigma 4 a dot is a picture, not a program (ADR-119 Amendment 1): a plain circle in the
// node's colour, one per colour, with no icon and no outline in another colour.
describe("dotImage", () => {
  it("is one plain circle per colour", () => {
    expect(dotImage("#336699")).toBe(dotImage("#336699"));
    expect(dotImage("#336699")).not.toBe(dotImage("#993366"));
    const svg = decodeURIComponent(dotImage("#336699"));
    expect(svg).toContain("<circle");
    expect(svg.toLowerCase()).not.toContain("#993366");
  });
});
