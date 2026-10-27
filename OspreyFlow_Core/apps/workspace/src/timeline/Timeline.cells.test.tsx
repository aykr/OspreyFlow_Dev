// @vitest-environment jsdom
// ADR-130 decision 2: the weekly view's "Choose cells" control sits in its own options menu, and the
// chart's brush listener is registered for the weekly view and taken off for the density one.
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const setOption = vi.fn();
const on = vi.fn();
const off = vi.fn();
vi.mock("echarts/core", () => ({
  use: () => undefined,
  init: () => ({
    setOption,
    on,
    off,
    dispatchAction: () => undefined,
    resize: () => undefined,
    dispose: () => undefined,
    getOption: () => ({}),
  }),
}));
vi.mock("../analytics/api", () => ({
  fetchHistogram: async (_u: string, _t: string, request: { bucketing: string }) =>
    request.bucketing === "weekday_hour"
      ? { bucketing: "weekday_hour", buckets: [{ weekday: 5, hour: 9, count: 2 }], total: 2 }
      : {
          bucketing: "fixed_interval",
          buckets: [{ start: "2026-01-01T00:00:00Z", end: "2026-01-02T00:00:00Z", count: 1 }],
          total: 1,
        },
  fetchCaseEvents: async () => ({}),
  fetchFirstSeen: async () => ({ nodes: {}, edges: {} }),
}));

import { createCrossFilterStore } from "../crossfilter/store";
import { Timeline } from "./Timeline";

afterEach(() => {
  cleanup();
  on.mockClear();
  off.mockClear();
  setOption.mockClear();
});

function mount() {
  const store = createCrossFilterStore("http://test.invalid", "unused", "inv-1");
  render(
    <Timeline
      apiBaseUrl="http://test.invalid"
      bearerToken="unused"
      investigationScope="inv-1"
      crossFilterStore={store}
      getNodeIds={() => ["a"]}
    />,
  );
  return store;
}

describe("the weekly view's Choose cells control", () => {
  it("is in the options menu in the weekly view and not in the density view", async () => {
    mount();
    await waitFor(() => expect(setOption).toHaveBeenCalled());
    fireEvent.click(screen.getByRole("button", { name: "More timeline options" }));
    expect(screen.queryByRole("group", { name: "Choose cells (UTC)" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Cyclical" }));
    await waitFor(() => expect(screen.getByRole("group", { name: "Choose cells (UTC)" })).toBeTruthy());
    for (const day of ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]) {
      expect(screen.getByRole("checkbox", { name: day })).toBeTruthy();
    }
    expect(screen.getByRole("spinbutton", { name: "From hour" })).toBeTruthy();
    expect(screen.getByRole("spinbutton", { name: "To hour" })).toBeTruthy();
  });

  it("Weekend sets Saturday and Sunday, every hour, in the store; Clear takes them off", async () => {
    const store = mount();
    fireEvent.click(screen.getByRole("button", { name: "Cyclical" }));
    fireEvent.click(await screen.findByRole("button", { name: "More timeline options" }));
    fireEvent.click(await screen.findByRole("button", { name: "Weekend" }));
    const cells = store.store.getState().cells!;
    expect(cells).toHaveLength(48);
    expect(new Set(cells.map((c) => c.weekday))).toEqual(new Set([5, 6]));
    expect((screen.getByRole("checkbox", { name: "Sat" }) as HTMLInputElement).checked).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "Clear" }));
    expect(store.store.getState().cells).toBeNull();
    expect((screen.getByRole("checkbox", { name: "Sat" }) as HTMLInputElement).checked).toBe(false);
  });

  it("registers a brush listener for the weekly view, and takes the density one off on entering it", async () => {
    mount();
    await waitFor(() => expect(on).toHaveBeenCalledWith("brushEnd", expect.any(Function)));
    on.mockClear();
    off.mockClear();
    fireEvent.click(screen.getByRole("button", { name: "Cyclical" }));
    await waitFor(() => expect(on).toHaveBeenCalledWith("brushEnd", expect.any(Function)));
    expect(off).toHaveBeenCalledWith("brushEnd");
    expect(off).toHaveBeenCalledWith("datazoom");
  });

  it("a dragged rectangle on the grid chooses its cells", async () => {
    const store = mount();
    await waitFor(() => expect(on).toHaveBeenCalledWith("brushEnd", expect.any(Function)));
    on.mockClear();
    fireEvent.click(screen.getByRole("button", { name: "Cyclical" }));
    await waitFor(() => expect(on).toHaveBeenCalledWith("brushEnd", expect.any(Function)));
    const handler = on.mock.calls.filter((c) => c[0] === "brushEnd").at(-1)![1] as (p: unknown) => void;
    handler({ areas: [{ coordRange: [[8.6, 10.2], [4.8, 6.1]] }] });
    expect(store.store.getState().cells).toHaveLength(4);
  });

  it("a drag sets the hours boxes from the dragged range too, not only the days", async () => {
    mount();
    await waitFor(() => expect(on).toHaveBeenCalledWith("brushEnd", expect.any(Function)));
    on.mockClear();
    fireEvent.click(screen.getByRole("button", { name: "Cyclical" }));
    await waitFor(() => expect(on).toHaveBeenCalledWith("brushEnd", expect.any(Function)));
    const handler = on.mock.calls.filter((c) => c[0] === "brushEnd").at(-1)![1] as (p: unknown) => void;
    act(() => handler({ areas: [{ coordRange: [[8.6, 10.2], [4.8, 6.1]] }] }));
    fireEvent.click(screen.getByRole("button", { name: "More timeline options" }));
    expect((screen.getByRole("spinbutton", { name: "From hour" }) as HTMLInputElement).value).toBe("9");
    expect((screen.getByRole("spinbutton", { name: "To hour" }) as HTMLInputElement).value).toBe("10");
  });

  it("a clear elsewhere resets the hours as well as the days", async () => {
    const store = mount();
    fireEvent.click(screen.getByRole("button", { name: "Cyclical" }));
    fireEvent.click(await screen.findByRole("button", { name: "More timeline options" }));
    fireEvent.change(await screen.findByRole("spinbutton", { name: "From hour" }), { target: { value: "6" } });
    fireEvent.change(screen.getByRole("spinbutton", { name: "To hour" }), { target: { value: "12" } });
    fireEvent.click(screen.getByRole("checkbox", { name: "Mon" }));
    act(() => store.store.getState().clearFilter());
    expect((screen.getByRole("spinbutton", { name: "From hour" }) as HTMLInputElement).value).toBe("0");
    expect((screen.getByRole("spinbutton", { name: "To hour" }) as HTMLInputElement).value).toBe("23");
    expect((screen.getByRole("checkbox", { name: "Mon" }) as HTMLInputElement).checked).toBe(false);
  });

  it("labels the control and the grid as UTC", async () => {
    mount();
    fireEvent.click(screen.getByRole("button", { name: "Cyclical" }));
    fireEvent.click(await screen.findByRole("button", { name: "More timeline options" }));
    expect(await screen.findByText("Hours (UTC)")).toBeTruthy();
    await waitFor(() => {
      const option = setOption.mock.calls.at(-1)![0] as { xAxis?: { name?: string } };
      expect(option.xAxis?.name).toBe("Hour (UTC)");
    });
  });
});
