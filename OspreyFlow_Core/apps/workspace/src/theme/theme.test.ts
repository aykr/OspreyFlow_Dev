// @vitest-environment jsdom
//
// Light and dark (ADR-070): dark is the working default; the analyst's choice is kept in this
// browser only and put on the page as `data-theme`, which tokens.css already styles. Nothing about
// it is sent to the server.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  applyTheme,
  currentTheme,
  onThemeChange,
  readStoredTheme,
  storeTheme,
  THEME_COOKIE_NAME,
  THEME_STORAGE_KEY,
} from "./theme";

function clearThemeCookie(): void {
  document.cookie = `${THEME_COOKIE_NAME}=; Path=/; Max-Age=0`;
}

beforeEach(() => {
  localStorage.clear();
  clearThemeCookie();
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

// The choice has to reach every OspreyFlow page, and the pages are on different ports of one host
// (the Glass, the launcher, the sign-in page, the setup harness). A browser keeps its saved settings
// per port, so the shared place is a cookie, which is kept per host (ADR-072).
describe("theme, shared across the pages of one host", () => {
  it("keeps the choice in a cookie as well as in this page's storage", () => {
    storeTheme("light");
    expect(document.cookie).toContain(`${THEME_COOKIE_NAME}=light`);
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe("light");
  });

  it("takes the cookie over the page's own storage, because another page may have changed it since", () => {
    localStorage.setItem(THEME_STORAGE_KEY, "dark");
    document.cookie = `${THEME_COOKIE_NAME}=light; Path=/`;
    expect(readStoredTheme()).toBe("light");
  });

  it("uses what the page's storage holds when there is no cookie, and puts it in a cookie for the other pages", () => {
    localStorage.setItem(THEME_STORAGE_KEY, "light");
    expect(readStoredTheme()).toBe("light");
    expect(document.cookie).toContain(`${THEME_COOKIE_NAME}=light`);
  });

  it("ignores a cookie value it does not know", () => {
    document.cookie = `${THEME_COOKIE_NAME}=sepia; Path=/`;
    expect(readStoredTheme()).toBe("dark");
  });

  it("still works when the browser refuses cookies", () => {
    vi.spyOn(Document.prototype, "cookie", "get").mockImplementation(() => {
      throw new Error("blocked");
    });
    vi.spyOn(Document.prototype, "cookie", "set").mockImplementation(() => {
      throw new Error("blocked");
    });
    storeTheme("light");
    expect(readStoredTheme()).toBe("light"); // from this page's storage
  });
});
