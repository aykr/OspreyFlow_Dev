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
  it("offers the light theme while dark is showing, and says it is not pressed", () => {
    render(<ThemeToggle />);
    const button = screen.getByRole("button", { name: "Light theme" });
    expect(button.getAttribute("aria-pressed")).toBe("false");
    expect(button.getAttribute("title")).toBe("Switch to the light theme");
  });

  it("switches the page to light, keeps the choice in this browser, and says it is pressed", () => {
    render(<ThemeToggle />);
    fireEvent.click(screen.getByRole("button", { name: "Light theme" }));
    expect(currentTheme()).toBe("light");
    expect(readStoredTheme()).toBe("light");
    const button = screen.getByRole("button", { name: "Light theme" });
    expect(button.getAttribute("aria-pressed")).toBe("true");
    expect(button.getAttribute("title")).toBe("Switch to the dark theme");
  });

  it("switches back to dark", () => {
    render(<ThemeToggle />);
    fireEvent.click(screen.getByRole("button", { name: "Light theme" }));
    fireEvent.click(screen.getByRole("button", { name: "Light theme" }));
    expect(currentTheme()).toBe("dark");
    expect(readStoredTheme()).toBe("dark");
  });

  it("follows a change made elsewhere (another toggle, a restored choice)", () => {
    render(<ThemeToggle />);
    act(() => applyTheme("light"));
    expect(screen.getByRole("button", { name: "Light theme" }).getAttribute("aria-pressed")).toBe("true");
  });
});
