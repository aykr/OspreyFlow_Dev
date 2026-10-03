// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CommunitiesControls } from "./CommunitiesControls";

afterEach(cleanup);

function setup(over: Partial<Parameters<typeof CommunitiesControls>[0]> = {}) {
  const handlers = { onToggle: vi.fn(), onCollapseAll: vi.fn(), onExpandAll: vi.fn() };
  render(<CommunitiesControls on={false} groupCount={0} foldedCount={0} {...handlers} {...over} />);
  return handlers;
}

describe("CommunitiesControls", () => {
  it("is one button until switched on, and says whether it is on", () => {
    setup();
    expect(screen.getByRole("button", { name: "Communities" }).getAttribute("aria-pressed")).toBe("false");
    expect(screen.queryByRole("button", { name: "Collapse all" })).toBeNull();
  });

  it("switches on and off from the button", () => {
    const h = setup();
    fireEvent.click(screen.getByRole("button", { name: "Communities" }));
    expect(h.onToggle).toHaveBeenCalledTimes(1);
  });

  it("when on, says how many groups there are and offers Collapse all and Expand all", () => {
    setup({ on: true, groupCount: 3, foldedCount: 1 });
    expect(screen.getByRole("button", { name: "Communities" }).getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByText("3 groups, 1 folded")).toBeTruthy();
    expect((screen.getByRole("button", { name: "Collapse all" }) as HTMLButtonElement).disabled).toBe(false);
    expect((screen.getByRole("button", { name: "Expand all" }) as HTMLButtonElement).disabled).toBe(false);
  });

  it("collapses and expands everything", () => {
    const h = setup({ on: true, groupCount: 2, foldedCount: 1 });
    fireEvent.click(screen.getByRole("button", { name: "Collapse all" }));
    fireEvent.click(screen.getByRole("button", { name: "Expand all" }));
    expect(h.onCollapseAll).toHaveBeenCalledTimes(1);
    expect(h.onExpandAll).toHaveBeenCalledTimes(1);
  });

  it("disables what cannot do anything: Collapse all when all are folded, Expand all when none is", () => {
    setup({ on: true, groupCount: 2, foldedCount: 2 });
    expect((screen.getByRole("button", { name: "Collapse all" }) as HTMLButtonElement).disabled).toBe(true);
    cleanup();
    setup({ on: true, groupCount: 2, foldedCount: 0 });
    expect((screen.getByRole("button", { name: "Expand all" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("says plainly when no group was found, and offers nothing to fold", () => {
    setup({ on: true, groupCount: 0 });
    expect(screen.getByText("No groups found among these nodes")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Collapse all" })).toBeNull();
  });

  it("uses the singular for one group", () => {
    setup({ on: true, groupCount: 1 });
    expect(screen.getByText("1 group, 0 folded")).toBeTruthy();
  });
});
