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

// ADR-115 Amendment 1: in the top bar the switch is an icon of its own; its name still says which
// theme a press switches to, for a screen reader and as a tooltip.
describe("ThemeToggle as the bar's icon", () => {
  it("is an icon button named for the theme it switches to", () => {
    render(<ThemeToggle variant="icon" />);
    const button = screen.getByRole("button", { name: "Switch to the light theme" });
    expect(button.classList.contains("icon-btn")).toBe(true);
    expect(button.getAttribute("title")).toBe("Switch to the light theme");
    expect(button.textContent?.trim()).toBe("☀");
    fireEvent.click(button);
    expect(currentTheme()).toBe("light");
    expect(screen.getByRole("button", { name: "Switch to the dark theme" }).textContent?.trim()).toBe("☾");
  });
});

describe("the bars carry the theme icon", () => {
  it("TopBar and StartBar each hold it beside the account", async () => {
    const { TopBar } = await import("../shell/TopBar");
    const { StartBar } = await import("../shell/StartPage");
    render(<TopBar app="glass" caseSwitcher={<span>case</span>} account={<span>account</span>} />);
    expect(screen.getByRole("button", { name: "Switch to the light theme" })).toBeTruthy();
    cleanup();
    render(<StartBar account={<span>account</span>} marking={null} />);
    expect(screen.getByRole("button", { name: "Switch to the light theme" })).toBeTruthy();
  });
});
