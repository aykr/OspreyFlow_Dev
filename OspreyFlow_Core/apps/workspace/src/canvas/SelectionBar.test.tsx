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
  // The owner, 14 October 2026: "make this a bit more elegant and intuitive" — one control that reads
  // as a sentence, *Show links* · *− direct +*, in the reference's selection bar.
  it("steps the degrees from direct to within 6, and asks within the one shown", () => {
    const onLinksAmong = vi.fn();
    render(<SelectionBar count={3} onLinksAmong={onLinksAmong} onRemove={() => {}} onClear={() => {}} />);
    const reading = screen
      .getByRole("group", { name: "Degrees of separation" })
      .querySelector(".selection-bar__reading") as HTMLElement;
    const fewer = screen.getByRole("button", { name: "Fewer degrees" });
    const more = screen.getByRole("button", { name: "More degrees" });
    expect(reading.textContent).toBe("direct");
    expect(fewer).toHaveProperty("disabled", true);
    fireEvent.click(screen.getByRole("button", { name: "Show links among these" }));
    fireEvent.click(more);
    fireEvent.click(more);
    fireEvent.click(more);
    expect(reading.textContent).toBe("within 4");
    fireEvent.click(screen.getByRole("button", { name: "Show links among these" }));
    for (let i = 0; i < 5; i += 1) fireEvent.click(more);
    expect(reading.textContent).toBe("within 6");
    expect(more).toHaveProperty("disabled", true);
    fireEvent.click(fewer);
    expect(reading.textContent).toBe("within 5");
    expect(onLinksAmong.mock.calls).toEqual([[1], [4]]);
  });

  it("keeps to direct links above 8 selected, and says why", () => {
    const onLinksAmong = vi.fn();
    render(<SelectionBar count={9} onLinksAmong={onLinksAmong} onRemove={() => {}} onClear={() => {}} />);
    const more = screen.getByRole("button", { name: "More degrees" });
    expect(more).toHaveProperty("disabled", true);
    expect(more.getAttribute("title")).toBe("Routes are looked for among at most 8 selected nodes");
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

// ADR-128 decision 2 (B3): after Select what is lit the bar says what was lit and that undated links
// are not included, and offers one undo, which gives back the selection that was there before.
describe("the selection bar after Select what is lit", () => {
  it("says what was lit and offers one undo while the lit selection stands", () => {
    const undo = vi.fn();
    render(
      <SelectionBar
        count={4}
        litNote="Lit 5 Jan – 30 Apr 2026: undated links are not included"
        onUndoLit={undo}
        onRemove={() => undefined}
        onClear={() => undefined}
      />,
    );
    expect(screen.getByText(/undated links are not included/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Undo select what is lit" }));
    expect(undo).toHaveBeenCalledTimes(1);
  });

  it("offers neither the note nor the undo otherwise", () => {
    render(<SelectionBar count={4} onRemove={() => undefined} onClear={() => undefined} />);
    expect(screen.queryByText(/undated links are not included/)).toBeNull();
    expect(screen.queryByRole("button", { name: "Undo select what is lit" })).toBeNull();
  });
});
