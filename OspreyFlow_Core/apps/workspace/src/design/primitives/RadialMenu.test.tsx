// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { pressEscapeOnAppear } from "../../testing/actOnAppear";
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

// 3 October 2026, the owner: the right-click menu "looks very cluttered". It was one flat list of
// relationship types and actions, each with its count run on after the name. ADR-078: the entries are
// grouped under a heading, each count is its own muted element at the right edge, and the order in
// which a keyboard user reaches the entries does not change.
describe("the tidy list", () => {
  function grouped(id: string, group: string, count: RadialMenuItem["count"] = undefined): RadialMenuItem {
    return { id, label: id, count, group, onSelect: vi.fn() };
  }

  it("puts each group's entries under its own heading, in the order given", () => {
    render(
      <RadialMenu
        x={0}
        y={0}
        layout="list"
        onClose={() => {}}
        items={[
          grouped("ASSOCIATE_OF", "Show links", 4),
          grouped("USES", "Show links", 2),
          grouped("Mark for suppression", "Actions"),
        ]}
      />,
    );
    const groups = screen.getAllByRole("group");
    expect(groups.map((g) => g.getAttribute("aria-label"))).toEqual(["Show links", "Actions"]);
    expect(Array.from(groups[0]!.querySelectorAll("[role='menuitem']")).map((e) => e.textContent)).toEqual([
      "ASSOCIATE_OF (4)",
      "USES (2)",
    ]);
    expect(labels()).toEqual(["ASSOCIATE_OF (4)", "USES (2)", "Mark for suppression"]);
    expect(screen.getByText("Show links").getAttribute("aria-hidden")).toBe("true");
  });

  it("draws a count as its own element, so it can sit at the right edge", () => {
    render(
      <RadialMenu x={0} y={0} layout="list" onClose={() => {}} items={[grouped("USES", "Show links", 8)]} />,
    );
    const count = screen.getByRole("menuitem").querySelector(".radial-menu__count");
    expect(count?.textContent?.trim()).toBe("(8)");
  });

  it("draws no group when no entry names one", () => {
    render(<RadialMenu x={0} y={0} layout="list" onClose={() => {}} items={[item("USES", 3)]} />);
    expect(screen.queryAllByRole("group")).toHaveLength(0);
  });
});

// Escape is heard from the moment it can be seen: a listener added in a passive effect missed an
// Escape pressed as it appeared on a slow machine (`Popover`, CI keyboard walkthroughs, 20 October 2026).
it("closes on an Escape pressed as soon as it is in the page", async () => {
  let closed = 0;
  await pressEscapeOnAppear(
    <RadialMenu x={0} y={0} layout="list" onClose={() => (closed += 1)} items={[item("expand", 3)]} />,
    "[role='menu']",
  );
  expect(closed).toBe(1);
});

// ADR-078 Amendment 1 (the owner's Part C, 13 November 2026): every action is reachable by keyboard,
// the menu never opens over the bottom bar, and a fold line opens in place.
describe("moving through the menu by keyboard", () => {
  const items = () => [item("first", undefined), item("second", undefined), item("third", undefined)];
  const focusedText = () => (document.activeElement?.textContent ?? "").trim();

  it.each(["list", "radial"] as const)("arrows step through the entries and wrap, in the %s layout", (layout) => {
    render(<RadialMenu x={0} y={0} layout={layout} onClose={() => {}} items={items()} />);
    const menu = screen.getByRole("menu");
    expect(focusedText()).toBe("first");
    fireEvent.keyDown(menu, { key: "ArrowDown" });
    expect(focusedText()).toBe("second");
    fireEvent.keyDown(menu, { key: "ArrowUp" });
    fireEvent.keyDown(menu, { key: "ArrowUp" });
    expect(focusedText()).toBe("third");
    fireEvent.keyDown(menu, { key: "ArrowDown" });
    expect(focusedText()).toBe("first");
  });

  it("Home and End go to the first and last entries", () => {
    render(<RadialMenu x={0} y={0} layout="list" onClose={() => {}} items={items()} />);
    const menu = screen.getByRole("menu");
    fireEvent.keyDown(menu, { key: "End" });
    expect(focusedText()).toBe("third");
    fireEvent.keyDown(menu, { key: "Home" });
    expect(focusedText()).toBe("first");
  });

  it("Enter on the focused entry acts and closes", () => {
    const close = vi.fn();
    const list = items();
    render(<RadialMenu x={0} y={0} layout="list" onClose={close} items={list} />);
    fireEvent.keyDown(screen.getByRole("menu"), { key: "ArrowDown" });
    fireEvent.click(document.activeElement as HTMLElement);
    expect(list[1]?.onSelect).toHaveBeenCalledTimes(1);
    expect(close).toHaveBeenCalledTimes(1);
  });
});

describe("an entry that keeps the menu open", () => {
  it("acts without closing, and focus stays in the menu", () => {
    const close = vi.fn();
    const fold: RadialMenuItem = { id: "fold", label: "7 types with no links", count: undefined, onSelect: vi.fn(), keepsOpen: true };
    render(<RadialMenu x={0} y={0} layout="list" onClose={close} items={[fold, item("other", undefined)]} />);
    fireEvent.click(screen.getByRole("menuitem", { name: "7 types with no links" }));
    expect(fold.onSelect).toHaveBeenCalledTimes(1);
    expect(close).not.toHaveBeenCalled();
    expect(screen.getByRole("menu").contains(document.activeElement)).toBe(true);
  });
});

describe("when the entries change under the keyboard", () => {
  it("keeps focus in the menu when the focused entry goes", () => {
    const { rerender } = render(
      <RadialMenu x={0} y={0} layout="list" onClose={() => {}} items={[item("a", undefined), item("b", undefined)]} />,
    );
    fireEvent.keyDown(screen.getByRole("menu"), { key: "End" });
    expect(document.activeElement?.textContent).toBe("b");
    rerender(<RadialMenu x={0} y={0} layout="list" onClose={() => {}} items={[item("a", undefined)]} />);
    expect(screen.getByRole("menu").contains(document.activeElement)).toBe(true);
    fireEvent.keyDown(screen.getByRole("menu"), { key: "End" });
    expect(document.activeElement?.textContent).toBe("a");
  });
});

describe("when an entry is replaced by another, the count of entries the same", () => {
  it("keeps focus in the menu", () => {
    const { rerender } = render(
      <RadialMenu x={0} y={0} layout="list" onClose={() => {}} items={[item("a", undefined), item("USES", 0)]} />,
    );
    fireEvent.keyDown(screen.getByRole("menu"), { key: "End" });
    expect(document.activeElement?.textContent).toBe("USES (0)");
    rerender(<RadialMenu x={0} y={0} layout="list" onClose={() => {}} items={[item("a", undefined), item("1 type with no links", undefined)]} />);
    expect(screen.getByRole("menu").contains(document.activeElement)).toBe(true);
  });
});

describe("keeping clear of the bottom bar", () => {
  function rect(top: number, height: number): DOMRect {
    return { top, bottom: top + height, left: 0, right: 200, width: 200, height, x: 0, y: top, toJSON: () => ({}) } as DOMRect;
  }

  it("moves up so its last entry sits above what it must not cover", () => {
    const spy = vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(function (this: HTMLElement) {
      return this.getAttribute("role") === "menu" ? rect(Number.parseFloat(this.style.top), 300) : rect(0, 0);
    });
    render(<RadialMenu x={40} y={500} layout="list" onClose={() => {}} items={[item("a", undefined)]} keepAbove={() => 600} />);
    expect(Number.parseFloat(screen.getByRole("menu").style.top)).toBeLessThanOrEqual(600 - 300);
    spy.mockRestore();
  });

  it("in the radial layout, keeps the ring's lowest entry above it, not only the list's own box", () => {
    // The ring's entries sit outside the list's box (RADIUS below its top): measured by their own boxes.
    const spy = vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(function (this: HTMLElement) {
      const menu = this.closest<HTMLElement>("[role='menu']");
      const top = Number.parseFloat(menu?.style.top ?? "0");
      return this.getAttribute("role") === "menu" ? rect(top, 10) : rect(top + 96, 30);
    });
    render(<RadialMenu x={40} y={500} layout="radial" onClose={() => {}} items={[item("a", undefined), item("b", undefined)]} keepAbove={() => 600} />);
    expect(Number.parseFloat(screen.getByRole("menu").style.top) + 96 + 30).toBeLessThanOrEqual(600);
    spy.mockRestore();
  });

  it("stays where it opened when it already sits above it", () => {
    const spy = vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(function (this: HTMLElement) {
      return this.getAttribute("role") === "menu" ? rect(Number.parseFloat(this.style.top), 100) : rect(0, 0);
    });
    render(<RadialMenu x={40} y={200} layout="list" onClose={() => {}} items={[item("a", undefined)]} keepAbove={() => 600} />);
    expect(screen.getByRole("menu").style.top).toBe("200px");
    spy.mockRestore();
  });
});

// ADR-097 Amendment 3 (the owner's Part E): the menu's heading is in the page's own face; mono is for values.
describe("the menu's heading", () => {
  it("is in the page's face, not the mono", () => {
    render(<RadialMenu x={0} y={0} layout="list" title="2 selected" onClose={() => {}} items={[item("a", undefined)]} />);
    const heading = screen.getByText("2 selected");
    expect(heading.style.fontFamily).not.toContain("mono");
  });
});
