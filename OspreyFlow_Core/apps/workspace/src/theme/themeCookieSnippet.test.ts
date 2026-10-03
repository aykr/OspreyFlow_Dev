// @vitest-environment jsdom
//
// `harness/theme_cookie.js` is the light and dark choice for the pages that are not React: the
// launcher's welcome page and Keycloak's sign-in page (ADR-072). It is one small script that is put
// in both. These tests run that very file, in a page with a cookie jar, so what is proved is what is
// shipped; and they run it against `theme.ts`, so the two can never disagree about the cookie.
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { readStoredTheme, storeTheme, THEME_COOKIE_NAME } from "./theme";

const SCRIPT = readFileSync(
  join(dirname(fileURLToPath(import.meta.url)), "..", "..", "..", "..", "harness", "theme_cookie.js"),
  "utf8",
);

interface OspreyThemeApi {
  current: () => "light" | "dark";
  set: (theme: "light" | "dark") => void;
  mountButton: () => HTMLButtonElement;
}

function runScript(): OspreyThemeApi {
  new Function(SCRIPT)();
  return (window as unknown as { ospreyTheme: OspreyThemeApi }).ospreyTheme;
}

beforeEach(() => {
  document.cookie = `${THEME_COOKIE_NAME}=; Path=/; Max-Age=0`;
  document.documentElement.removeAttribute("data-theme");
  document.body.innerHTML = "";
});
afterEach(() => {
  delete (window as unknown as { ospreyTheme?: unknown }).ospreyTheme;
});

describe("theme_cookie.js", () => {
  it("shows dark when no choice has been made", () => {
    runScript();
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
  });

  it("shows the choice made on another page of this host, before anything is drawn", () => {
    document.cookie = `${THEME_COOKIE_NAME}=light; Path=/`;
    runScript();
    expect(document.documentElement.getAttribute("data-theme")).toBe("light");
  });

  it("shows exactly what the Glass saved (the two read and write one cookie)", () => {
    storeTheme("light");
    runScript();
    expect(document.documentElement.getAttribute("data-theme")).toBe("light");
  });

  it("is dark for a value it does not know", () => {
    document.cookie = `${THEME_COOKIE_NAME}=sepia; Path=/`;
    runScript();
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
  });

  it("saves a choice where the Glass will read it", () => {
    const theme = runScript();
    theme.set("light");
    expect(readStoredTheme()).toBe("light");
    expect(theme.current()).toBe("light");
  });

  it("offers a Light button, a real button, that is pressed when the page is light and switches both ways", () => {
    const theme = runScript();
    const button = theme.mountButton();
    expect(button.tagName).toBe("BUTTON");
    expect(button.getAttribute("type")).toBe("button");
    expect(button.getAttribute("aria-label")).toBe("Light theme");
    expect(button.textContent).toContain("Light");
    expect(button.getAttribute("aria-pressed")).toBe("false");

    button.click();
    expect(document.documentElement.getAttribute("data-theme")).toBe("light");
    expect(button.getAttribute("aria-pressed")).toBe("true");
    expect(readStoredTheme()).toBe("light");

    button.click();
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
    expect(button.getAttribute("aria-pressed")).toBe("false");
    expect(readStoredTheme()).toBe("dark");
  });

  it("puts its button on the page by itself, once", () => {
    const theme = runScript();
    theme.mountButton();
    expect(document.querySelectorAll("button#osprey-theme-toggle")).toHaveLength(1);
  });

  it("starts its button pressed when the page is already light", () => {
    document.cookie = `${THEME_COOKIE_NAME}=light; Path=/`;
    const button = runScript().mountButton();
    expect(button.getAttribute("aria-pressed")).toBe("true");
  });

  it("colours its button only with the design tokens", () => {
    const button = runScript().mountButton();
    const style = button.getAttribute("style") ?? "";
    expect(style).not.toMatch(/#[0-9a-f]{3,8}\b|rgb\(|hsl\(/i);
    expect(style).toContain("var(--");
  });

  it("uses only tokens that exist (a misspelt token resolves to nothing, silently)", () => {
    const tokens = readFileSync(
      join(dirname(fileURLToPath(import.meta.url)), "..", "design", "tokens.css"),
      "utf8",
    );
    const defined = new Set([...tokens.matchAll(/(--[a-z0-9-]+)\s*:/g)].map((m) => m[1]));
    const used = [...SCRIPT.matchAll(/var\((--[a-z0-9-]+)\)/g)].map((m) => m[1]);
    expect(used.length).toBeGreaterThan(0);
    expect(used.filter((name) => !defined.has(name!))).toEqual([]);
  });

  it("does not stop a page that refuses cookies", () => {
    const original = Object.getOwnPropertyDescriptor(Document.prototype, "cookie")!;
    Object.defineProperty(document, "cookie", {
      configurable: true,
      get() {
        throw new Error("blocked");
      },
      set() {
        throw new Error("blocked");
      },
    });
    try {
      expect(() => runScript().set("light")).not.toThrow();
      expect(document.documentElement.getAttribute("data-theme")).toBe("light");
    } finally {
      delete (document as unknown as { cookie?: unknown }).cookie;
      Object.defineProperty(Document.prototype, "cookie", original);
    }
  });
});
