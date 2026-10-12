// ADR-115 E5 (review item 11): hovering a link says its type and how many links of that type join
// the same two entities — counted from what the canvas holds, in words.
import Graph from "graphology";
import { describe, expect, it } from "vitest";

import { linkHoverText } from "./linkHover";

function graph() {
  const g = new Graph({ multi: true, type: "mixed" }); // as `workingset/store.ts` makes it
  for (const id of ["a", "b", "c"]) g.addNode(id);
  const add = (key: string, type: string, s: string, t: string) =>
    g.addEdgeWithKey(key, s, t, { data: { id: key, type, source: s, target: t } });
  add("e1", "COMMUNICATED_WITH", "a", "b");
  add("e2", "COMMUNICATED_WITH", "b", "a");
  add("e3", "COMMUNICATED_WITH", "a", "b");
  add("e4", "OWNS", "a", "b");
  add("e5", "COMMUNICATED_WITH", "a", "c");
  return g;
}

describe("a link's hover text", () => {
  it("names its type and counts the links of that type between the same two, either way round", () => {
    expect(linkHoverText(graph(), "e1", [])).toEqual({ type: "Communicated with", count: "3 links of this type between these two" });
  });

  it("uses the type's declared label and says one link plainly", () => {
    expect(linkHoverText(graph(), "e4", [{ name: "OWNS", label: "Owns" }])).toEqual({
      type: "Owns",
      count: "1 link of this type between these two",
    });
  });

  it("says nothing for a link not on the canvas", () => {
    expect(linkHoverText(graph(), "nope", [])).toBeNull();
  });
});
