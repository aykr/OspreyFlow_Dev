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

  it("lists a cited fact the words never mark, and makes every occurrence of a repeated marker a fact", () => {
    const { parts, unmarked } = splitAnswer("One [G-1] and again [G-1].", [G1, G2]);
    expect(parts).toEqual([
      { kind: "text", text: "One " },
      { kind: "fact", citation: G1 },
      { kind: "text", text: " and again " },
      { kind: "fact", citation: G1 },
      { kind: "text", text: "." },
    ]);
    expect(unmarked).toEqual([G2]);
  });
});

function fakeCanvas(drawn: Record<string, boolean | null> = {}) {
  return {
    highlightNodes: vi.fn(),
    selectLink: vi.fn(),
    centreOn: vi.fn(),
    linkDrawn: vi.fn((id: string) => (id in drawn ? drawn[id]! : null)),
  };
}

describe("bringFactIntoView", () => {
  it("selects the one link a fact stands for, when it is drawn, and centres on its first end", () => {
    const canvas = fakeCanvas({ "l-1": true });
    bringFactIntoView(canvas, G1);
    expect(canvas.selectLink).toHaveBeenCalledWith("l-1");
    expect(canvas.centreOn).toHaveBeenCalledWith("n-a");
    expect(canvas.highlightNodes).not.toHaveBeenCalled();
  });

  it("selects the two ends of a link fact whose link is not drawn, rather than nothing", () => {
    const canvas = fakeCanvas({}); // the canvas holds no such link
    bringFactIntoView(canvas, G1);
    expect(canvas.selectLink).not.toHaveBeenCalled();
    expect(canvas.highlightNodes).toHaveBeenCalledWith(["n-a", "n-b"]);
  });

  it("treats a link the view hides as not drawn", () => {
    const canvas = fakeCanvas({ "l-1": false });
    bringFactIntoView(canvas, G1);
    expect(canvas.selectLink).not.toHaveBeenCalled();
    expect(canvas.highlightNodes).toHaveBeenCalledWith(["n-a", "n-b"]);
  });

  it("selects every node of a fact with several links: only one link can be selected, so none is", () => {
    const canvas = fakeCanvas({ "l-1": true, "l-2": true });
    const several: GraphCitation = { number: 3, label: "[G-3]", node_ids: ["n-a", "n-b", "n-c"], link_ids: ["l-1", "l-2"] };
    bringFactIntoView(canvas, several);
    expect(canvas.selectLink).not.toHaveBeenCalled();
    expect(canvas.highlightNodes).toHaveBeenCalledWith(["n-a", "n-b", "n-c"]);
  });

  it("selects the nodes of a fact that stands for no link", () => {
    const canvas = fakeCanvas();
    bringFactIntoView(canvas, G2);
    expect(canvas.highlightNodes).toHaveBeenCalledWith(["n-c"]);
    expect(canvas.centreOn).toHaveBeenCalledWith("n-c");
    expect(canvas.selectLink).not.toHaveBeenCalled();
  });

  it("leaves the selection as it was for a fact that names no node and no drawn link", () => {
    const canvas = fakeCanvas();
    bringFactIntoView(canvas, { number: 4, label: "[G-4]", node_ids: [], link_ids: [] });
    expect(canvas.highlightNodes).not.toHaveBeenCalled();
    expect(canvas.selectLink).not.toHaveBeenCalled();
    expect(canvas.centreOn).not.toHaveBeenCalled();
  });
});
