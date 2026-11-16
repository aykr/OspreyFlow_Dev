// @vitest-environment jsdom
// v0.6.1 glass-rows C (ADR-145 Amendment 19 decision 6; the owner's ruling 3, 16 November 2026): whether the
// view's toolbar is hidden is remembered per signed-in analyst in this browser, as the Studio remembers its
// mode (`ospreyflow.studio.mode.<username>`), and Alt+Shift+T hides or shows it.
import { afterEach, describe, expect, it, vi } from "vitest";

import { forgetToolbarSettings, isToolbarShortcut, readToolbarHidden, toolbarKey, writeToolbarHidden } from "./toolbarVisibility";

afterEach(() => {
  localStorage.clear();
  forgetToolbarSettings();
});

describe("the remembered setting", () => {
  it("is kept under ospreyflow.glass.toolbar.<username>, as hidden or not at all", () => {
    expect(toolbarKey("osprey-demo-analyst")).toBe("ospreyflow.glass.toolbar.osprey-demo-analyst");
    expect(readToolbarHidden("osprey-demo-analyst")).toBe(false);
    writeToolbarHidden("osprey-demo-analyst", true);
    expect(localStorage.getItem("ospreyflow.glass.toolbar.osprey-demo-analyst")).toBe("hidden");
    expect(readToolbarHidden("osprey-demo-analyst")).toBe(true);
    writeToolbarHidden("osprey-demo-analyst", false);
    expect(localStorage.getItem("ospreyflow.glass.toolbar.osprey-demo-analyst")).toBeNull();
  });

  it("is one analyst's: another signed in on the same browser sees the toolbar", () => {
    writeToolbarHidden("analyst-a", true);
    expect(readToolbarHidden("analyst-b")).toBe(false);
  });

  it("is not remembered for nobody, but still hides for this page: with no one signed in nothing is written", () => {
    writeToolbarHidden(null, true);
    expect(localStorage.length).toBe(0);
    expect(readToolbarHidden(null)).toBe(true);
    writeToolbarHidden(null, false);
    expect(readToolbarHidden(null)).toBe(false);
  });

  it("still hides for this page where the browser's storage refuses it", () => {
    const setItem = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("blocked", "SecurityError");
    });
    writeToolbarHidden("analyst-c", true);
    expect(readToolbarHidden("analyst-c")).toBe(true);
    setItem.mockRestore();
    writeToolbarHidden("analyst-c", false);
  });
});

describe("Alt+Shift+T", () => {
  const key = (init: KeyboardEventInit) => new KeyboardEvent("keydown", init);
  it("is matched by the key's place, so a Mac's Option character does not matter", () => {
    expect(isToolbarShortcut(key({ code: "KeyT", key: "T", altKey: true, shiftKey: true }))).toBe(true);
    expect(isToolbarShortcut(key({ code: "KeyT", key: "ˇ", altKey: true, shiftKey: true }))).toBe(true);
  });
  it("is not Ctrl+Shift+T (a browser's reopen tab), nor T alone, nor with Cmd", () => {
    expect(isToolbarShortcut(key({ code: "KeyT", key: "T", ctrlKey: true, shiftKey: true }))).toBe(false);
    expect(isToolbarShortcut(key({ code: "KeyT", key: "t" }))).toBe(false);
    expect(isToolbarShortcut(key({ code: "KeyT", key: "T", altKey: true }))).toBe(false);
    expect(isToolbarShortcut(key({ code: "KeyT", key: "T", altKey: true, shiftKey: true, metaKey: true }))).toBe(false);
    expect(isToolbarShortcut(key({ code: "KeyT", key: "T", altKey: true, shiftKey: true, ctrlKey: true }))).toBe(false);
  });
});
