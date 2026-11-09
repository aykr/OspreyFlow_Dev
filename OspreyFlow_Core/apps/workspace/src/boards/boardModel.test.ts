// The board's pure reading of an opened board (ADR-143 decisions 4 and 5): an item's name, where it
// sits, and how far an arrow key moves it, never off the board.
import { describe, expect, it } from "vitest";

import { clamp, gradesOf, itemLabel, linkLabel, moved, nextPlace, offerGrades, placed } from "./boardModel";
import type { BoardOpened } from "./boardsApi";

const at = "2026-11-08T10:00:00Z";
const provenance = (drawn?: Record<string, unknown>) => ({
  state: "asserted" as const,
  sources: [{ document_id: "d", locator: "l", excerpt_hash: "" }],
  first_seen: at,
  ...(drawn ? { drawn } : {}),
});
const handling = { classification: "OFFICIAL", handling_code: "P", originator: "u", owning_unit: "u" };
const audit = { created_at: at, created_by: "alice" };
const grading = { scheme: "5x5x5" as const, source: "B", intelligence: "2", handling: "1" };

function node(id: string, properties: Record<string, unknown>, drawnLabel?: string) {
  return {
    id,
    type: "Person",
    properties,
    provenance: provenance(drawnLabel ? { item_id: "i", asserted_by: "a", board_id: "b", case_id: "c", label: drawnLabel, grading } : undefined),
    handling,
    audit,
  };
}

describe("itemLabel", () => {
  it("names a drawn item by the analyst's own label, whatever its properties say", () => {
    expect(itemLabel(node("d", { family_name: "Tall" }, "Unknown male “Tall”") as never)).toBe("Unknown male “Tall”");
  });
  it("names a loaded person by given names and family name, and anything else by its type", () => {
    expect(itemLabel(node("p", { family_name: "Mercer", given_names: "Ada" }) as never)).toBe("Ada Mercer");
    expect(itemLabel(node("x", {}) as never)).toBe("Unnamed Person");
  });
});

describe("linkLabel", () => {
  it("says a drawn link's own words and a resolution link's meaning", () => {
    const edge = (type: string, drawnLabel?: string) => ({
      id: "e", type, source: "a", target: "b", provenance: provenance(drawnLabel ? { item_id: "i", asserted_by: "a", board_id: "b", case_id: "c", label: drawnLabel, grading } : undefined), handling, audit,
    });
    expect(linkLabel(edge("ASSOCIATE_OF", "seen together") as never)).toBe("seen together");
    expect(linkLabel(edge("SAME_AS") as never)).toBe("same as");
    expect(linkLabel(edge("FAMILY_OF") as never)).toBe("family of");
  });
});

describe("placing and moving", () => {
  const opened = (layout: Record<string, unknown>) =>
    ({ nodes: [node("a", {}), node("b", {})], edges: [], layout } as unknown as BoardOpened);

  it("keeps a kept place and gives the rest a free place on the board", () => {
    const places = placed(opened({ a: { x: 0.4, y: 0.6 } }));
    expect(places.a).toEqual({ x: 0.4, y: 0.6 });
    expect(places.b).toEqual({ x: 0.15, y: 0.15 });
  });

  it("never places or moves an item off the board", () => {
    expect(placed(opened({ a: { x: 3, y: -1 } })).a).toEqual({ x: 0.95, y: 0.05 });
    expect(moved({ x: 0.94, y: 0.5 }, "ArrowRight", true)).toEqual({ x: 0.95, y: 0.5 });
    expect(clamp(-2)).toBe(0.05);
  });

  it("moves by a small step, or a large one with Shift, and ignores other keys", () => {
    expect(moved({ x: 0.5, y: 0.5 }, "ArrowLeft", false)).toEqual({ x: 0.48, y: 0.5 });
    expect(moved({ x: 0.5, y: 0.5 }, "ArrowDown", true)).toEqual({ x: 0.5, y: 0.6 });
    expect(moved({ x: 0.5, y: 0.5 }, "Enter", false)).toBeNull();
  });

  it("puts a new item beside the last, or the middle of an empty board", () => {
    expect(nextPlace({})).toEqual({ x: 0.5, y: 0.5 });
    expect(nextPlace({ a: { x: 0.3, y: 0.3 } })).toEqual({ x: 0.42, y: 0.3 });
  });
});

describe("the grades a board offers (ADR-143 Amendment 6)", () => {
  it("a scheme's grades are the opened board's, and none before one is open", () => {
    expect(gradesOf("force-4x3")).toBeUndefined();
    expect(gradesOf("5x5x5")).toBeUndefined();
    offerGrades({ scheme: "force-4x3", source: ["W", "X"], intelligence: ["1"], handling: ["H"] });
    expect(gradesOf("force-4x3")).toEqual({ source: ["W", "X"], intelligence: ["1"], handling: ["H"] });
    offerGrades(null);
    expect(gradesOf("force-4x3")).toEqual({ source: ["W", "X"], intelligence: ["1"], handling: ["H"] });
  });
});
