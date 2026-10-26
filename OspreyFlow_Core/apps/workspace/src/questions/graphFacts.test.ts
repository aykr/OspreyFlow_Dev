// ADR-129 decision 1: a `[G-n]` in an answer is mapped to ids from the payload alone, and selecting
// it selects those ids on the canvas and brings them into view.
import { describe, expect, it, vi } from "vitest";

import { bringFactIntoView, splitAnswer, type GraphCitation } from "./graphFacts";

const G1: GraphCitation = { number: 1, label: "[G-1]", node_ids: ["n-a", "n-b"], link_ids: ["l-1"] };
const G2: GraphCitation = { number: 2, label: "[G-2]", node_ids: ["n-c"], link_ids: [] };

describe("splitAnswer", () => {
  it("turns each marker the payload holds into a fact, in order, and keeps the words between", () => {
    const { parts, unmarked } = splitAnswer("Dana called him [G-1], then Rohan [G-2].", [G1, G2]);
    expect(parts).toEqual([
      { kind: "text", text: "Dana called him " },
      { kind: "fact", citation: G1 },
      { kind: "text", text: ", then Rohan " },
      { kind: "fact", citation: G2 },
      { kind: "text", text: "." },
    ]);
    expect(unmarked).toEqual([]);
  });

  it("leaves a number the payload does not hold as plain words: nothing is looked up from the text", () => {
    const { parts } = splitAnswer("See [G-7].", [G1]);
    expect(parts).toEqual([{ kind: "text", text: "See [G-7]." }]);
  });

  it("lists a cited fact the words never mark, and shows a fact marked twice once", () => {
    const { parts, unmarked } = splitAnswer("One [G-1] and again [G-1].", [G1, G2]);
    expect(parts.filter((p) => p.kind === "fact")).toHaveLength(1);
    expect(unmarked).toEqual([G2]);
  });
});

describe("bringFactIntoView", () => {
  it("selects the link a fact stands for and centres on its first end", () => {
    const canvas = { highlightNodes: vi.fn(), selectLink: vi.fn(), centreOn: vi.fn() };
    bringFactIntoView(canvas, G1);
    expect(canvas.selectLink).toHaveBeenCalledWith("l-1");
    expect(canvas.centreOn).toHaveBeenCalledWith("n-a");
    expect(canvas.highlightNodes).not.toHaveBeenCalled();
  });

  it("selects the nodes of a fact that stands for no link", () => {
    const canvas = { highlightNodes: vi.fn(), selectLink: vi.fn(), centreOn: vi.fn() };
    bringFactIntoView(canvas, G2);
    expect(canvas.highlightNodes).toHaveBeenCalledWith(["n-c"]);
    expect(canvas.centreOn).toHaveBeenCalledWith("n-c");
    expect(canvas.selectLink).not.toHaveBeenCalled();
  });
});
