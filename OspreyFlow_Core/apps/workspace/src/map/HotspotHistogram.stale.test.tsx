// @vitest-environment jsdom
// A stale answer: the filter moved while an older cross-filter read was in flight, and the older one
// arrived last. The panel keeps what the newer read said.
import { cleanup, render, waitFor } from "@testing-library/react";
import { act } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Histogram } from "../../../../packages/schemas/generated";

const resolvers: Array<(value: { target_id: Histogram }) => void> = [];
vi.mock("../analytics/api", () => ({
  fetchCrossFilter: () =>
    new Promise<{ target_id: Histogram }>((resolve) => {
      resolvers.push(resolve);
    }),
}));
const shown: string[][] = [];
vi.mock("../design/primitives/Histogram", () => ({
  Histogram: ({ buckets }: { buckets: Array<{ key: string }> }) => {
    shown.push(buckets.map((b) => b.key));
    return null;
  },
}));

import { createCrossFilterStore } from "../crossfilter/store";
import { HotspotHistogram } from "./HotspotHistogram";

afterEach(() => {
  cleanup();
  resolvers.length = 0;
  shown.length = 0;
});

const answer = (label: string): { target_id: Histogram } => ({
  target_id: { bucketing: "categorical", total: 1, buckets: [{ label, count: 1 }] },
});

describe("HotspotHistogram, answers out of order", () => {
  it("drops an older answer that arrives after a newer one", async () => {
    const crossFilterStore = createCrossFilterStore("http://api", "t", "inv-1");
    render(
      <HotspotHistogram
        apiBaseUrl="http://api"
        bearerToken="t"
        investigationScope="inv-1"
        crossFilterStore={crossFilterStore}
        getNodeIds={() => []}
        locationEdgeTypes={["PRESENT_AT"]}
      />,
    );
    await waitFor(() => expect(resolvers).toHaveLength(1));
    act(() => crossFilterStore.store.getState().setCells([{ weekday: 1, hour: 1 }]));
    await waitFor(() => expect(resolvers).toHaveLength(2));

    await act(async () => resolvers[1]!(answer("newer")));
    await act(async () => resolvers[0]!(answer("older")));

    expect(shown.at(-1)).toEqual(["newer"]);
    expect(shown.flat()).not.toContain("older");
  });
});
