// @vitest-environment jsdom
import { cleanup, fireEvent, render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { forgetLayoutSizesForTest, getLayoutSizes } from "./layoutSizes";

import { BottomPanelFrame, SidePanelFrame } from "./PanelFrames";

afterEach(cleanup);

const mode = (el: HTMLElement) => el.querySelector("[data-panel-mode]")!.getAttribute("data-panel-mode");

describe("SidePanelFrame", () => {
  it("starts at its normal width with its contents shown", () => {
    const { container, getByText } = render(
      <SidePanelFrame name="Inspector">
        <p>Query builder</p>
      </SidePanelFrame>,
    );
    expect(mode(container)).toBe("normal");
    expect(getByText("Query builder")).toBeTruthy();
  });

  it("hides to a strip, keeps its contents mounted, and comes back", () => {
    const { container, getByLabelText, getByText } = render(
      <SidePanelFrame name="Inspector">
        <input aria-label="A half-typed query" defaultValue="" />
      </SidePanelFrame>,
    );
    const box = getByLabelText("A half-typed query") as HTMLInputElement;
    fireEvent.change(box, { target: { value: "person where age > 30" } });
    fireEvent.click(getByLabelText("Hide the inspector"));
    expect(mode(container)).toBe("collapsed");
    // Still in the page, with what was typed: hiding a panel loses nothing.
    expect((getByLabelText("A half-typed query") as HTMLInputElement).value).toBe("person where age > 30");
    fireEvent.click(getByLabelText("Show the inspector"));
    expect(mode(container)).toBe("normal");
    expect(getByText("Hide")).toBeTruthy();
  });

  it("opens to the full width and returns to its normal width", () => {
    const { container, getByLabelText } = render(
      <SidePanelFrame name="Inspector">
        <p>Contents</p>
      </SidePanelFrame>,
    );
    fireEvent.click(getByLabelText("Open the inspector to the full width"));
    expect(mode(container)).toBe("full");
    fireEvent.click(getByLabelText("Return the inspector to its normal width"));
    expect(mode(container)).toBe("normal");
  });

  it("can be hidden from the full width", () => {
    const { container, getByLabelText } = render(
      <SidePanelFrame name="Inspector" initialMode="full">
        <p>Contents</p>
      </SidePanelFrame>,
    );
    fireEvent.click(getByLabelText("Hide the inspector"));
    expect(mode(container)).toBe("collapsed");
  });
});

describe("BottomPanelFrame", () => {
  it("hides and shows its contents without unmounting them", () => {
    const { getByLabelText, getByText } = render(
      <BottomPanelFrame title="Timeline" height={252}>
        <p>Brush</p>
      </BottomPanelFrame>,
    );
    const button = getByLabelText("Hide the timeline");
    expect(button.getAttribute("aria-expanded")).toBe("true");
    fireEvent.click(button);
    expect(getByLabelText("Show the timeline").getAttribute("aria-expanded")).toBe("false");
    expect(getByText("Brush")).toBeTruthy();
    fireEvent.click(getByLabelText("Show the timeline"));
    expect(getByLabelText("Hide the timeline").getAttribute("aria-expanded")).toBe("true");
  });

  it("opens when told to, as Explore's busiest day does (ADR-100)", () => {
    const { getByLabelText, rerender } = render(
      <BottomPanelFrame title="Timeline" height={252} initiallyOpen={false} openSignal={0}>
        <p>Brush</p>
      </BottomPanelFrame>,
    );
    expect(getByLabelText("Show the timeline").getAttribute("aria-expanded")).toBe("false");
    rerender(
      <BottomPanelFrame title="Timeline" height={252} initiallyOpen={false} openSignal={1}>
        <p>Brush</p>
      </BottomPanelFrame>,
    );
    expect(getByLabelText("Hide the timeline").getAttribute("aria-expanded")).toBe("true");
  });
});

// ADR-086: a sash on the column's edge sets its width, and one above the timeline sets its height.
// Each is a keyboard-reachable separator; Home resets it. The sizes are kept in `layoutSizes`.
describe("the sashes (ADR-086)", () => {
  beforeEach(() => {
    localStorage.clear();
    forgetLayoutSizesForTest();
  });

  it("the side panel has a sash in its normal mode, and none when collapsed or full", () => {
    const { getByRole, getByLabelText, queryByRole } = render(
      <SidePanelFrame name="Inspector">
        <p>Contents</p>
      </SidePanelFrame>,
    );
    expect(getByRole("separator", { name: "Resize the side panel" })).toBeTruthy();
    fireEvent.click(getByLabelText("Hide the inspector"));
    expect(queryByRole("separator", { name: "Resize the side panel" })).toBeNull();
    fireEvent.click(getByLabelText("Show the inspector"));
    fireEvent.click(getByLabelText("Open the inspector to the full width"));
    expect(queryByRole("separator", { name: "Resize the side panel" })).toBeNull();
  });

  it("ArrowLeft on the side sash widens the column by a step, and Home returns it to 320", () => {
    const { container, getByRole } = render(
      <SidePanelFrame name="Inspector">
        <p>Contents</p>
      </SidePanelFrame>,
    );
    const frame = container.querySelector("[data-panel-mode]") as HTMLElement;
    expect(frame.style.width).toBe("320px");
    fireEvent.keyDown(getByRole("separator", { name: "Resize the side panel" }), { key: "ArrowLeft" });
    expect(frame.style.width).toBe("336px");
    expect(getLayoutSizes().sideWidth).toBe(336);
    fireEvent.keyDown(getByRole("separator", { name: "Resize the side panel" }), { key: "Home" });
    expect(frame.style.width).toBe("320px");
  });

  it("the timeline has a sash while shown; ArrowUp raises its height and hiding removes the sash", () => {
    const { getByRole, getByLabelText, queryByRole, getByText } = render(
      <BottomPanelFrame title="Timeline" height={252}>
        <p>Brush</p>
      </BottomPanelFrame>,
    );
    const body = getByText("Brush").parentElement as HTMLElement;
    expect(body.style.height).toBe("252px");
    fireEvent.keyDown(getByRole("separator", { name: "Resize the timeline" }), { key: "ArrowUp" });
    expect(body.style.height).toBe("268px");
    expect(getLayoutSizes().timelineHeight).toBe(268);
    fireEvent.click(getByLabelText("Hide the timeline"));
    expect(queryByRole("separator", { name: "Resize the timeline" })).toBeNull();
  });
});
