import { describe, expect, it } from "vitest";

import { describeValueIcon, valueIconFor } from "./valueIcons";

// ADR-128 Decision 4 (B7): an entity type may name one enum property and map some of its values to
// drawings. These tests are the pure half: which drawing a node's properties give, if any.

const ENDPOINT = {
  property: "endpoint_kind",
  icons: { msisdn: "phone", handle: "keypad", account: "account" },
} as const;

describe("the icon a node's property value gives", () => {
  it("is the drawing mapped to the value, with the value it was read from", () => {
    expect(valueIconFor(ENDPOINT, { endpoint_kind: "handle" })).toEqual({ glyph: "keypad", value: "handle" });
    expect(valueIconFor(ENDPOINT, { endpoint_kind: "msisdn" })).toEqual({ glyph: "phone", value: "msisdn" });
  });

  it("is none for a value the map leaves out, so the type's icon is drawn", () => {
    expect(valueIconFor(ENDPOINT, { endpoint_kind: "email" })).toBeNull();
  });

  it("is none for a node without the property, or with no properties at all", () => {
    expect(valueIconFor(ENDPOINT, { value_raw: "x" })).toBeNull();
    expect(valueIconFor(ENDPOINT, undefined)).toBeNull();
  });

  it("is none for a value that is not text", () => {
    expect(valueIconFor(ENDPOINT, { endpoint_kind: 3 })).toBeNull();
    expect(valueIconFor(ENDPOINT, { endpoint_kind: ["handle"] })).toBeNull();
    expect(valueIconFor(ENDPOINT, { endpoint_kind: null })).toBeNull();
  });

  it("is none for a type with no rule", () => {
    expect(valueIconFor(null, { endpoint_kind: "handle" })).toBeNull();
    expect(valueIconFor(undefined, { endpoint_kind: "handle" })).toBeNull();
  });

  it("does not read an inherited name as a mapped value", () => {
    // The shape a loaded node can have: a value spelled like an Object property.
    for (const value of ["constructor", "toString", "__proto__", "hasOwnProperty"]) {
      expect(valueIconFor(ENDPOINT, { endpoint_kind: value })).toBeNull();
    }
  });

  it("reads only the map's own keys, so a name an object inherits that is text is not a hit", () => {
    // `constructor` and the rest are functions, which the text check refuses anyway; a prototype that
    // does carry text is the case only the own-key check refuses.
    const inherited = Object.create({ handle: "keypad" }) as Record<string, string>;
    expect(valueIconFor({ property: "endpoint_kind", icons: inherited }, { endpoint_kind: "handle" })).toBeNull();
  });

  it("is none when the mapped name is not a drawing the Glass has", () => {
    expect(valueIconFor({ property: "k", icons: { a: "not-an-icon" } }, { k: "a" })).toBeNull();
  });
});

describe("saying what an icon means", () => {
  it("names the drawing, the type, the property and the value, in words", () => {
    expect(describeValueIcon("Endpoint", "endpoint_kind", "handle", "keypad")).toBe(
      "Keypad: Endpoint, endpoint kind handle",
    );
    expect(describeValueIcon("Incident", "category", "throw_over", "parcel-over-wall")).toBe(
      "Parcel over wall: Incident, category throw over",
    );
  });
});
