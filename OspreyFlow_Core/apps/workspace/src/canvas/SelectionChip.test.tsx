// @vitest-environment jsdom
// ADR-093 step 3: while anything is selected, a chip in the canvas corner says how many, with Clear.
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SelectionChip } from "./SelectionChip";

afterEach(cleanup);

describe("SelectionChip", () => {
  it("says how many are selected and clears them", () => {
    const onClear = vi.fn();
    render(<SelectionChip count={3} onClear={onClear} />);
    expect(screen.getByRole("status").textContent).toContain("3 selected");
    fireEvent.click(screen.getByRole("button", { name: "Clear the selection" }));
    expect(onClear).toHaveBeenCalledTimes(1);
  });

  it("says one node in the singular, and shows nothing when nothing is selected", () => {
    const { rerender, container } = render(<SelectionChip count={1} onClear={vi.fn()} />);
    expect(screen.getByRole("status").textContent).toContain("1 selected");
    rerender(<SelectionChip count={0} onClear={vi.fn()} />);
    expect(container.textContent).toBe("");
  });
});
