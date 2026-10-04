// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  SIDE_PANEL_IDS,
  SIDE_PANEL_ORDER_KEY,
  forgetSidePanelOrderForTest,
  getSidePanelOrder,
  moveSidePanel,
  moveSidePanelTo,
  normaliseSidePanelOrder,
  onSidePanelOrderChange,
} from "./panelOrder";

// ADR-085. The order of the right-hand column's panels is a way of looking, so it is kept in this
// browser only (as the theme, labels and icons are), never sent to the server and not part of the case.

beforeEach(() => {
  localStorage.clear();
  forgetSidePanelOrderForTest();
});
afterEach(() => vi.restoreAllMocks());

describe("the default order", () => {
  it("is the Inspector, then the Metrics panel, then the Query builder, as ADR-082 laid them out", () => {
    expect(getSidePanelOrder()).toEqual(["inspector", "metrics", "query-builder"]);
    expect([...SIDE_PANEL_IDS]).toEqual(["inspector", "metrics", "query-builder"]);
  });
});

describe("moving a panel", () => {
  it("up swaps it with the one above and writes the order to storage", () => {
    moveSidePanel("metrics", "up");
    expect(getSidePanelOrder()).toEqual(["metrics", "inspector", "query-builder"]);
    expect(JSON.parse(localStorage.getItem(SIDE_PANEL_ORDER_KEY) ?? "null")).toEqual([
      "metrics",
      "inspector",
      "query-builder",
    ]);
  });

  it("down swaps it with the one below", () => {
    moveSidePanel("inspector", "down");
    expect(getSidePanelOrder()).toEqual(["metrics", "inspector", "query-builder"]);
  });

  it("at the end of the stack changes nothing and tells nobody", () => {
    const listener = vi.fn();
    onSidePanelOrderChange(listener);
    moveSidePanel("inspector", "up");
    moveSidePanel("query-builder", "down");
    expect(getSidePanelOrder()).toEqual(["inspector", "metrics", "query-builder"]);
    expect(listener).not.toHaveBeenCalled();
    expect(localStorage.getItem(SIDE_PANEL_ORDER_KEY)).toBeNull();
  });

  it("to another panel's place (a drop) puts it there and shifts the rest", () => {
    moveSidePanelTo("query-builder", "inspector");
    expect(getSidePanelOrder()).toEqual(["query-builder", "inspector", "metrics"]);
    moveSidePanelTo("query-builder", "metrics");
    expect(getSidePanelOrder()).toEqual(["inspector", "metrics", "query-builder"]);
  });

  it("tells a listener once per change, and the listener can stop", () => {
    const listener = vi.fn();
    const stop = onSidePanelOrderChange(listener);
    moveSidePanel("metrics", "up");
    expect(listener).toHaveBeenCalledTimes(1);
    stop();
    moveSidePanel("metrics", "down");
    expect(listener).toHaveBeenCalledTimes(1);
  });

  it("is read back from storage by a fresh page", () => {
    moveSidePanel("query-builder", "up");
    forgetSidePanelOrderForTest();
    expect(getSidePanelOrder()).toEqual(["inspector", "query-builder", "metrics"]);
  });
});

describe("a stored order can never lose or duplicate a panel", () => {
  it("drops an id the Glass does not know", () => {
    expect(normaliseSidePanelOrder(["metrics", "dossier", "inspector", "query-builder"])).toEqual([
      "metrics",
      "inspector",
      "query-builder",
    ]);
  });

  it("appends, in default order, any panel the stored list lacks", () => {
    expect(normaliseSidePanelOrder(["query-builder"])).toEqual(["query-builder", "inspector", "metrics"]);
  });

  it("keeps the first of a repeated id", () => {
    expect(normaliseSidePanelOrder(["metrics", "metrics", "inspector", "query-builder"])).toEqual([
      "metrics",
      "inspector",
      "query-builder",
    ]);
  });

  it("falls back to the default for anything that is not a list of strings", () => {
    for (const bad of [null, 42, "inspector", { inspector: 0 }, [1, 2, 3]]) {
      expect(normaliseSidePanelOrder(bad)).toEqual(["inspector", "metrics", "query-builder"]);
    }
  });

  it("reads damaged storage as the default rather than failing", () => {
    localStorage.setItem(SIDE_PANEL_ORDER_KEY, "{not json");
    expect(getSidePanelOrder()).toEqual(["inspector", "metrics", "query-builder"]);
  });

  it("keeps the order for this page when storage refuses to write", () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("QuotaExceededError");
    });
    moveSidePanel("metrics", "up");
    expect(getSidePanelOrder()).toEqual(["metrics", "inspector", "query-builder"]);
  });
});
