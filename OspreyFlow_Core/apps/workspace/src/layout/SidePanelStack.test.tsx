// @vitest-environment jsdom
import { cleanup, fireEvent, render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { SidePanelStack } from "./SidePanelStack";
import { forgetLayoutSizesForTest, getLayoutSizes } from "./layoutSizes";
import { forgetSidePanelOrderForTest, getSidePanelOrder, moveSidePanel } from "./panelOrder";

// ADR-085. The three panels of the right-hand column, each in a slot with a grip row: a drag handle
// and Move up / Move down buttons, which are the keyboard route (rule 13).

beforeEach(() => {
  localStorage.clear();
  forgetSidePanelOrderForTest();
  forgetLayoutSizesForTest();
});
afterEach(cleanup);

const panels = [
  { id: "inspector" as const, name: "Inspector", content: <p>Inspector body</p> },
  { id: "metrics" as const, name: "Metrics", content: <p>Metrics body</p> },
  { id: "query-builder" as const, name: "Query builder", content: <p>Query builder body</p> },
];

const slotsOf = (container: HTMLElement) =>
  Array.from(container.querySelectorAll("[data-panel-slot]")).map((el) => el.getAttribute("data-panel-slot"));

describe("SidePanelStack", () => {
  it("draws the panels in the stored order", () => {
    moveSidePanel("query-builder", "up");
    const { container } = render(<SidePanelStack panels={panels} />);
    expect(slotsOf(container)).toEqual(["inspector", "query-builder", "metrics"]);
  });

  it("Move down swaps a panel with the one below, on screen and in storage", () => {
    const { container, getByLabelText } = render(<SidePanelStack panels={panels} />);
    fireEvent.click(getByLabelText("Move the inspector down"));
    expect(slotsOf(container)).toEqual(["metrics", "inspector", "query-builder"]);
    expect(getSidePanelOrder()).toEqual(["metrics", "inspector", "query-builder"]);
  });

  it("the top panel's Move up is unavailable, changes nothing and keeps focus", () => {
    const { container, getByLabelText } = render(<SidePanelStack panels={panels} />);
    const up = getByLabelText("Move the inspector up");
    expect(up.getAttribute("aria-disabled")).toBe("true");
    up.focus();
    fireEvent.click(up);
    expect(slotsOf(container)).toEqual(["inspector", "metrics", "query-builder"]);
    expect(document.activeElement).toBe(up);
    expect(getByLabelText("Move the query builder down").getAttribute("aria-disabled")).toBe("true");
    expect(getByLabelText("Move the metrics up").getAttribute("aria-disabled")).toBe("false");
  });

  it("a panel moved to the top keeps focus on the button that moved it", () => {
    const { getByLabelText } = render(<SidePanelStack panels={panels} />);
    const up = getByLabelText("Move the metrics up");
    up.focus();
    fireEvent.click(up);
    expect(document.activeElement).toBe(getByLabelText("Move the metrics up"));
    expect(getByLabelText("Move the metrics up").getAttribute("aria-disabled")).toBe("true");
  });

  it("dropping a dragged handle on another panel's place puts the panel there", () => {
    const { container, getByLabelText } = render(<SidePanelStack panels={panels} />);
    const handle = getByLabelText("Drag to move the query builder");
    const target = container.querySelector('[data-panel-slot="inspector"]')!;
    fireEvent.dragStart(handle);
    fireEvent.dragOver(target);
    fireEvent.drop(target);
    expect(slotsOf(container)).toEqual(["query-builder", "inspector", "metrics"]);
    expect(getSidePanelOrder()).toEqual(["query-builder", "inspector", "metrics"]);
  });

  it("a drop with nothing dragged changes nothing", () => {
    const { container } = render(<SidePanelStack panels={panels} />);
    fireEvent.drop(container.querySelector('[data-panel-slot="metrics"]')!);
    expect(slotsOf(container)).toEqual(["inspector", "metrics", "query-builder"]);
  });

  it("a panel the view does not draw keeps its place in the order", () => {
    moveSidePanel("metrics", "up");
    const inspectorOnly = panels.filter((p) => p.id === "inspector");
    const { container, getByLabelText } = render(<SidePanelStack panels={inspectorOnly} />);
    expect(slotsOf(container)).toEqual(["inspector"]);
    // Alone on screen, it can go neither way.
    expect(getByLabelText("Move the inspector up").getAttribute("aria-disabled")).toBe("true");
    expect(getByLabelText("Move the inspector down").getAttribute("aria-disabled")).toBe("true");
    expect(getSidePanelOrder()).toEqual(["metrics", "inspector", "query-builder"]);
  });
});

// ADR-086: a sash below each stacked panel but the last sets that panel's height.
describe("SidePanelStack and its sashes (ADR-086)", () => {
  it("puts a sash between consecutive panels and none after the last", () => {
    const { getAllByRole, queryByRole } = render(<SidePanelStack panels={panels} />);
    const names = getAllByRole("separator").map((el) => el.getAttribute("aria-label"));
    expect(names).toEqual(["Resize the inspector", "Resize the metrics"]);
    expect(queryByRole("separator", { name: "Resize the query builder" })).toBeNull();
  });

  it("ArrowDown on a panel's sash gives it a height of its own, and Home lets it share again", () => {
    const { container, getByRole } = render(<SidePanelStack panels={panels} />);
    const slot = container.querySelector('[data-panel-slot="inspector"]') as HTMLElement;
    expect(slot.style.height).toBe("");
    fireEvent.keyDown(getByRole("separator", { name: "Resize the inspector" }), { key: "ArrowDown" });
    // Nothing is measured in this environment, so the height grows from the minimum.
    expect(slot.style.height).toBe("64px");
    expect(getLayoutSizes().panelHeights.inspector).toBe(64);
    fireEvent.keyDown(getByRole("separator", { name: "Resize the inspector" }), { key: "Home" });
    expect(slot.style.height).toBe("");
    expect(getLayoutSizes().panelHeights).toEqual({});
  });

  it("a stored height is applied on first draw", () => {
    localStorage.setItem("ospreyflow.layout-sizes", JSON.stringify({ panelHeights: { metrics: 180 } }));
    const { container } = render(<SidePanelStack panels={panels} />);
    expect((container.querySelector('[data-panel-slot="metrics"]') as HTMLElement).style.height).toBe("180px");
  });
});
