// @vitest-environment jsdom
// The owner's ruling of 14 November 2026 (spec 02 §2.0, `BAR_FOLD_ORDER`): what folds first when the top bar runs out
// of room, how a wrapped item is told from a one-line bar, and the place switcher folded into one menu. That the real
// bar folds and stays one line, in each look, is `keyboard/top-bar.spec.ts`'s, in a browser.
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { applyBrand } from "../brand/brand";
import { PlaceSwitcher } from "./PlaceSwitcher";
import { barWraps, foldSteps } from "./TopBar";

afterEach(() => {
  cleanup();
  applyBrand("ospreyflow");
});

const views = (...ids: string[]) => ids.map((id) => ({ id }));

describe("the fold order", () => {
  it("folds Build a report, then Reports, the Drawing board, the Map and Messages, then the places, Graph last", () => {
    expect(foldSteps(views("graph", "map", "boards", "dashboards", "dossier"), { places: true, buildAReport: true })).toEqual([
      "build-a-report", "dashboards", "boards", "map", "dossier", "places", "graph",
    ]);
  });

  it("folds only what the bar holds", () => {
    expect(foldSteps(views("graph", "map"), { places: false, buildAReport: false })).toEqual(["map", "graph"]);
  });

  it("folds a switch view the order does not name just before Graph (the built-in Administrator's)", () => {
    expect(foldSteps(views("strength"), { places: true, buildAReport: true })).toEqual(["build-a-report", "places", "strength"]);
    expect(foldSteps(views("graph", "matrix", "strength"), { places: false, buildAReport: false })).toEqual(["strength", "matrix", "graph"]);
  });
});

describe("a wrapped bar", () => {
  const bar = (boxes: Array<[top: number, height: number]>) => {
    const element = document.createElement("header");
    for (const [top, height] of boxes) {
      const child = document.createElement("div");
      child.getBoundingClientRect = () => ({ top, bottom: top + height, height, width: 10, left: 0, right: 10, x: 0, y: top, toJSON: () => ({}) });
      element.appendChild(child);
    }
    return element;
  };

  it("is one line when every item starts above the shortest one's bottom, however they are centred", () => {
    expect(barWraps(bar([[32, 20], [26, 32], [29, 26]]))).toBe(false);
  });

  it("wraps when an item starts at or below the shortest one's bottom", () => {
    expect(barWraps(bar([[32, 20], [26, 32], [60, 32]]))).toBe(true);
  });

  it("counts no item drawn with no size", () => {
    expect(barWraps(bar([[26, 32], [0, 0]]))).toBe(false);
  });
});

describe("the place switcher folded", () => {
  it("is one menu named by the place open, each place in it, the one open marked, a choice closing it", () => {
    const chose = vi.fn();
    render(<PlaceSwitcher places={["glass", "ingest", "rules"]} current="glass" onChoose={chose} counts={{ rules: 3 }} folded />);
    const nav = screen.getByRole("navigation", { name: "Places" });
    fireEvent.click(within(nav).getByRole("button", { name: /^The Glass/ }));
    const menu = screen.getByRole("group", { name: "Places" });
    expect(within(menu).getByRole("button", { name: "The Glass" }).getAttribute("aria-current")).toBe("page");
    expect(within(menu).getAllByRole("button").map((b) => b.textContent)).toEqual(["The Glass", "Ingest Studio", "Rules and Monitoring 3 open"]);
    fireEvent.click(within(menu).getByRole("button", { name: "Ingest Studio" }));
    expect(chose).toHaveBeenCalledWith("ingest");
    expect(screen.queryByRole("group", { name: "Places" })).toBeNull();
  });

  it("stays a list for one place, with nothing to choose between", () => {
    render(<PlaceSwitcher places={["glass"]} current="glass" onChoose={() => {}} folded />);
    expect(screen.queryByRole("button", { name: /▾/ })).toBeNull();
    expect(screen.getByRole("button", { name: "The Glass" }).getAttribute("aria-current")).toBe("page");
  });
});
