// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  ICON_CHOICES_KEY,
  forgetIconChoicesForTest,
  getIconChoices,
  onIconChoicesChange,
  resolveNodeIcon,
  setIconChoice,
} from "./iconChoices";

// ADR-079. The ontology gives each entity type a default icon; the analyst may choose another
// built-in drawing, none, or a picture of their own. Like the label choice (ADR-076) it is a way of
// looking, kept in this browser only, never sent to the server and not part of the case.

const DATA = "data:image/png;base64,iVBORw0KGgo=";
const DARK_FILL = "#1b2a6b";
const LIGHT_FILL = "#e8d9a0";

beforeEach(() => {
  localStorage.clear();
  forgetIconChoicesForTest();
});
afterEach(() => vi.restoreAllMocks());

describe("which icon a type is drawn with", () => {
  it("is the ontology's, in a colour that reads on the fill, when nothing was chosen", () => {
    expect(resolveNodeIcon("Person", "person", DARK_FILL)).toEqual({ kind: "glyph", name: "person", colourHex: "#ffffff" });
    expect(resolveNodeIcon("Person", "person", LIGHT_FILL)).toEqual({ kind: "glyph", name: "person", colourHex: "#101314" });
  });

  it("is none when the ontology names none, or names one the Glass cannot draw", () => {
    expect(resolveNodeIcon("Person", undefined, DARK_FILL)).toBeNull();
    expect(resolveNodeIcon("Person", null, DARK_FILL)).toBeNull();
    expect(resolveNodeIcon("Person", "not-an-icon", DARK_FILL)).toBeNull();
  });

  it("is the analyst's own built-in drawing, for that type only", () => {
    setIconChoice("Person", { kind: "glyph", name: "shield" });
    expect(resolveNodeIcon("Person", "person", DARK_FILL)).toMatchObject({ kind: "glyph", name: "shield" });
    expect(resolveNodeIcon("Endpoint", "phone", DARK_FILL)).toMatchObject({ kind: "glyph", name: "phone" });
  });

  it("is nothing at all when the analyst chose none, even where the ontology names one", () => {
    setIconChoice("Person", { kind: "none" });
    expect(resolveNodeIcon("Person", "person", DARK_FILL)).toBeNull();
  });

  it("is the analyst's own picture, keyed so that a new picture is a new key", () => {
    setIconChoice("Person", { kind: "image", dataUrl: DATA });
    const first = resolveNodeIcon("Person", "person", DARK_FILL);
    expect(first).toMatchObject({ kind: "image", dataUrl: DATA });
    setIconChoice("Person", { kind: "image", dataUrl: "data:image/png;base64,AAAA" });
    const second = resolveNodeIcon("Person", "person", DARK_FILL);
    expect(second && second.kind === "image" && first && first.kind === "image" && second.key !== first.key).toBe(true);
  });

  it("goes back to the ontology's when the choice is cleared", () => {
    setIconChoice("Person", { kind: "none" });
    setIconChoice("Person", null);
    expect(resolveNodeIcon("Person", "person", DARK_FILL)).toMatchObject({ name: "person" });
    expect(getIconChoices()).toEqual({});
  });

  it("refuses a choice that is not a drawing on the list or a small raster picture", () => {
    setIconChoice("Person", { kind: "glyph", name: "not-an-icon" });
    setIconChoice("Endpoint", { kind: "image", dataUrl: "https://example.test/a.png" });
    setIconChoice("Device", { kind: "image", dataUrl: "data:image/svg+xml;utf8,<svg/>" });
    expect(getIconChoices()).toEqual({});
  });
});

describe("keeping the choice in this browser", () => {
  it("writes it under one key, and says it was kept", () => {
    expect(setIconChoice("Person", { kind: "glyph", name: "shield" })).toBe(true);
    expect(JSON.parse(localStorage.getItem(ICON_CHOICES_KEY) ?? "null")).toEqual({
      Person: { kind: "glyph", name: "shield" },
    });
  });

  it("is read back after a reload", () => {
    localStorage.setItem(ICON_CHOICES_KEY, JSON.stringify({ Person: { kind: "image", dataUrl: DATA }, Device: { kind: "none" } }));
    forgetIconChoicesForTest();
    expect(getIconChoices()).toEqual({ Person: { kind: "image", dataUrl: DATA }, Device: { kind: "none" } });
  });

  it("ignores stored text that is not a choice, and keeps the rest", () => {
    for (const bad of ["not json", "[1]", "null", '{"Person":42}', '{"Person":{"kind":"glyph","name":"nope"}}', '{"Person":{"kind":"image","dataUrl":"https://x.test"}}']) {
      localStorage.setItem(ICON_CHOICES_KEY, bad);
      forgetIconChoicesForTest();
      expect(getIconChoices()).toEqual({});
    }
    localStorage.setItem(ICON_CHOICES_KEY, JSON.stringify({ Person: { kind: "none" }, Bad: { kind: "x" } }));
    forgetIconChoicesForTest();
    expect(getIconChoices()).toEqual({ Person: { kind: "none" } });
  });

  it("still works for this page, and says it was not kept, when the browser will not store it", () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("quota", "QuotaExceededError");
    });
    expect(setIconChoice("Person", { kind: "glyph", name: "shield" })).toBe(false);
    expect(resolveNodeIcon("Person", "person", DARK_FILL)).toMatchObject({ name: "shield" });
  });
});

describe("telling the canvas", () => {
  it("calls a listener when a choice changes, not when it is unchanged, and not after it is removed", () => {
    const heard = vi.fn();
    const stop = onIconChoicesChange(heard);
    setIconChoice("Person", { kind: "none" });
    setIconChoice("Person", { kind: "none" });
    expect(heard).toHaveBeenCalledTimes(1);
    stop();
    setIconChoice("Person", null);
    expect(heard).toHaveBeenCalledTimes(1);
  });
});
