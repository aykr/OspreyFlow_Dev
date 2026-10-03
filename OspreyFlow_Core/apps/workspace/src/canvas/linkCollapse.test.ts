import { describe, expect, it } from "vitest";

import { sameAsGroup } from "./linkCollapse";

const clusters: Record<string, string | undefined> = {
  a: "k1",
  b: "k1",
  c: "k1",
  d: "k2",
  e: undefined,
};
const inView = ["a", "b", "c", "d", "e", "f"];
const clusterOf = (id: string) => clusters[id];

describe("sameAsGroup", () => {
  it("folds the whole cluster when both ends belong to it, so one entity is one node", () => {
    const group = sameAsGroup("a", "b", inView, clusterOf);
    expect(group.members).toEqual(["a", "b", "c"]);
    expect(group.label).toBe("Same entity: 3 nodes");
  });

  it("folds only the two ends when the link does not join them into one cluster", () => {
    const group = sameAsGroup("a", "d", inView, clusterOf);
    expect(group.members).toEqual(["a", "d"]);
    expect(group.label).toBe("Same entity: 2 nodes");
  });

  it("folds only the two ends when neither has a cluster", () => {
    expect(sameAsGroup("e", "f", inView, clusterOf).members).toEqual(["e", "f"]);
  });

  it("names the group the same way wherever the link is clicked from, so it can be opened again", () => {
    expect(sameAsGroup("a", "b", inView, clusterOf).id).toBe(sameAsGroup("b", "a", inView, clusterOf).id);
    expect(sameAsGroup("a", "b", inView, clusterOf).id).toBe(sameAsGroup("a", "c", inView, clusterOf).id);
  });

  it("starts the name with s: so it cannot be mistaken for a community's c: name", () => {
    expect(sameAsGroup("a", "b", inView, clusterOf).id.startsWith("s:")).toBe(true);
  });

  it("leaves out a cluster member that is not in the view", () => {
    expect(sameAsGroup("a", "b", ["a", "b", "d"], clusterOf).members).toEqual(["a", "b"]);
  });
});
