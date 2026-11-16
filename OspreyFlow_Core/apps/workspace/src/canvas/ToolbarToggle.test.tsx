// @vitest-environment jsdom
// v0.6.1 glass-rows C (ADR-145 Amendment 19 decision 6; the owner's rulings 1 and 14, 16 November 2026): on a narrow
// toolbar *Hide toolbar* reads "Hide" and *Show toolbar* "Show", each keeping its whole name for a screen reader.
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { HideToolbarButton, ShowToolbarButton } from "./ToolbarToggle";
import { CanvasToolbarCompact } from "./toolbarCompact";

afterEach(cleanup);

describe("Show toolbar's words (ruling 14)", () => {
  it("reads Show on a narrow toolbar, its name still Show toolbar", () => {
    render(<ShowToolbarButton onToggle={() => undefined} compact />);
    const show = screen.getByRole("button", { name: "Show toolbar" });
    expect(show.textContent).toBe("Show");
  });
  it("reads Show toolbar otherwise", () => {
    render(<ShowToolbarButton onToggle={() => undefined} />);
    expect(screen.getByRole("button", { name: "Show toolbar" }).textContent).toBe("Show toolbar");
  });
});

describe("Hide toolbar's words (ruling 1)", () => {
  it("reads Hide on a narrow toolbar, its name still Hide toolbar", () => {
    render(
      <CanvasToolbarCompact.Provider value={true}>
        <HideToolbarButton onToggle={() => undefined} />
      </CanvasToolbarCompact.Provider>,
    );
    expect(screen.getByRole("button", { name: "Hide toolbar" }).textContent).toBe("Hide");
  });
});
