// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { RadialMenu, type RadialMenuItem } from "./RadialMenu";

/**
 * Seen 3 October 2026, in the running Glass: right-clicking a node drew the menu as a pile of
 * overlapping labels (the ring is 96 px across, the labels such as `COMMUNICATED_WITH (…)` are
 * wider), `(…)` that never resolved, and `View messages (0)` / `Mark for suppression (0)` whose
 * `0` was a fixed placeholder, not a count of anything.
 */

afterEach(cleanup);

function item(id: string, count: RadialMenuItem["count"]): RadialMenuItem {
  return { id, label: id, count, onSelect: vi.fn() };
}

function labels(): string[] {
  return screen.getAllByRole("menuitem").map((el) => el.textContent ?? "");
}

describe("what a menu entry says about its count", () => {
  it("shows a number when the preview answered", () => {
    render(
      <RadialMenu
        x={0}
        y={0}
        layout="list"
        onClose={() => {}}
        items={[item("USES", 8)]}
      />,
    );
    expect(labels()).toEqual(["USES (8)"]);
  });

  it("shows an ellipsis only while the answer is still awaited", () => {
    render(
      <RadialMenu
        x={0}
        y={0}
        layout="list"
        onClose={() => {}}
        items={[item("USES", null)]}
      />,
    );
    expect(labels()).toEqual(["USES (…)"]);
  });

  it("says the count is unavailable when the preview failed, never an endless ellipsis", () => {
    render(
      <RadialMenu
        x={0}
        y={0}
        layout="list"
        onClose={() => {}}
        items={[item("USES", "unavailable")]}
      />,
    );
    expect(labels()).toEqual(["USES (count unavailable)"]);
  });

  it("shows no figure at all for an action that has no count", () => {
    render(
      <RadialMenu
        x={0}
        y={0}
        layout="list"
        onClose={() => {}}
        items={[item("View messages", undefined)]}
      />,
    );
    expect(labels()).toEqual(["View messages"]);
  });
});

// Seen 3 October 2026 in the running Glass: after right-clicking a node the menu stayed on screen
// whatever was clicked, because it closed only on Escape or on choosing an item, unlike every other
// menu on the page (ADR-065: Escape, a click outside, focus leaving). It also never said which node
// it belonged to, so with two nodes in view the analyst could not tell whose menu it was.
describe("closing and naming the menu", () => {
  for (const layout of ["list", "radial"] as const) {
    it(`${layout}: a click outside closes it`, () => {
      const onClose = vi.fn();
      render(
        <div>
          <button type="button">elsewhere</button>
          <RadialMenu x={0} y={0} layout={layout} onClose={onClose} items={[item("USES", 3)]} />
        </div>,
      );
      fireEvent.mouseDown(screen.getByRole("button", { name: "elsewhere" }));
      expect(onClose).toHaveBeenCalledTimes(1);
    });

    it(`${layout}: a click on the menu itself does not close it`, () => {
      const onClose = vi.fn();
      render(<RadialMenu x={0} y={0} layout={layout} onClose={onClose} items={[item("USES", 3)]} />);
      fireEvent.mouseDown(screen.getByRole("menuitem"));
      expect(onClose).not.toHaveBeenCalled();
    });
  }

  it("says whose menu it is when it is given a title", () => {
    render(
      <RadialMenu
        x={0}
        y={0}
        layout="list"
        title="Endpoint: someone@example.test"
        onClose={() => {}}
        items={[item("USES", 3)]}
      />,
    );
    expect(screen.getByText("Endpoint: someone@example.test")).toBeTruthy();
    expect(screen.getByRole("menu").getAttribute("aria-label")).toBe(
      "Endpoint: someone@example.test",
    );
  });
});
