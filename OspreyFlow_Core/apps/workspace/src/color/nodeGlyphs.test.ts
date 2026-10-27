import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

import { GLYPH_NAMES, glyphMarkup, hasGlyph } from "./nodeGlyphs";

// ADR-079. The ontology's JSON Schema holds the closed list of icon names; the Glass holds the
// drawings. These tests are the only thing that ties the two together, so a name added to one and
// not the other fails here and not in somebody's browser.

const here = dirname(fileURLToPath(import.meta.url));
const schema = JSON.parse(
  readFileSync(join(here, "../../../../packages/ontology/schema/ontology.schema.json"), "utf8"),
) as { $defs: { entity_type: { properties: { icon: { enum: string[] } } } } };
const SCHEMA_NAMES = schema.$defs.entity_type.properties.icon.enum;

describe("the drawings the ontology may name", () => {
  it("are exactly the names in the ontology's schema, no more and no fewer", () => {
    expect([...GLYPH_NAMES].sort()).toEqual([...SCHEMA_NAMES].sort());
  });

  it("include the six ADR-128 Amendment 3 added for icons chosen by a value, and make twenty-six", () => {
    for (const name of ["keypad", "account", "parcel-over-wall", "clash", "crowd", "magnifier"]) {
      expect(SCHEMA_NAMES).toContain(name);
      expect(hasGlyph(name)).toBe(true);
    }
    expect(SCHEMA_NAMES).toHaveLength(26);
    expect(GLYPH_NAMES).toHaveLength(26);
  });

  it("each have a drawing, and an unknown name has none", () => {
    for (const name of SCHEMA_NAMES) {
      expect(hasGlyph(name)).toBe(true);
      expect(glyphMarkup(name, "#ffffff")).toContain("<");
    }
    expect(hasGlyph("not-an-icon")).toBe(false);
    expect(glyphMarkup("not-an-icon", "#ffffff")).toBeNull();
  });

  it("are drawn in the colour given and in no other, so they follow the node's fill", () => {
    for (const name of SCHEMA_NAMES) {
      const markup = glyphMarkup(name, "#123abc") ?? "";
      expect(markup).not.toContain("currentColor");
      expect(markup).toContain("#123abc");
      expect(markup.match(/#[0-9a-f]{3,8}\b/gi)?.every((hex) => hex === "#123abc")).toBe(true);
    }
  });

  it("use only drawing shapes: nothing that could run, load or reach outside the picture", () => {
    for (const name of SCHEMA_NAMES) {
      const tags = [...(glyphMarkup(name, "#000000") ?? "").matchAll(/<\s*([a-zA-Z]+)/g)].map((m) => m[1]);
      expect(tags.length).toBeGreaterThan(0);
      for (const tag of tags) expect(["path", "circle", "rect", "ellipse"]).toContain(tag);
      expect(glyphMarkup(name, "#000000")).not.toMatch(/href|on[a-z]+=|url\(/i);
    }
  });
});
