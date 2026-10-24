import { describe, expect, it } from "vitest";

import { makeEdge, makeNode } from "../testing/fixtures";
import { createWorkingSet } from "../workingset/store";
import { edgeReducer, nodeReducer, zoomBandForRatio } from "./zoomBands";

describe("zoomBandForRatio", () => {
  it("covers every camera ratio with exactly one of the four bands", () => {
    expect(zoomBandForRatio(0.05)).toBe("link-detail");
    expect(zoomBandForRatio(0.3)).toBe("neighbourhood");
    expect(zoomBandForRatio(1)).toBe("structure");
    expect(zoomBandForRatio(5)).toBe("overview");
  });
});

describe("nodeReducer / edgeReducer", () => {
  it("never return a graph or store — only per-element display attributes", () => {
    const node = nodeReducer({ degree: 20 }, 1); // "structure" band
    expect(node).toEqual({ hidden: false, labelEligible: true });

    const edge = edgeReducer({ weight: 0 }, 5); // "overview" band, zero-weight
    expect(edge.hidden).toBe(true);
  });
});

describe("zoom vs filter separation (exit-criterion invariant)", () => {
  it("sweeping every zoom band never changes graph.order or graph.size", () => {
    const { graph, store } = createWorkingSet();
    store.getState().applyDelta({
      seq: 1,
      op: "snapshot",
      nodes: [makeNode("n1"), makeNode("n2"), makeNode("n3")],
      edges: [makeEdge("e1", "n1", "n2"), makeEdge("e2", "n2", "n3")],
      withheld: true,
    });

    const orderBefore = graph.order;
    const sizeBefore = graph.size;

    // A representative ratio from each of the four bands, sweeping from
    // closest zoom to furthest out and back — `nodeReducer`/`edgeReducer`
    // are called the way Sigma would call them per frame, purely for
    // their *return value*; nothing here can reach the graph itself,
    // which is exactly the point being proven.
    const ratios = [0.05, 0.3, 1, 5, 1, 0.3, 0.05];
    for (const ratio of ratios) {
      graph.forEachNode((_id, attrs) => {
        nodeReducer({ degree: graph.degree(_id) }, ratio);
        void attrs;
      });
      graph.forEachEdge((_id, attrs) => {
        edgeReducer({ weight: (attrs.data.weight as number | undefined) ?? 1 }, ratio);
      });

      expect(graph.order).toBe(orderBefore);
      expect(graph.size).toBe(sizeBefore);
    }

    // And the store's own status-bar-facing flag is untouched by any of
    // this — zoom is not a filter, so it must not have moved either (it began true, so a sweep that
    // reset it would be seen).
    expect(store.getState().withheld).toBe(true);
  });
});
