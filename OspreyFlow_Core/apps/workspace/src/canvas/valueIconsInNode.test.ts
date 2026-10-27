// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { makeNode } from "../testing/fixtures";
import { forgetEntityPictures, setEntityPictureForTest } from "./entityPictures";
import { forgetIconChoicesForTest, setIconChoice } from "./iconChoices";
import { computeNodeGraphAttributes } from "./nodeAttributes";

// ADR-128 Decision 4 (B7), at the place a node's picture is made: a value icon is drawn for its
// value only, a node without the property draws the type's icon, the order of precedence holds, and
// shape and colour stay the type's.

const STATE = { dimmed: false, filteredOut: false, hovered: false, selected: false, onPath: false };
const ENDPOINT = {
  channel: "cyan",
  shape: "hexagon",
  icon: "device",
  iconByValue: { property: "endpoint_kind", icons: { msisdn: "phone", handle: "keypad", account: "account" } },
} as const;
const PHOTO = "data:image/png;base64,iVBORw0KGgo=";

function svg(uri: string): string {
  return decodeURIComponent(uri.replace(/^data:image\/svg\+xml;utf8,/, ""));
}
const endpoint = (id: string, properties: Record<string, unknown>) => makeNode(id, { type: "Endpoint", properties });
const imageOf = (id: string, properties: Record<string, unknown>) =>
  svg(computeNodeGraphAttributes(endpoint(id, properties), ENDPOINT, STATE).image);
const plainOf = (id: string, properties: Record<string, unknown>) =>
  svg(computeNodeGraphAttributes(endpoint(id, properties), ENDPOINT, STATE).imagePlain);
// A picture is the type's if it is what a node with no property draws.
const TYPE_ICON = () => imageOf("t", {});

beforeEach(() => {
  localStorage.clear();
  forgetIconChoicesForTest();
  forgetEntityPictures();
});
afterEach(() => {
  forgetIconChoicesForTest();
  forgetEntityPictures();
});

describe("a value icon in a node's picture", () => {
  it("is drawn for its value, and differs from the type's icon and from another value's", () => {
    const handle = imageOf("a", { endpoint_kind: "handle" });
    const msisdn = imageOf("b", { endpoint_kind: "msisdn" });
    expect(handle).toContain("<g ");
    expect(handle).not.toBe(TYPE_ICON());
    expect(msisdn).not.toBe(TYPE_ICON());
    expect(handle).not.toBe(msisdn);
  });

  it("is drawn for its value only: another value, or none mapped, draws the type's icon", () => {
    expect(imageOf("a", { endpoint_kind: "email" })).toBe(TYPE_ICON());
    expect(imageOf("a", { endpoint_kind: "ip" })).toBe(TYPE_ICON());
  });

  it("is not drawn for a node without the property, or with no properties", () => {
    expect(imageOf("a", { value_raw: "x" })).toBe(TYPE_ICON());
    const bare = computeNodeGraphAttributes(makeNode("z", { type: "Endpoint" }), ENDPOINT, STATE).image;
    expect(svg(bare)).toBe(TYPE_ICON());
  });

  it("is not drawn for a type that has no rule, whatever its properties hold", () => {
    const person = { channel: "indigo", shape: "circle", icon: "person" } as const;
    const withKind = makeNode("p", { properties: { endpoint_kind: "handle" } });
    const without = makeNode("q");
    expect(svg(computeNodeGraphAttributes(withKind, person, STATE).image)).toBe(
      svg(computeNodeGraphAttributes(without, person, STATE).image),
    );
  });

  it("keeps the type's shape and colour: only the drawing inside changes", () => {
    const a = computeNodeGraphAttributes(endpoint("a", { endpoint_kind: "handle" }), ENDPOINT, STATE);
    const b = computeNodeGraphAttributes(endpoint("b", {}), ENDPOINT, STATE);
    expect(a.color).toBe(b.color);
    const shapeOnly = (uri: string) => svg(uri).replace(/<g [\s\S]*<\/g>/, "");
    expect(shapeOnly(a.image)).toBe(shapeOnly(b.image));
  });

  it("is not in the plain picture drawn below the neighbourhood band, which has no icon", () => {
    expect(plainOf("a", { endpoint_kind: "handle" })).not.toContain("<g ");
    expect(plainOf("a", { endpoint_kind: "handle" })).toBe(plainOf("b", {}));
  });
});

describe("the order of precedence in a node's picture", () => {
  const handle = { endpoint_kind: "handle" };

  it("is the value icon over the type's icon", () => {
    expect(imageOf("a", handle)).not.toBe(TYPE_ICON());
  });

  it("gives the analyst's per-type drawing over the value icon, for every value of the type", () => {
    const valueIcon = imageOf("a", handle);
    setIconChoice("Endpoint", { kind: "glyph", name: "shield" });
    expect(imageOf("a", handle)).not.toBe(valueIcon);
    expect(imageOf("a", handle)).toBe(imageOf("b", { endpoint_kind: "msisdn" }));
    expect(imageOf("a", handle)).toBe(TYPE_ICON());
    expect(imageOf("a", handle)).toContain("<g ");
  });

  it("gives the analyst's no-icon choice over the value icon", () => {
    setIconChoice("Endpoint", { kind: "none" });
    expect(imageOf("a", handle)).not.toContain("<g ");
  });

  it("gives the entity's own picture over everything", () => {
    setIconChoice("Endpoint", { kind: "glyph", name: "shield" });
    setEntityPictureForTest("pic", PHOTO);
    const out = imageOf("pic", handle);
    expect(out).toContain("<image ");
    expect(imageOf("other", handle)).not.toContain("<image ");
  });
});
