import { describe, expect, it } from "vitest";

import { makeEdge, makeNode } from "../testing/fixtures";
import type { WorkingSetDelta } from "./models";
import { createWorkingSet } from "./store";

describe("createWorkingSet", () => {
  it("applies an add delta to the graph and bumps seq", () => {
    const { graph, store } = createWorkingSet();

    store.getState().applyDelta({
      seq: 1,
      op: "add",
      nodes: [makeNode("n1"), makeNode("n2")],
      edges: [makeEdge("e1", "n1", "n2")],
    });

    expect(graph.order).toBe(2);
    expect(graph.size).toBe(1);
    expect(store.getState().seq).toBe(1);
  });

  it("does not double-add a node already in the graph", () => {
    const { graph, store } = createWorkingSet();
    store.getState().applyDelta({ seq: 1, op: "add", nodes: [makeNode("n1")], edges: [] });

    store.getState().applyDelta({ seq: 2, op: "add", nodes: [makeNode("n1")], edges: [] });

    expect(graph.order).toBe(1);
  });

  it("merges update properties without touching membership", () => {
    const { graph, store } = createWorkingSet();
    store
      .getState()
      .applyDelta({ seq: 1, op: "add", nodes: [makeNode("n1", { properties: { a: 1 } })], edges: [] });

    store.getState().applyDelta({
      seq: 2,
      op: "update",
      nodes: [{ id: "n1", properties: { b: 2 } }],
    });

    const data = graph.getNodeAttribute("n1", "data");
    expect(data.properties).toEqual({ a: 1, b: 2 });
    expect(graph.order).toBe(1);
  });

  it("removing a node also drops its incident edges", () => {
    const { graph, store } = createWorkingSet();
    store.getState().applyDelta({
      seq: 1,
      op: "add",
      nodes: [makeNode("n1"), makeNode("n2")],
      edges: [makeEdge("e1", "n1", "n2")],
    });

    store.getState().applyDelta({ seq: 2, op: "remove", node_ids: ["n1"] });

    expect(graph.order).toBe(1);
    expect(graph.size).toBe(0);
  });

  it("a snapshot replaces the entire graph contents", () => {
    const { graph, store } = createWorkingSet();
    store.getState().applyDelta({ seq: 1, op: "add", nodes: [makeNode("stale")], edges: [] });

    store.getState().applyDelta({
      seq: 5,
      op: "snapshot",
      nodes: [makeNode("n1"), makeNode("n2")],
      edges: [makeEdge("e1", "n1", "n2")],
    });

    expect(graph.hasNode("stale")).toBe(false);
    expect(graph.order).toBe(2);
    expect(store.getState().seq).toBe(5);
  });

  // ADR-124 decision 5: a stale server still sends `filtered_count` and `notice`; the Glass keeps
  // no figure from either and does not fail on them.
  it("a notice delta and a filtered_count field are ignored without error", () => {
    const { graph, store } = createWorkingSet();
    store.getState().applyDelta({
      seq: 1,
      op: "snapshot",
      nodes: [makeNode("n1")],
      edges: [],
      filtered_count: 2,
    } as unknown as WorkingSetDelta);
    expect(() =>
      store.getState().applyDelta({
        seq: 2,
        op: "notice",
        level: "warning",
        message: "3 item(s) withheld by handling policy",
        count: 3,
      } as unknown as WorkingSetDelta),
    ).not.toThrow();
    const state = store.getState() as unknown as Record<string, unknown>;
    expect(state.filteredCount).toBeUndefined();
    expect(state.notices).toBeUndefined();
    expect(state.withheld).toBe(false);
    expect(graph.order).toBe(1);
  });

  describe("the standing sentence's flag (ADR-124 decision 5)", () => {
    const snapshot = (seq: number, withheld?: boolean | null): WorkingSetDelta => ({
      seq,
      op: "snapshot",
      nodes: [makeNode("n1")],
      edges: [],
      ...(withheld === undefined ? {} : { withheld }),
    });

    it("is false until a snapshot says true", () => {
      const { store } = createWorkingSet();
      expect(store.getState().withheld).toBe(false);
      store.getState().applyDelta(snapshot(1, false));
      expect(store.getState().withheld).toBe(false);
      store.getState().applyDelta(snapshot(2, true));
      expect(store.getState().withheld).toBe(true);
    });

    it("keeps the last non-null value: a null or absent field never overwrites a true", () => {
      const { store } = createWorkingSet();
      store.getState().applyDelta(snapshot(1, true));
      store.getState().applyDelta(snapshot(2, null));
      expect(store.getState().withheld).toBe(true);
      store.getState().applyDelta(snapshot(3));
      expect(store.getState().withheld).toBe(true);
    });

    it("survives later deltas of every other kind", () => {
      const { store } = createWorkingSet();
      store.getState().applyDelta(snapshot(1, true));
      store.getState().applyDelta({ seq: 2, op: "add", nodes: [makeNode("n2")], edges: [] });
      store.getState().applyDelta({ seq: 3, op: "remove", node_ids: ["n2"] });
      expect(store.getState().withheld).toBe(true);
    });

    it("a later false replaces a true (a restore may declassify)", () => {
      const { store } = createWorkingSet();
      store.getState().applyDelta(snapshot(1, true));
      store.getState().applyDelta(snapshot(2, false));
      expect(store.getState().withheld).toBe(false);
    });

    it("resets when the case changes", () => {
      const { store } = createWorkingSet();
      store.getState().applyDelta(snapshot(1, true));
      store.getState().resetCase();
      expect(store.getState().withheld).toBe(false);
      store.getState().applyDelta(snapshot(1, null));
      expect(store.getState().withheld).toBe(false);
    });
  });

  it("reproject bumps seq and annotates every affected node's cluster id, without touching membership", () => {
    const { graph, store } = createWorkingSet();
    store.getState().applyDelta({
      seq: 1,
      op: "add",
      nodes: [makeNode("n1"), makeNode("n2")],
      edges: [],
    });

    store.getState().applyDelta({
      seq: 2,
      op: "reproject",
      reason: "resolution_threshold",
      merged: 1,
      split: 0,
      affected: 2,
      affected_cluster_ids: { n1: "n1", n2: "n1" },
    });

    expect(graph.order).toBe(2);
    expect(store.getState().seq).toBe(2);
    expect(graph.getNodeAttribute("n1", "data").resolution?.cluster_id).toBe("n1");
    expect(graph.getNodeAttribute("n2", "data").resolution?.cluster_id).toBe("n1");
  });

  it("reproject silently skips an affected node not (yet) in this client's own graph", () => {
    const { graph, store } = createWorkingSet();
    store.getState().applyDelta({ seq: 1, op: "add", nodes: [makeNode("n1")], edges: [] });

    store.getState().applyDelta({
      seq: 2,
      op: "reproject",
      reason: "resolution_threshold",
      merged: 1,
      split: 0,
      affected: 2,
      affected_cluster_ids: { n1: "n1", "not-in-graph": "n1" },
    });

    expect(graph.order).toBe(1);
    expect(graph.hasNode("not-in-graph")).toBe(false);
    expect(graph.getNodeAttribute("n1", "data").resolution?.cluster_id).toBe("n1");
  });
  it("a replaced link leaves the graph and its replacement arrives in the same step (ADR-080)", () => {
    const { graph, store } = createWorkingSet();
    store.getState().applyDelta({
      seq: 1,
      op: "add",
      nodes: [makeNode("n1"), makeNode("n2")],
      edges: [makeEdge("e1", "n1", "n2")],
    });

    store.getState().applyDelta({
      seq: 2,
      op: "replace_edge",
      old_edge_id: "e1",
      edge: makeEdge("e2", "n1", "n2", { type: "FAMILY_OF" }),
    });

    expect(graph.hasEdge("e1")).toBe(false);
    expect(graph.hasEdge("e2")).toBe(true);
    expect(graph.getEdgeAttribute("e2", "data").type).toBe("FAMILY_OF");
    expect(graph.size).toBe(1);
    expect(store.getState().seq).toBe(2);
  });

  it("a replacement is still added when the old link was never in this client's graph", () => {
    const { graph, store } = createWorkingSet();
    store.getState().applyDelta({
      seq: 1,
      op: "add",
      nodes: [makeNode("n1"), makeNode("n2")],
      edges: [],
    });

    store.getState().applyDelta({
      seq: 2,
      op: "replace_edge",
      old_edge_id: "gone",
      edge: makeEdge("e2", "n1", "n2"),
    });

    expect(graph.hasEdge("e2")).toBe(true);
  });

  it("a replacement whose ends are not in this client's graph is skipped, not thrown on", () => {
    const { graph, store } = createWorkingSet();
    store.getState().applyDelta({ seq: 1, op: "add", nodes: [makeNode("n1")], edges: [] });

    store.getState().applyDelta({
      seq: 2,
      op: "replace_edge",
      old_edge_id: "e1",
      edge: makeEdge("e2", "n1", "missing"),
    });

    expect(graph.size).toBe(0);
    expect(store.getState().seq).toBe(2);
  });
});
