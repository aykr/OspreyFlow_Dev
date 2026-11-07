// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";

import { readStudioMode, studioModeKey, writeStudioMode } from "./studioMode";

afterEach(() => {
  window.localStorage.clear();
  vi.restoreAllMocks();
});

describe("the Studio's mode preference (ADR-140 decision 3, Amendment 1.3)", () => {
  it("starts every person in guided mode", () => {
    expect(readStudioMode("engineer-1")).toBe("guided");
  });

  it("is per person: one person's expert mode is not another's", () => {
    writeStudioMode("engineer-1", "expert");
    expect(readStudioMode("engineer-1")).toBe("expert");
    expect(readStudioMode("engineer-2")).toBe("guided");
  });

  it("reads an unknown stored value as guided, never as expert", () => {
    window.localStorage.setItem(studioModeKey("engineer-1"), "EXPERT");
    expect(readStudioMode("engineer-1")).toBe("guided");
  });

  it("falls back to guided when the browser refuses storage", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("refused");
    });
    expect(readStudioMode("engineer-1")).toBe("guided");
    expect(() => writeStudioMode("engineer-1", "expert")).not.toThrow();
  });
});
