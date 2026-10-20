import { describe, expect, it } from "vitest";

import { COMMUNITY_LINKS_ABOVE, communityLinks, communityLinkWidth, drawsCommunityLinks } from "./communityLinks";

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
