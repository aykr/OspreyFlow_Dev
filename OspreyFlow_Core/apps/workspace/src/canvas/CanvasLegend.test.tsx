// @vitest-environment jsdom
import { cleanup, fireEvent, render } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it } from "vitest";

afterEach(() => {
  cleanup();
  localStorage.clear();
});

// jsdom has no PointerEvent, so the testing library would fire a bare Event with no coordinates; a
// MouseEvent carries `clientX`/`clientY` (as the sash's own tests do).
beforeAll(() => {
  if (typeof window.PointerEvent === "undefined") {
    (window as unknown as { PointerEvent: typeof MouseEvent }).PointerEvent = MouseEvent;
  }
});

import { CanvasLegend } from "./CanvasLegend";

// ADR-097 step 2, design review item 10: a legend of the types present, as the canvas draws them.
describe("CanvasLegend", () => {
  const types = [
    { type: "Person", count: 12, visual: { channel: "indigo", shape: "circle", icon: null } as const },
    { type: "Phone", count: 3, visual: { channel: "cyan", shape: "hexagon", icon: null } as const },
  ];

  it("lists each type in view with its count, most first", () => {
    const { getByRole } = render(<CanvasLegend types={types} />);
    const list = getByRole("list", { name: "Types in view" });
    const rows = Array.from(list.querySelectorAll("li")).map((li) => li.textContent);
    expect(rows).toEqual(["Person12", "Phone3"]);
    expect(list.querySelectorAll("img")).toHaveLength(2);
  });

  it("folds and opens from its own button, keeping the list in the page", () => {
    const { container, getByRole } = render(<CanvasLegend types={types} />);
    const toggle = getByRole("button", { name: "Legend" });
    expect(toggle.getAttribute("aria-expanded")).toBe("true");
    fireEvent.click(toggle);
    expect(toggle.getAttribute("aria-expanded")).toBe("false");
    const list = container.querySelector<HTMLUListElement>('ul[aria-label="Types in view"]');
    expect(list?.hidden).toBe(true);
  });

  // The owner, 14 October 2026: "the legend is hiding the button behind, can the legend panel be a
  // floating panel". It moves by its grip — dragged, or by keyboard — and stays where it was put.
  const offset = (el: Element | null) => (el as HTMLElement | null)?.style.transform ?? "";

  it("moves by keyboard from its grip: arrows by 16px, Shift by 64px, Home puts it back", () => {
    const { container, getByRole } = render(<CanvasLegend types={types} />);
    const legend = container.querySelector(".canvas-legend");
    const grip = getByRole("button", { name: "Move legend" });
    fireEvent.keyDown(grip, { key: "ArrowLeft" });
    expect(offset(legend)).toBe("translate(-16px, 0px)");
    fireEvent.keyDown(grip, { key: "ArrowDown", shiftKey: true });
    expect(offset(legend)).toBe("translate(-16px, 64px)");
    fireEvent.keyDown(grip, { key: "Home" });
    expect(offset(legend)).toBe("");
  });

  it("is dragged by its grip", () => {
    const { container, getByRole } = render(<CanvasLegend types={types} />);
    const grip = getByRole("button", { name: "Move legend" });
    fireEvent.pointerDown(grip, { clientX: 100, clientY: 100, pointerId: 1, button: 0 });
    fireEvent.pointerMove(grip, { clientX: 40, clientY: 130, pointerId: 1 });
    fireEvent.pointerUp(grip, { clientX: 40, clientY: 130, pointerId: 1 });
    expect(offset(container.querySelector(".canvas-legend"))).toBe("translate(-60px, 30px)");
  });

  it("stays where it was put, in this browser", () => {
    const first = render(<CanvasLegend types={types} />);
    fireEvent.keyDown(first.getByRole("button", { name: "Move legend" }), { key: "ArrowDown" });
    first.unmount();
    const { container } = render(<CanvasLegend types={types} />);
    expect(offset(container.querySelector(".canvas-legend"))).toBe("translate(0px, 16px)");
  });

  it("never rises above where it docks, just below the toolbar, so it cannot cover it", () => {
    const { container, getByRole } = render(<CanvasLegend types={types} />);
    const grip = getByRole("button", { name: "Move legend" });
    fireEvent.keyDown(grip, { key: "ArrowUp", shiftKey: true });
    expect(offset(container.querySelector(".canvas-legend"))).toBe("");
    fireEvent.pointerDown(grip, { clientX: 100, clientY: 100, pointerId: 1, button: 0 });
    fireEvent.pointerMove(grip, { clientX: 100, clientY: 20, pointerId: 1 });
    fireEvent.pointerUp(grip, { clientX: 100, clientY: 20, pointerId: 1 });
    expect(offset(container.querySelector(".canvas-legend"))).toBe("");
  });

  it("is not drawn for an empty view", () => {
    const { container } = render(<CanvasLegend types={[]} />);
    expect(container.textContent).toBe("");
  });
});

// ADR-117: the links in view, each in its colour, each one left out of the view or brought back.
describe("CanvasLegend's links", () => {
  const types = [{ type: "Person", count: 4, visual: { channel: "indigo", shape: "circle", icon: null } as const }];
  const links = [
    { type: "VISITED", label: "Visited", count: 2, colour: "violet", shown: true },
    { type: "SHARED_CELL_WITH", label: "Shared a cell with", count: 9, colour: "ochre", shown: false },
    { type: "KNOWS", label: "Knows", count: 1, colour: "not-a-channel", shown: true },
  ];

  it("lists each link type with its count, most first, and whether it is shown", () => {
    const { getByRole } = render(<CanvasLegend types={types} links={links} onToggleLink={() => {}} />);
    const list = getByRole("list", { name: "Links in view" });
    const rows = Array.from(list.querySelectorAll("li")).map((li) => li.textContent);
    expect(rows).toEqual(["Shared a cell with9", "Visited2", "Knows1"]);
    expect((getByRole("checkbox", { name: "Shared a cell with" }) as HTMLInputElement).checked).toBe(false);
    expect((getByRole("checkbox", { name: "Visited" }) as HTMLInputElement).checked).toBe(true);
  });

  it("asks for a type to be left out or brought back when its box is changed", () => {
    const asked: string[] = [];
    const { getByRole } = render(
      <CanvasLegend types={types} links={links} onToggleLink={(type) => asked.push(type)} />,
    );
    fireEvent.click(getByRole("checkbox", { name: "Visited" }));
    fireEvent.click(getByRole("checkbox", { name: "Shared a cell with" }));
    expect(asked).toEqual(["VISITED", "SHARED_CELL_WITH"]);
  });

  it("draws a type's colour from the tokens only, and the ordinary line for any other name", () => {
    const { getByRole } = render(<CanvasLegend types={types} links={links} onToggleLink={() => {}} />);
    const swatchOf = (name: string) =>
      (getByRole("checkbox", { name }).parentElement?.querySelector(".canvas-legend__swatch") as HTMLElement)
        .style.background;
    expect(swatchOf("Visited")).toBe("var(--ch-violet)");
    expect(swatchOf("Knows")).toBe("var(--border-strong)");
  });

  it("shows no links list when there are no links in view", () => {
    const { queryByRole } = render(<CanvasLegend types={types} links={[]} />);
    expect(queryByRole("list", { name: "Links in view" })).toBeNull();
  });
});
