import { describe, expect, it } from "vitest";

import { makeNode } from "../testing/fixtures";
import { createWorkingSet } from "../workingset/store";
import { explanationBasis, visiblePairs } from "./explainView";
import type { ClusterExplanation, PairwiseExplanation } from "../workingset/models";

function pair(overrides: Partial<PairwiseExplanation> = {}): PairwiseExplanation {
  return {
    node_a: "n1",
    node_b: "n2",
    edge_type: "SAME_AS",
    score: 0.97,
    model_version: "splink-3.9.9-config-1",
    comparison_vector: null,
    manually_asserted: false,
    meets_threshold: true,
    ...overrides,
  };
}

describe("visiblePairs", () => {
  it("keeps a pair whose both endpoints are in member_node_ids and already in the local graph", () => {
    const { graph, store } = createWorkingSet();
    store.getState().applyDelta({
      seq: 1,
      op: "add",
      nodes: [makeNode("n1"), makeNode("n2")],
      edges: [],
    });
    const explanation: ClusterExplanation = {
      cluster_id: "n1",
      member_node_ids: ["n1", "n2"],
      pairs: [pair()],
    };

    expect(visiblePairs(explanation, graph)).toEqual([pair()]);
  });

  // Phase 6a Stage 3, Question 1: a future backend regression naming a node outside its own
  // `member_node_ids` must never reach the table — checked here independently of the backend's
  // own access-control test (`test_explain_cluster_access_control.py`), which proves the API
  // itself never does this today. This is the rendering-boundary's own, separate guarantee.
  it("drops a pair naming a node absent from member_node_ids, even if it is in the local graph", () => {
    const { graph, store } = createWorkingSet();
    store.getState().applyDelta({
      seq: 1,
      op: "add",
      nodes: [makeNode("n1"), makeNode("n2"), makeNode("hidden")],
      edges: [],
    });
    const explanation: ClusterExplanation = {
      cluster_id: "n1",
      member_node_ids: ["n1", "n2"], // "hidden" deliberately not listed
      pairs: [pair(), pair({ node_a: "n1", node_b: "hidden" })],
    };

    const result = visiblePairs(explanation, graph);
    expect(result).toEqual([pair()]);
    expect(result.some((p) => p.node_a === "hidden" || p.node_b === "hidden")).toBe(false);
  });

  it("drops a pair naming a member_node_ids entry not yet present in this session's own graph", () => {
    const { graph, store } = createWorkingSet();
    store.getState().applyDelta({
      seq: 1,
      op: "add",
      nodes: [makeNode("n1")], // "n2" never synced to this client
      edges: [],
    });
    const explanation: ClusterExplanation = {
      cluster_id: "n1",
      member_node_ids: ["n1", "n2"],
      pairs: [pair()],
    };

    expect(visiblePairs(explanation, graph)).toEqual([]);
  });
});

describe("explanationBasis", () => {
  it("a manually-asserted pair reads as asserted, never as missing data", () => {
    const manual = pair({
      manually_asserted: true,
      score: null,
      model_version: null,
      comparison_vector: null,
    });

    expect(explanationBasis(manual)).toBe("Asserted by analyst");
  });

  it("a model-scored pair shows its score and model version", () => {
    const scored = pair({ score: 0.973, model_version: "splink-3.9.9-config-1" });

    expect(explanationBasis(scored)).toBe("0.97 · splink-3.9.9-config-1");
  });

  it("a model-scored pair with a comparison vector includes it inline", () => {
    const scored = pair({
      score: 0.9,
      model_version: "splink-3.9.9-config-1",
      comparison_vector: { given_name: 0.88, family_name: 0.95 },
    });

    expect(explanationBasis(scored)).toBe(
      "0.90 · splink-3.9.9-config-1 (given_name: 0.88, family_name: 0.95)",
    );
  });
});
