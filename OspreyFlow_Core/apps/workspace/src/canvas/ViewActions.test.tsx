// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ViewActions } from "./ViewActions";

afterEach(cleanup);

function setup(
  overrides: Partial<Parameters<typeof ViewActions>[0]> = {},
) {
  const handlers = { onRemoveSelected: vi.fn(), onClearAll: vi.fn() };
  render(
    <ViewActions nodeCount={1091} selectedCount={2} {...handlers} {...overrides} />,
  );
  return handlers;
}

describe("ViewActions", () => {
  it("removes the selected nodes at once, and says how many", () => {
    const h = setup();
    fireEvent.click(screen.getByRole("button", { name: /Remove selected \(2\)/ }));
    expect(h.onRemoveSelected).toHaveBeenCalledOnce();
  });

  it("offers no removal when nothing is selected", () => {
    setup({ selectedCount: 0 });
    const button = screen.getByRole("button", { name: /Remove selected/ });
    expect((button as HTMLButtonElement).disabled).toBe(true);
  });

  it("does not clear the view on the first click; it asks, with the number", () => {
    const h = setup();
    fireEvent.click(screen.getByRole("button", { name: "Clear view" }));
    expect(h.onClearAll).not.toHaveBeenCalled();
    expect(screen.getByRole("alertdialog").textContent).toContain("1,091");
  });

  it("clears the view only after the analyst confirms", () => {
    const h = setup();
    fireEvent.click(screen.getByRole("button", { name: "Clear view" }));
    fireEvent.click(screen.getByRole("button", { name: /Clear all 1,091/ }));
    expect(h.onClearAll).toHaveBeenCalledOnce();
  });

  it("can back out of clearing, and nothing is removed", () => {
    const h = setup();
    fireEvent.click(screen.getByRole("button", { name: "Clear view" }));
    fireEvent.click(screen.getByRole("button", { name: "Keep" }));
    expect(h.onClearAll).not.toHaveBeenCalled();
    expect(screen.queryByRole("alertdialog")).toBeNull();
  });

  it("says the records stay in the store and History can undo", () => {
    setup();
    fireEvent.click(screen.getByRole("button", { name: "Clear view" }));
    expect(screen.getByRole("alertdialog").textContent).toMatch(/History/);
  });

  it("offers no clearing from an empty view", () => {
    setup({ nodeCount: 0, selectedCount: 0 });
    const button = screen.getByRole("button", { name: "Clear view" });
    expect((button as HTMLButtonElement).disabled).toBe(true);
  });
});
