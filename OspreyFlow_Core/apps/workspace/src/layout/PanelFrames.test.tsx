// @vitest-environment jsdom
import { cleanup, fireEvent, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

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
});
