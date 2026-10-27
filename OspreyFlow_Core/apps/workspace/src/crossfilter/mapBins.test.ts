import { describe, expect, it, vi } from "vitest";

import * as api from "../analytics/api";
import { createCrossFilterStore } from "./store";
import { followCrossFilterWithMapBins } from "./mapBins";

describe("the map's bins follow the cross-filter (ADR-130 decision 2)", () => {
  it("asks again, with the cells in the request, when the cells change, and not when nothing did", async () => {
    const asked: unknown[] = [];
    vi.spyOn(api, "fetchGeoBins").mockImplementation(async (_u, _t, request) => {
      asked.push(request);
      return [];
    });
    const { store } = createCrossFilterStore("http://api", "token", "inv-1");
    const unsubscribe = followCrossFilterWithMapBins(store, "http://api", "token", "inv-1", 8, () => {});

    await vi.waitFor(() => expect(asked).toHaveLength(1)); // the first read, no filter
    store.getState().setCells([{ weekday: 5, hour: 9 }]);
    await vi.waitFor(() => expect(asked).toHaveLength(2));
    expect((asked[1] as { filter: { weekday_hours?: unknown } }).filter.weekday_hours).toEqual([
      { weekday: 5, hour: 9 },
    ]);
    store.setState({ dimmedCount: 3 }); // nothing the bins depend on
    store.getState().setCells(null);
    await vi.waitFor(() => expect(asked).toHaveLength(3));
    expect((asked[2] as { filter: object }).filter).not.toHaveProperty("weekday_hours");
    unsubscribe();
    vi.restoreAllMocks();
  });
});
