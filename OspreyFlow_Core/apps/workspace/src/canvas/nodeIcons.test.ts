// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { makeNode } from "../testing/fixtures";
import { forgetIconChoicesForTest, setIconChoice } from "./iconChoices";
import { computeNodeGraphAttributes } from "./nodeAttributes";

// ADR-079: the picture drawn for a node carries its type's icon, the analyst's choice taking over
// from the ontology's.

const STATE = { dimmed: false, filteredOut: false, hovered: false, selected: false, onPath: false };
const PLAIN = { channel: "indigo", shape: "circle" } as const;
const WITH_ICON = { ...PLAIN, icon: "person" } as const;
const DATA = "data:image/png;base64,iVBORw0KGgo=";

function svg(uri: string): string {
  return decodeURIComponent(uri.replace(/^data:image\/svg\+xml;utf8,/, ""));
}

beforeEach(() => {
  localStorage.clear();
  forgetIconChoicesForTest();
});
afterEach(() => forgetIconChoicesForTest());

describe("the icon in a node's picture", () => {
  it("is the ontology's, drawn inside the shape", () => {
    const withIcon = svg(computeNodeGraphAttributes(makeNode("n1"), WITH_ICON, STATE).image);
    const without = svg(computeNodeGraphAttributes(makeNode("n1"), PLAIN, STATE).image);
    expect(withIcon).toContain("<g ");
    expect(without).not.toContain("<g ");
  });

  it("is the analyst's choice for the type when there is one, and nothing when they chose none", () => {
    setIconChoice("Person", { kind: "glyph", name: "shield" });
    const shield = svg(computeNodeGraphAttributes(makeNode("n1"), WITH_ICON, STATE).image);
    localStorage.clear();
    forgetIconChoicesForTest();
    const person = svg(computeNodeGraphAttributes(makeNode("n1"), WITH_ICON, STATE).image);
    expect(shield).not.toBe(person);
    setIconChoice("Person", { kind: "none" });
    expect(svg(computeNodeGraphAttributes(makeNode("n1"), WITH_ICON, STATE).image)).toBe(
      svg(computeNodeGraphAttributes(makeNode("n1"), PLAIN, STATE).image),
    );
  });

  it("is the analyst's own picture, cut to the shape", () => {
    setIconChoice("Person", { kind: "image", dataUrl: DATA });
    const out = svg(computeNodeGraphAttributes(makeNode("n1"), WITH_ICON, STATE).image);
    expect(out).toContain("<image");
    expect(out).toContain("<clipPath");
  });

  it("is only for the type chosen for: another type keeps the ontology's", () => {
    setIconChoice("Endpoint", { kind: "none" });
    expect(svg(computeNodeGraphAttributes(makeNode("n1"), WITH_ICON, STATE).image)).toContain("<g ");
  });

  it("fades with a dimmed or filtered-out node", () => {
    const full = svg(computeNodeGraphAttributes(makeNode("n1"), WITH_ICON, STATE).image);
    const dim = svg(computeNodeGraphAttributes(makeNode("n1"), WITH_ICON, { ...STATE, dimmed: true }).image);
    const out = svg(computeNodeGraphAttributes(makeNode("n1"), WITH_ICON, { ...STATE, filteredOut: true }).image);
    expect(full).not.toContain("opacity=");
    expect(dim).toMatch(/opacity="0\.\d+"/);
    expect(out).toMatch(/opacity="0\.\d+"/);
    expect(dim).not.toBe(out);
  });
});
