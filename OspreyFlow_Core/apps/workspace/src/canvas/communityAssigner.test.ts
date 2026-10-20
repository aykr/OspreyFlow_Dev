import { describe, expect, it } from "vitest";

import { assignCommunities } from "./communities";
import { latestOnly, workerAssign } from "./communityAssigner";

describe("assignCommunities (ADR-119)", () => {
  it("gives every node a community, a node with no link included", () => {
    const assignment = assignCommunities(["a", "b", "c", "lonely"], [
      ["a", "b"],
      ["b", "c"],
    ]);
    expect(Object.keys(assignment).sort()).toEqual(["a", "b", "c", "lonely"]);
    expect(assignment.lonely).not.toBe(assignment.a);
  });

  it("puts two tight groups joined by one link into two communities, the same way every time", () => {
    const left = ["l1", "l2", "l3", "l4"];
    const right = ["r1", "r2", "r3", "r4"];
    const links: [string, string][] = [];
    for (const group of [left, right]) {
      for (let i = 0; i < group.length; i++) for (let j = i + 1; j < group.length; j++) links.push([group[i]!, group[j]!]);
    }
    links.push(["l1", "r1"]);
    const first = assignCommunities([...left, ...right], links);
    expect(new Set(left.map((id) => first[id])).size).toBe(1);
    expect(new Set(right.map((id) => first[id])).size).toBe(1);
    expect(first.l1).not.toBe(first.r1);
    expect(assignCommunities([...left, ...right], links)).toEqual(first);
  });
});

describe("latestOnly", () => {
  it("drops an answer to a question asked before the latest one", async () => {
    const pending: ((value: Record<string, number>) => void)[] = [];
    const ask = latestOnly(() => new Promise((resolve) => pending.push(resolve)));
    const older = ask(["a"], []);
    const newer = ask(["b"], []);
    pending[0]!({ a: 0 });
    pending[1]!({ b: 1 });
    expect(await older).toBeNull();
    expect(await newer).toEqual(new Map([["b", 1]]));
  });
});

describe("workerAssign", () => {
  it("runs in place where there is no Worker, with the same answer", async () => {
    expect(await workerAssign()(["a", "b"], [["a", "b"]])).toEqual(assignCommunities(["a", "b"], [["a", "b"]]));
  });
});
