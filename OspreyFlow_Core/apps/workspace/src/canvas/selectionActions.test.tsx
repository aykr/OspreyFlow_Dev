// @vitest-environment jsdom
// ADR-078 Amendment 1: the right-click menu offers the selection's actions in the bar's own words and
// order, on the bar's own conditions. Read from the rendered bar, not from the shared table, so a bar
// that stopped using the table would fail here.
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SelectionBar, type SelectionBarProps } from "./SelectionBar";
import { selectionMenuItems } from "./selectionActions";

function barWords(props: SelectionBarProps): string[] {
  const { unmount } = render(<SelectionBar {...props} />);
  const bar = screen.getByRole("toolbar", { name: "Selection" });
  const words = within(bar)
    .getAllByRole("button")
    .filter((b) => !b.closest("[role='group']")) // the stepper's − and + are the bar's degree, not actions
    .map((b) => (b.textContent ?? "").replace(/\s*Esc$/, "").trim());
  unmount();
  return words;
}

afterEach(cleanup);

const all = (count: number): SelectionBarProps => ({
  count,
  onExpand: vi.fn(),
  onLinksAmong: vi.fn(),
  onAsk: vi.fn(),
  onSaveView: vi.fn(),
  onRemove: vi.fn(),
  onClear: vi.fn(),
  litNote: "Selected what is lit",
  onUndoLit: vi.fn(),
});

describe("the selection's actions in the right-click menu", () => {
  it.each([
    ["two selected, every action offered", all(2)],
    ["one selected: no Show links", all(1)],
    ["in a view: what changes the case is absent", { count: 3, onSaveView: vi.fn(), onAsk: vi.fn(), onClear: vi.fn() }],
    ["no Document selected: Ask still offered (ADR-098 Amendment 7)", all(2)],
    ["no Select what is lit: no undo", { ...all(2), litNote: undefined }],
  ])("are the bar's own, in its words and order: %s", (_name, props) => {
    expect(selectionMenuItems(props).map((i) => i.label)).toEqual(barWords(props));
  });

  it("each acts as the bar's button does", () => {
    const props = all(2);
    const items = selectionMenuItems(props);
    for (const item of items) item.onSelect();
    expect(props.onExpand).toHaveBeenCalledTimes(1);
    expect(props.onLinksAmong).toHaveBeenCalledWith(1); // direct, as the bar reads until its stepper moves
    for (const handler of [props.onAsk, props.onSaveView, props.onRemove, props.onClear, props.onUndoLit])
      expect(handler).toHaveBeenCalledTimes(1);
  });

  it("is empty with nothing selected", () => {
    expect(selectionMenuItems({ count: 0, onClear: vi.fn() })).toEqual([]);
  });

  it("clicking the bar's button and the menu's entry reach the same handler", () => {
    const props = all(2);
    render(<SelectionBar {...props} />);
    fireEvent.click(screen.getByRole("button", { name: "Save as a view" }));
    selectionMenuItems(props).find((i) => i.label === "Save as a view")?.onSelect();
    expect(props.onSaveView).toHaveBeenCalledTimes(2);
  });
});

// The orchestrator's ruling (Part C, one set of actions): the same words do the same thing, so the menu's
// Show links looks as far as the bar's stepper says, one source of state.
import { useState } from "react";

function BarAndMenu({ onLinksAmong }: { onLinksAmong: (degree: number) => void }) {
  const [degree, setDegree] = useState(1);
  const props: SelectionBarProps = { count: 3, onLinksAmong, degree, onDegreeChange: setDegree, onClear: () => {} };
  return (
    <>
      <SelectionBar {...props} />
      <button type="button" onClick={() => selectionMenuItems(props).find((i) => i.label === "Show links")?.onSelect()}>
        the menu's Show links
      </button>
    </>
  );
}

describe("the menu's Show links and the bar's stepper", () => {
  it("looks as far as the stepper says, moved or not", () => {
    const linksAmong = vi.fn();
    render(<BarAndMenu onLinksAmong={linksAmong} />);
    fireEvent.click(screen.getByRole("button", { name: "the menu's Show links" }));
    expect(linksAmong).toHaveBeenLastCalledWith(1);
    fireEvent.click(screen.getByRole("button", { name: "More degrees" }));
    fireEvent.click(screen.getByRole("button", { name: "More degrees" }));
    fireEvent.click(screen.getByRole("button", { name: "the menu's Show links" }));
    expect(linksAmong).toHaveBeenLastCalledWith(3);
    fireEvent.click(screen.getByRole("button", { name: "Show links among these" }));
    expect(linksAmong).toHaveBeenLastCalledWith(3); // the bar's own, the same
  });

  it("looks for direct links where the bar does, above the routes' limit of selected nodes", () => {
    const linksAmong = vi.fn();
    const props: SelectionBarProps = { count: 12, onLinksAmong: linksAmong, degree: 4, onDegreeChange: () => {}, onClear: () => {} };
    selectionMenuItems(props).find((i) => i.label === "Show links")?.onSelect();
    expect(linksAmong).toHaveBeenLastCalledWith(1);
  });
});
