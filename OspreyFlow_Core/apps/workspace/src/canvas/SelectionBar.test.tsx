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

// ADR-098 decision 1: the links among the selected nodes, on demand.
describe("SelectionBar: Show links among these", () => {
  it("is offered for two or more selected nodes and calls back", () => {
    const onLinksAmong = vi.fn();
    render(<SelectionBar count={3} onLinksAmong={onLinksAmong} onRemove={() => {}} onClear={() => {}} />);
    fireEvent.click(screen.getByRole("button", { name: "Show links among these" }));
    expect(onLinksAmong).toHaveBeenCalledTimes(1);
  });

  // ADR-098 Amendment 4 (the owner: "specify the degrees of separation i am allowed to explore,
  // limit the maximum depth to 6"): a degree from 1 to 6 beside the button.
  it("asks within the degrees chosen, 1 to 6, 1 unless changed", () => {
    const onLinksAmong = vi.fn();
    render(<SelectionBar count={3} onLinksAmong={onLinksAmong} onRemove={() => {}} onClear={() => {}} />);
    const group = screen.getByRole("radiogroup", { name: "Degrees of separation" });
    const radios = Array.from(group.querySelectorAll<HTMLInputElement>('input[type="radio"]'));
    expect(radios.map((r) => r.value)).toEqual(["1", "2", "3", "4", "5", "6"]);
    expect(radios[0]?.checked).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "Show links among these" }));
    fireEvent.click(screen.getByRole("radio", { name: "Within 4 degrees" }));
    fireEvent.click(screen.getByRole("button", { name: "Show links among these" }));
    expect(onLinksAmong.mock.calls).toEqual([[1], [4]]);
  });

  it("keeps to one degree above 8 selected, and says why", () => {
    const onLinksAmong = vi.fn();
    render(<SelectionBar count={9} onLinksAmong={onLinksAmong} onRemove={() => {}} onClear={() => {}} />);
    const group = screen.getByRole("radiogroup", { name: "Degrees of separation" });
    expect(group.getAttribute("title")).toBe("Routes are looked for among at most 8 selected nodes");
    expect(screen.getByRole("radio", { name: "Within 4 degrees" })).toHaveProperty("disabled", true);
    fireEvent.click(screen.getByRole("button", { name: "Show links among these" }));
    expect(onLinksAmong).toHaveBeenCalledWith(1);
  });

  it("is not offered for one node, which has no links among itself", () => {
    render(<SelectionBar count={1} onLinksAmong={() => {}} onRemove={() => {}} onClear={() => {}} />);
    expect(screen.queryByRole("button", { name: "Show links among these" })).toBeNull();
  });

  it("offers Ask the model about these… only while the selection holds a Document (ADR-098 decision 4)", () => {
    const ask = vi.fn();
    const { rerender } = render(
      <SelectionBar count={2} onAsk={ask} documentCount={0} onRemove={() => {}} onClear={() => {}} />,
    );
    expect(screen.queryByRole("button", { name: "Ask the model about these…" })).toBeNull();
    rerender(<SelectionBar count={2} onAsk={ask} documentCount={1} onRemove={() => {}} onClear={() => {}} />);
    fireEvent.click(screen.getByRole("button", { name: "Ask the model about these…" }));
    expect(ask).toHaveBeenCalledTimes(1);
  });
});

// ADR-115 E4 (review items 2 and 5): Expand is the bar's one primary action, in brass; Clear shows
// that Escape does the same.
describe("the selection bar's actions", () => {
  it("makes Expand the primary action and every other action quiet", () => {
    render(<SelectionBar count={3} onExpand={() => undefined} onBranch={() => undefined} onRemove={() => undefined} onClear={() => undefined} />);
    const bar = screen.getByRole("toolbar", { name: "Selection" });
    const primary = Array.from(bar.querySelectorAll(".btn--primary")).map((b) => b.textContent);
    expect(primary).toEqual(["Expand"]);
  });

  it("names Escape beside Clear, without changing what Clear is called", () => {
    render(<SelectionBar count={1} onRemove={() => undefined} onClear={() => undefined} />);
    const clear = screen.getByRole("button", { name: "Clear" });
    expect(clear.querySelector("kbd")?.textContent).toBe("Esc");
  });
});
