import { describe, expect, it } from "vitest";

import { describeEmptyExpansion } from "./expansionOutcome";

// A relationship chosen from a node's menu can add nothing: everything it leads to is already in
// view, or it leads nowhere. Doing nothing and saying nothing looks like a fault (seen 3 October
// 2026 on the Fixture Corp case, where the six Volkovs are already all drawn).

const none = () => false;
const only = (...ids: string[]) => (id: string) => ids.includes(id);

describe("describeEmptyExpansion", () => {
  it("says nothing when the expansion added a node", () => {
    expect(
      describeEmptyExpansion({ rootId: "root", nodeIds: ["a", "b"], edgeIds: ["e1"], hasNode: only("a"), hasEdge: only("e1"), edgeType: "SAME_AS" }),
    ).toBeNull();
  });

  it("says nothing when it added only a link between nodes already drawn", () => {
    expect(
      describeEmptyExpansion({ rootId: "root", nodeIds: ["a", "b"], edgeIds: ["e1"], hasNode: only("a", "b"), hasEdge: none, edgeType: "SAME_AS" }),
    ).toBeNull();
  });

  it("says everything is already in view when it returned only what is drawn", () => {
    expect(
      describeEmptyExpansion({
        rootId: "root",
        nodeIds: ["a", "b", "c"],
        edgeIds: ["e1", "e2"],
        hasNode: only("a", "b", "c"),
        hasEdge: only("e1", "e2"),
        edgeType: "SAME_AS",
      }),
    ).toBe("Nothing new: everything linked by SAME_AS is already in view.");
  });

  it("says the node has no such links when the server returned nothing", () => {
    expect(
      describeEmptyExpansion({ rootId: "root", nodeIds: [], edgeIds: [], hasNode: none, hasEdge: none, edgeType: "MEMBER_OF" }),
    ).toBe("No MEMBER_OF links from this node.");
  });

  it("does not name a relationship when every kind was asked for", () => {
    expect(describeEmptyExpansion({ rootId: "root", nodeIds: [], edgeIds: [], hasNode: none, hasEdge: none, edgeType: null })).toBe(
      "No links from this node.",
    );
    expect(
      describeEmptyExpansion({ rootId: "root", nodeIds: ["a"], edgeIds: [], hasNode: only("a"), hasEdge: none, edgeType: null }),
    ).toBe("Nothing new: everything linked to this node is already in view.");
  });

  it("does not count the node being expanded as something it led to", () => {
    // The server may return the node itself; a node with no links must still be told so.
    expect(
      describeEmptyExpansion({ rootId: "self", nodeIds: ["self"], edgeIds: [], hasNode: only("self"), hasEdge: none, edgeType: "ASSOCIATE_OF" }),
    ).toBe("No ASSOCIATE_OF links from this node.");
  });
});
