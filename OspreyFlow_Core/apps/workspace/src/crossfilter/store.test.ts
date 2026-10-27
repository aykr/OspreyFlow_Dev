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
    const spy = vi.spyOn(api, "fetchFirstSeen");
    const { store, refresh } = createCrossFilterStore("http://api", "token", "inv-1");

    await refresh(["a", "b", "c"]);

    expect(spy).not.toHaveBeenCalled();
    expect(store.getState().dimmedNodeIds.size).toBe(0);
    expect(store.getState().dimmedCount).toBe(0);
  });

  it("dims every node id with no event in the window, and every link too (ADR-087)", async () => {
    const spy = vi.spyOn(api, "fetchFirstSeen").mockResolvedValue({
      nodes: { a: "2026-01-02T00:00:00Z", b: "2026-01-02T00:00:00Z" },
      edges: { ab: "2026-01-02T00:00:00Z" },
    });
    const { store, refresh } = createCrossFilterStore("http://api", "token", "inv-1");
    store.getState().setWindow({ validFrom: "2026-01-01T00:00:00Z", validTo: null });

    await refresh(["a", "b", "c"], ["ab", "bc"]);

    expect(spy).toHaveBeenCalledWith("http://api", "token", {
      filter: {
        investigation_scope: "inv-1",
        window: { valid_from: "2026-01-01T00:00:00Z", valid_to: null },
        node_ids: [],
        edge_types: [],
      },
    });
    expect(store.getState().dimmedNodeIds).toEqual(new Set(["c"]));
    expect(store.getState().dimmedEdgeIds).toEqual(new Set(["bc"]));
    expect(store.getState().dimmedCount).toBe(1);
    // Kept for the playback, which lights things up in this order.
    expect(store.getState().firstSeen?.nodes.a).toBe("2026-01-02T00:00:00Z");
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

describe("the weekly view's cells (ADR-130 decision 2)", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  const WEEKEND = [
    { weekday: 5, hour: 9 },
    { weekday: 6, hour: 9 },
  ];

  it("buildEventFilter sends the cells, an empty choice as an empty list, and none as no key at all", () => {
    expect(buildEventFilter("inv-1", null, null, WEEKEND).weekday_hours).toEqual(WEEKEND);
    expect(buildEventFilter("inv-1", null, null, []).weekday_hours).toEqual([]);
    expect(buildEventFilter("inv-1", null, null, null)).not.toHaveProperty("weekday_hours");
    expect(buildEventFilter("inv-1", null, null)).not.toHaveProperty("weekday_hours");
  });

  it("starts with no cells, and setCells holds them", () => {
    const { store } = createCrossFilterStore("http://api", "token", "inv-1");
    expect(store.getState().cells).toBeNull();
    store.getState().setCells(WEEKEND);
    expect(store.getState().cells).toEqual(WEEKEND);
  });

  it("cells alone make the filter active: refresh asks which nodes survive, with the cells in the request", async () => {
    const spy = vi.spyOn(api, "fetchFirstSeen").mockResolvedValue({
      nodes: { a: "2026-01-10T09:00:00Z" },
      edges: { ab: "2026-01-10T09:00:00Z" },
    });
    const { store, refresh } = createCrossFilterStore("http://api", "token", "inv-1");
    store.getState().setCells(WEEKEND);

    await refresh(["a", "b"], ["ab", "bc"]);

    expect(spy).toHaveBeenCalledWith("http://api", "token", {
      filter: {
        investigation_scope: "inv-1",
        window: null,
        node_ids: [],
        edge_types: [],
        weekday_hours: WEEKEND,
      },
    });
    expect(store.getState().dimmedNodeIds).toEqual(new Set(["b"]));
    expect(store.getState().dimmedEdgeIds).toEqual(new Set(["bc"]));
  });

  it("an empty choice of cells is still a filter: it matches nothing, so everything dims", async () => {
    vi.spyOn(api, "fetchFirstSeen").mockResolvedValue({ nodes: {}, edges: {} });
    const { store, refresh } = createCrossFilterStore("http://api", "token", "inv-1");
    store.getState().setCells([]);

    await refresh(["a", "b"]);

    expect(store.getState().dimmedNodeIds).toEqual(new Set(["a", "b"]));
  });

  it("clearFilter clears the cells", () => {
    const { store } = createCrossFilterStore("http://api", "token", "inv-1");
    store.getState().setCells(WEEKEND);
    store.getState().clearFilter();
    expect(store.getState().cells).toBeNull();
  });
});

