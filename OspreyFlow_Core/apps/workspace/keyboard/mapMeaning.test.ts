// `meaning()` forgives only what the Conduit's schema reads as absent (rule 15: a comparison that
// forgave more would let the keyboard case pass a template the real Map save refuses).
import { describe, expect, it } from "vitest";

import { meaning } from "./mapMeaning";

const committed = { type: "MENTIONED_IN", from: "area_1", to: "report" };

describe("meaning", () => {
  it("reads a nullable field holding null, and an empty properties object, as absent", () => {
    expect(meaning({ ...committed, when: null, properties: {} })).toEqual(meaning(committed));
    expect(meaning({ ref: "report", match_on: null, properties: { title: { field: "title", transform: null } } }))
      .toEqual(meaning({ ref: "report", properties: { title: { field: "title" } } }));
  });

  it("keeps a null the schema refuses, so it differs from the committed link", () => {
    expect(meaning({ ...committed, properties: null })).not.toEqual(meaning(committed));
    expect(meaning({ ref: "report", on_match: null })).not.toEqual(meaning({ ref: "report" }));
  });

  it("keeps a properties that is not a plain empty object", () => {
    for (const odd of [[], "", 0, false]) {
      expect(meaning({ ...committed, properties: odd })).not.toEqual(meaning(committed));
    }
  });
});
