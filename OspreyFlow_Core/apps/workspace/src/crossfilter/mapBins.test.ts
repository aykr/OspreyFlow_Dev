import { describe, expect, it, vi } from "vitest";

import type { GeoBin } from "../../../../packages/schemas/generated";
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

describe("the map's bins, answers out of order", () => {
  it("drops an older bins answer that arrives after a newer one", async () => {
    const resolvers: Array<(bins: GeoBin[]) => void> = [];
    vi.spyOn(api, "fetchGeoBins").mockImplementation(
      () => new Promise<GeoBin[]>((resolve) => resolvers.push(resolve)),
    );
    const { store } = createCrossFilterStore("http://api", "token", "inv-1");
    const delivered: GeoBin[][] = [];
    const unsubscribe = followCrossFilterWithMapBins(store, "http://api", "token", "inv-1", 8, (b) =>
      delivered.push(b),
    );
    await vi.waitFor(() => expect(resolvers).toHaveLength(1)); // the first read
    store.getState().setCells([{ weekday: 5, hour: 9 }]);
    await vi.waitFor(() => expect(resolvers).toHaveLength(2));

    const bin = (cell: string): GeoBin => ({ cell, count: 1 }) as unknown as GeoBin;
    resolvers[1]!([bin("newer")]);
    await vi.waitFor(() => expect(delivered).toHaveLength(1));
    resolvers[0]!([bin("older")]);
    await new Promise((r) => setTimeout(r, 10));

    expect(delivered).toEqual([[bin("newer")]]);
    unsubscribe();
    vi.restoreAllMocks();
  });
});

