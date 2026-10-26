// @vitest-environment jsdom
// ADR-097 step 3 (design review item 13): the density strip's counts are whole numbers and its ticks
// are literal values, in mono. The chart paints to a canvas, so this reads the option the Timeline
// hands the chart library.
import { cleanup, fireEvent, render, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const setOption = vi.fn();
vi.mock("echarts/core", () => ({
  use: () => undefined,
  init: () => ({
    setOption,
    on: () => undefined,
    off: () => undefined,
    dispatchAction: () => undefined,
    resize: () => undefined,
    dispose: () => undefined,
    getOption: () => ({}),
  }),
}));
vi.mock("../analytics/api", () => ({
  fetchHistogram: async () => ({
    bucketing: "fixed_interval",
    buckets: [
      { start: "2026-01-01T00:00:00Z", end: "2026-01-02T00:00:00Z", count: 1 },
      { start: "2026-01-02T00:00:00Z", end: "2026-01-03T00:00:00Z", count: 2 },
    ],
    total: 3,
  }),
}));

import { createCrossFilterStore } from "../crossfilter/store";
import { Timeline } from "./Timeline";
import { currentTimelineSummary, forgetTimelineSummaryForTest } from "./timelineSummary";

afterEach(cleanup);

describe("Timeline's density strip", () => {
  it("counts in whole numbers, and sets every tick in mono", async () => {
    const store = createCrossFilterStore("http://test.invalid", "unused", "inv-1");
    render(
      <Timeline
        apiBaseUrl="http://test.invalid"
        bearerToken="unused"
        investigationScope="inv-1"
        crossFilterStore={store}
        getNodeIds={() => []}
      />,
    );
    await waitFor(() => expect(setOption).toHaveBeenCalled());
    const option = setOption.mock.calls.at(-1)![0] as {
      xAxis: { axisLabel: { fontFamily?: string }; data: string[] };
      yAxis: { minInterval?: number; axisLabel: { fontFamily?: string } };
    };
    expect(option.yAxis.minInterval).toBe(1);
    expect(option.yAxis.axisLabel.fontFamily).toMatch(/IBM Plex Mono/);
    expect(option.xAxis.axisLabel.fontFamily).toMatch(/IBM Plex Mono/);
    expect(option.xAxis.data).toEqual(["2026-01-01", "2026-01-02"]);
    // ADR-115 E4: the folded row draws the histogram the timeline itself read.
    expect(currentTimelineSummary()?.total).toBe(3);
    forgetTimelineSummaryForTest();
  });

  it("fills the brushed window translucently, so the bars within stay readable", async () => {
    // The owner, 9 October 2026: "selecting a portion of timeline should still let me see the
    // trends for the selected zone and not block it out" — an opaque surface fill hid the bars.
    const store = createCrossFilterStore("http://test.invalid", "unused", "inv-1");
    render(
      <Timeline
        apiBaseUrl="http://test.invalid"
        bearerToken="unused"
        investigationScope="inv-1"
        crossFilterStore={store}
        getNodeIds={() => []}
      />,
    );
    await waitFor(() => expect(setOption).toHaveBeenCalled());
    const option = setOption.mock.calls.at(-1)![0] as {
      brush: { brushStyle: { color: string } };
    };
    // An 8-digit hex: the fill carries its own alpha, never an opaque surface colour.
    expect(option.brush.brushStyle.color).toMatch(/^#[0-9a-fA-F]{6}[0-3][0-9a-fA-F]$/);
  });
});

// ADR-128 decision 2 (B3): with a window set the timeline offers Select what is lit, and says that
// undated links are not included.
describe("Timeline's Select what is lit", () => {
  function mount(onSelectLit?: () => void, withWindow = true) {
    const store = createCrossFilterStore("http://test.invalid", "unused", "inv-1");
    if (withWindow) {
      store.store
        .getState()
        .setWindow({ validFrom: "2026-01-01T00:00:00Z", validTo: "2026-01-02T00:00:00Z" });
    }
    return render(
      <Timeline
        apiBaseUrl="http://test.invalid"
        bearerToken="unused"
        investigationScope="inv-1"
        crossFilterStore={store}
        getNodeIds={() => []}
        onSelectLit={onSelectLit}
      />,
    );
  }

  it("offers the action with a window set, and runs it when chosen", async () => {
    const lit = vi.fn();
    const view = mount(lit);
    const button = await view.findByRole("button", { name: "Select what is lit" });
    expect(button.getAttribute("title")).toMatch(/undated links are not included/i);
    fireEvent.click(button);
    expect(lit).toHaveBeenCalledTimes(1);
  });

  it("offers nothing to light while no window is set", async () => {
    const view = mount(vi.fn(), false);
    await waitFor(() => expect(setOption).toHaveBeenCalled());
    expect(view.queryByRole("button", { name: "Select what is lit" })).toBeNull();
  });

  it("offers nothing where the surface has no canvas to select on", async () => {
    const view = mount(undefined);
    await waitFor(() => expect(setOption).toHaveBeenCalled());
    expect(view.queryByRole("button", { name: "Select what is lit" })).toBeNull();
  });
});

