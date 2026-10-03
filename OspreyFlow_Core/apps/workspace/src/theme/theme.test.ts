// @vitest-environment jsdom
//
// Light and dark (ADR-070): dark is the working default; the analyst's choice is kept in this
// browser only and put on the page as `data-theme`, which tokens.css already styles. Nothing about
// it is sent to the server.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { applyTheme, currentTheme, onThemeChange, readStoredTheme, storeTheme, THEME_STORAGE_KEY } from "./theme";

beforeEach(() => {
  localStorage.clear();
  document.documentElement.removeAttribute("data-theme");
});
afterEach(() => vi.restoreAllMocks());

describe("theme", () => {
  it("is dark until the analyst chooses otherwise", () => {
    expect(readStoredTheme()).toBe("dark");
    expect(currentTheme()).toBe("dark");
  });

  it("remembers a choice in this browser", () => {
    storeTheme("light");
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe("light");
    expect(readStoredTheme()).toBe("light");
  });

  it("ignores a stored value it does not know", () => {
    localStorage.setItem(THEME_STORAGE_KEY, "sepia");
    expect(readStoredTheme()).toBe("dark");
  });

  it("still works, as dark, when the browser will not let it read or write storage", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    expect(readStoredTheme()).toBe("dark");
    expect(() => storeTheme("light")).not.toThrow();
  });

  it("puts the theme on the page, where tokens.css styles it, and says which is current", () => {
    applyTheme("light");
    expect(document.documentElement.getAttribute("data-theme")).toBe("light");
    expect(currentTheme()).toBe("light");
    applyTheme("dark");
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
    expect(currentTheme()).toBe("dark");
  });

  it("tells anything drawing to a canvas when the theme changes, and stops when asked", () => {
    const seen: string[] = [];
    const stop = onThemeChange((theme) => seen.push(theme));
    applyTheme("light");
    applyTheme("light"); // no change, no news
    applyTheme("dark");
    stop();
    applyTheme("light");
    expect(seen).toEqual(["light", "dark"]);
  });
});
