import { afterEach, describe, expect, it, vi } from "vitest";

import * as api from "../analytics/api";
import { buildEventFilter, createCrossFilterStore } from "./store";

describe("buildEventFilter", () => {
  it("carries no window or node restriction when neither is set", () => {
    const filter = buildEventFilter("inv-1", null, null);
    expect(filter).toEqual({
      investigation_scope: "inv-1",
      window: null,
      node_ids: [],
      edge_types: [],
    });
  });

  it("translates a TimeWindow into an Interval", () => {
    const filter = buildEventFilter("inv-1", { validFrom: "2026-01-01T00:00:00Z", validTo: null }, null);
    expect(filter.window).toEqual({ valid_from: "2026-01-01T00:00:00Z", valid_to: null });
  });

  it("carries the selected node ids", () => {
    const filter = buildEventFilter("inv-1", null, ["a", "b"]);
    expect(filter.node_ids).toEqual(["a", "b"]);
  });
});

describe("createCrossFilterStore", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("dims nothing when no filter is active, without calling the API", async () => {
    const spy = vi.spyOn(api, "fetchCrossFilter");
    const { store, refresh } = createCrossFilterStore("http://api", "token", "inv-1");

    await refresh(["a", "b", "c"]);

    expect(spy).not.toHaveBeenCalled();
    expect(store.getState().dimmedNodeIds.size).toBe(0);
    expect(store.getState().dimmedCount).toBe(0);
  });

  it("dims every node id absent from the surviving source_id/target_id buckets", async () => {
    vi.spyOn(api, "fetchCrossFilter").mockResolvedValue({
      source_id: { bucketing: "categorical", total: 2, buckets: [{ label: "a", count: 1 }] },
      target_id: { bucketing: "categorical", total: 1, buckets: [{ label: "b", count: 1 }] },
    });
    const { store, refresh } = createCrossFilterStore("http://api", "token", "inv-1");
    store.getState().setWindow({ validFrom: "2026-01-01T00:00:00Z", validTo: null });

    await refresh(["a", "b", "c"]);

    expect(store.getState().dimmedNodeIds).toEqual(new Set(["c"]));
    expect(store.getState().dimmedCount).toBe(1);
  });

  it("clearFilter resets both the inputs and the derived dimming state", () => {
    const { store } = createCrossFilterStore("http://api", "token", "inv-1");
    store.getState().setSelectedNodeIds(["a"]);
    store.setState({ dimmedNodeIds: new Set(["b"]), dimmedCount: 1 });

    store.getState().clearFilter();

    expect(store.getState()).toMatchObject({
      window: null,
      selectedNodeIds: null,
      dimmedCount: 0,
    });
    expect(store.getState().dimmedNodeIds.size).toBe(0);
  });
});
