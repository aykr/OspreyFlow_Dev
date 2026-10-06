// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ViewActions } from "./ViewActions";

afterEach(cleanup);

function setup(
  overrides: Partial<Parameters<typeof ViewActions>[0]> = {},
) {
  const handlers = { onClearAll: vi.fn() };
  render(<ViewActions nodeCount={1091} {...handlers} {...overrides} />);
  return handlers;
}

describe("ViewActions", () => {
  it("offers nothing to do to selected nodes: that is the selection bar's (ADR-097 step 1)", () => {
    setup();
    expect(screen.queryByRole("button", { name: /Remove selected|Branch selected/ })).toBeNull();
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
    setup({ nodeCount: 0 });
    const button = screen.getByRole("button", { name: "Clear view" });
    expect((button as HTMLButtonElement).disabled).toBe(true);
  });

  it("offers to hide a link only while one is selected", () => {
    const h = { onHideLink: vi.fn(), onShowHiddenLinks: vi.fn() };
    setup({ selectedLink: false, ...h });
    expect(screen.queryByRole("button", { name: "Hide selected link" })).toBeNull();
    cleanup();
    setup({ selectedLink: true, ...h });
    fireEvent.click(screen.getByRole("button", { name: "Hide selected link" }));
    expect(h.onHideLink).toHaveBeenCalledOnce();
  });

  it("offers to bring hidden links back, with how many, only when some are hidden", () => {
    const h = { onHideLink: vi.fn(), onShowHiddenLinks: vi.fn() };
    setup({ hiddenLinkCount: 0, ...h });
    expect(screen.queryByRole("button", { name: /Show hidden links/ })).toBeNull();
    cleanup();
    setup({ hiddenLinkCount: 3, ...h });
    fireEvent.click(screen.getByRole("button", { name: "Show hidden links (3)" }));
    expect(h.onShowHiddenLinks).toHaveBeenCalledOnce();
  });



});
