// @vitest-environment jsdom
// DESIGN.md §3.3 and §10 (ADR-115 E1): semantic colour appears only with an icon and a text label, and
// never as a status stripe — the detector's "side-tab" finding on the old 3px left border.
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { Toast } from "./Toast";

afterEach(cleanup);

describe("Toast", () => {
  it("says its kind with a glyph and in words, never by colour alone", () => {
    render(<Toast kind="error" message="The export was refused." />);
    const toast = screen.getByRole("status");
    expect(toast.textContent).toBe("!Error: The export was refused.");
    expect(toast.querySelector(".toast__glyph")?.getAttribute("aria-hidden")).toBe("true");
  });

  it("an information toast has neither", () => {
    render(<Toast message="2 items withheld by handling policy." />);
    expect(screen.getByRole("status").textContent).toBe("2 items withheld by handling policy.");
  });

  it("has no status stripe", () => {
    const css = readFileSync(join(__dirname, "..", "primitives.css"), "utf-8");
    expect(css).not.toMatch(/\.toast[^{]*\{[^}]*border-left/);
  });
});
