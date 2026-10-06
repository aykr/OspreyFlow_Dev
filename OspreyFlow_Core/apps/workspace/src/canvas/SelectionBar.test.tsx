// @vitest-environment jsdom
// ADR-097 step 1 (design review item 2): one selection bar, the only live count of the selection,
// shown only while something is selected, with what can be done to it.
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SelectionBar } from "./SelectionBar";

afterEach(cleanup);

function mount(count: number) {
  const calls = { expand: vi.fn(), branch: vi.fn(), remove: vi.fn(), clear: vi.fn() };
  const view = render(
    <SelectionBar
      count={count}
      onExpand={calls.expand}
      onBranch={calls.branch}
      onRemove={calls.remove}
      onClear={calls.clear}
    />,
  );
  return { ...calls, view };
}

describe("SelectionBar", () => {
  it("is not there while nothing is selected", () => {
    const { view } = mount(0);
    expect(view.container.innerHTML).toBe("");
  });

  it("says how many once, and offers each action on the selection", () => {
    const calls = mount(3);
    expect(screen.getByRole("toolbar", { name: "Selection" })).toBeTruthy();
    expect(screen.getAllByText(/3 selected/)).toHaveLength(1);
    fireEvent.click(screen.getByRole("button", { name: "Expand" }));
    fireEvent.click(screen.getByRole("button", { name: "Branch to a new case" }));
    fireEvent.click(screen.getByRole("button", { name: "Remove from view" }));
    fireEvent.click(screen.getByRole("button", { name: "Clear" }));
    expect([calls.expand, calls.branch, calls.remove, calls.clear].every((f) => f.mock.calls.length === 1)).toBe(true);
  });

  it("clears on Escape", () => {
    const calls = mount(2);
    fireEvent.keyDown(screen.getByRole("toolbar", { name: "Selection" }), { key: "Escape" });
    expect(calls.clear).toHaveBeenCalled();
  });

  it("offers no Branch where the surface cannot branch", () => {
    render(<SelectionBar count={1} onRemove={vi.fn()} onClear={vi.fn()} />);
    expect(screen.queryByRole("button", { name: "Branch to a new case" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Expand" })).toBeNull();
  });
});
