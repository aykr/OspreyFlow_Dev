// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
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
