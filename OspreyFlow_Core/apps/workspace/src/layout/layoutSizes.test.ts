// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  DEFAULT_SIDE_WIDTH,
  DEFAULT_TIMELINE_HEIGHT,
  LAYOUT_SIZES_KEY,
  MIN_PANEL_HEIGHT,
  MIN_SIDE_WIDTH,
  MIN_TIMELINE_HEIGHT,
  clamp,
  forgetLayoutSizesForTest,
  getLayoutSizes,
  normaliseLayoutSizes,
  onLayoutSizesChange,
  resetPanelHeight,
  resetSideWidth,
  resetTimelineHeight,
  setPanelHeight,
  setSideWidth,
  setTimelineHeight,
  MAX_SIDE_WIDTH,
} from "./layoutSizes";

// ADR-086. The sizes an analyst drags the sashes to: the right-hand column's width, each stacked
// panel's height and the timeline's height. Kept in this browser only, beside the panel order.

beforeEach(() => {
  localStorage.clear();
  forgetLayoutSizesForTest();
});
afterEach(() => vi.restoreAllMocks());

describe("the defaults", () => {
  it("are ADR-082's sizes with no panel height set", () => {
    expect(getLayoutSizes()).toEqual({
      sideWidth: DEFAULT_SIDE_WIDTH,
      timelineHeight: DEFAULT_TIMELINE_HEIGHT,
      panelHeights: {},
    });
    // DESIGN.md v0.3 §5a (ADR-115 decision 9): 340 by default, resizable from 300 to 480.
    expect([DEFAULT_SIDE_WIDTH, MIN_SIDE_WIDTH, MAX_SIDE_WIDTH]).toEqual([340, 300, 480]);
    expect(DEFAULT_TIMELINE_HEIGHT).toBe(252);
  });
});

describe("the column's width (DESIGN.md §5a)", () => {
  it("is held within 300 to 480 when set and when read back", () => {
    setSideWidth(900);
    expect(getLayoutSizes().sideWidth).toBe(480);
    setSideWidth(100);
    expect(getLayoutSizes().sideWidth).toBe(300);
    expect(normaliseLayoutSizes({ sideWidth: 1200 }).sideWidth).toBe(480);
  });
});

describe("setting a size", () => {
  it("writes the column width to storage and tells a listener", () => {
    const listener = vi.fn();
    onLayoutSizesChange(listener);
    setSideWidth(400);
    expect(getLayoutSizes().sideWidth).toBe(400);
    expect(JSON.parse(localStorage.getItem(LAYOUT_SIZES_KEY) ?? "null").sideWidth).toBe(400);
    expect(listener).toHaveBeenCalledTimes(1);
  });

  it("never goes below the minimums", () => {
    setSideWidth(10);
    setTimelineHeight(10);
    setPanelHeight("metrics", 1);
    expect(getLayoutSizes().sideWidth).toBe(MIN_SIDE_WIDTH);
    expect(getLayoutSizes().timelineHeight).toBe(MIN_TIMELINE_HEIGHT);
    expect(getLayoutSizes().panelHeights.metrics).toBe(MIN_PANEL_HEIGHT);
  });

  it("rounds to whole pixels and ignores a size that is not a number", () => {
    setSideWidth(333.6);
    expect(getLayoutSizes().sideWidth).toBe(334);
    setSideWidth(Number.NaN);
    expect(getLayoutSizes().sideWidth).toBe(334);
  });

  it("changes nothing and tells nobody when the size is the one already held", () => {
    const listener = vi.fn();
    onLayoutSizesChange(listener);
    setSideWidth(DEFAULT_SIDE_WIDTH);
    expect(listener).not.toHaveBeenCalled();
    expect(localStorage.getItem(LAYOUT_SIZES_KEY)).toBeNull();
  });

  it("resets each size on its own", () => {
    setSideWidth(400);
    setTimelineHeight(300);
    setPanelHeight("inspector", 200);
    resetSideWidth();
    expect(getLayoutSizes().sideWidth).toBe(DEFAULT_SIDE_WIDTH);
    expect(getLayoutSizes().timelineHeight).toBe(300);
    resetTimelineHeight();
    expect(getLayoutSizes().timelineHeight).toBe(DEFAULT_TIMELINE_HEIGHT);
    expect(getLayoutSizes().panelHeights).toEqual({ inspector: 200 });
    resetPanelHeight("inspector");
    expect(getLayoutSizes().panelHeights).toEqual({});
  });

  it("is read back from storage by a fresh page", () => {
    setSideWidth(400);
    setPanelHeight("metrics", 180);
    forgetLayoutSizesForTest();
    expect(getLayoutSizes()).toEqual({ sideWidth: 400, timelineHeight: DEFAULT_TIMELINE_HEIGHT, panelHeights: { metrics: 180 } });
  });
});

describe("a stored value can never break the layout", () => {
  it("falls back to the defaults for anything that is not an object", () => {
    for (const bad of [null, 7, "wide", [320]]) {
      expect(normaliseLayoutSizes(bad)).toEqual(getLayoutSizes());
    }
  });

  it("keeps the good fields and drops the bad ones", () => {
    expect(
      normaliseLayoutSizes({ sideWidth: "400", timelineHeight: 300, panelHeights: { metrics: 180, dossier: 50, inspector: "x" } }),
    ).toEqual({ sideWidth: DEFAULT_SIDE_WIDTH, timelineHeight: 300, panelHeights: { metrics: 180 } });
  });

  it("clamps a stored size below a minimum up to it", () => {
    expect(normaliseLayoutSizes({ sideWidth: 5 }).sideWidth).toBe(MIN_SIDE_WIDTH);
  });

  it("reads damaged storage as the defaults", () => {
    localStorage.setItem(LAYOUT_SIZES_KEY, "{oops");
    expect(getLayoutSizes().sideWidth).toBe(DEFAULT_SIDE_WIDTH);
  });
});

describe("clamp", () => {
  it("holds a value between its bounds, and to the minimum when the bounds cross", () => {
    expect(clamp(50, 10, 100)).toBe(50);
    expect(clamp(5, 10, 100)).toBe(10);
    expect(clamp(500, 10, 100)).toBe(100);
    expect(clamp(50, 100, 10)).toBe(100);
  });
});
