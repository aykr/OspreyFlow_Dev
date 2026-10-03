// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { applyTheme, currentTheme, readStoredTheme } from "./theme";
import { ThemeToggle } from "./ThemeToggle";

beforeEach(() => {
  localStorage.clear();
  applyTheme("dark");
});
afterEach(cleanup);

describe("ThemeToggle", () => {
  it("names the theme it will switch to: Light while the page is dark", () => {
    render(<ThemeToggle />);
    const button = screen.getByRole("button", { name: "Switch to the light theme" });
    expect(button.textContent).toContain("Light");
    expect(button.textContent).not.toContain("Dark");
    expect(button.hasAttribute("aria-pressed")).toBe(false);
  });

  it("is a plainly drawn, worded button, not a bare glyph that has to be hunted for", () => {
    render(<ThemeToggle />);
    const button = screen.getByRole("button", { name: "Switch to the light theme" });
    expect(button.classList.contains("btn")).toBe(true);
  });

  it("once the page is light it says Dark, the theme it will switch back to", () => {
    render(<ThemeToggle />);
    fireEvent.click(screen.getByRole("button", { name: "Switch to the light theme" }));
    expect(currentTheme()).toBe("light");
    expect(readStoredTheme()).toBe("light");
    const button = screen.getByRole("button", { name: "Switch to the dark theme" });
    expect(button.textContent).toContain("Dark");
    expect(button.textContent).not.toContain("Light");
    expect(button.hasAttribute("aria-pressed")).toBe(false);
  });

  it("switches back to dark and says Light again", () => {
    render(<ThemeToggle />);
    fireEvent.click(screen.getByRole("button", { name: "Switch to the light theme" }));
    fireEvent.click(screen.getByRole("button", { name: "Switch to the dark theme" }));
    expect(currentTheme()).toBe("dark");
    expect(readStoredTheme()).toBe("dark");
    expect(screen.getByRole("button", { name: "Switch to the light theme" }).textContent).toContain("Light");
  });

  it("follows a change made elsewhere (another toggle, a restored choice)", () => {
    render(<ThemeToggle />);
    act(() => applyTheme("light"));
    expect(screen.getByRole("button", { name: "Switch to the dark theme" }).textContent).toContain("Dark");
  });
});
