import { describe, expect, it } from "vitest";

import type { Node } from "../../../../packages/schemas/generated";
import { labelIsLiteral, labelStartX, middleTruncate, NODE_LABEL_MAX_CHARS } from "./nodeLabel";

// ADR-097 step 2, design review item 9: labels at `--fs-12`, an identifier in mono (DESIGN.md §9
// exception 3: mono means a literal value, safe to copy), cut in the middle at 24 characters, and
// never drawn past the canvas's edge.

const node = (type: string, properties: Record<string, unknown>): Node =>
  ({ id: `${type}-1`, type, properties }) as unknown as Node;

// DESIGN.md v0.3 §5a (ADR-115 decision 9): a label of 28 characters or fewer is drawn whole; a longer
// one keeps its first 19 characters and its last 4, with an ellipsis between — 24 in all.
describe("middleTruncate", () => {
  it("leaves a label of 28 characters or fewer as it is", () => {
    expect(NODE_LABEL_MAX_CHARS).toBe(28);
    expect(middleTruncate("a".repeat(28))).toBe("a".repeat(28));
  });

  it("keeps a longer one's first 19 and last 4 characters, with an ellipsis between", () => {
    const cut = middleTruncate("email:enron-ev-6be2a8f1c3d4e5f6a7b890c7");
    expect(cut).toBe("email:enron-ev-6be2…90c7");
    expect(Array.from(cut)).toHaveLength(24);
  });
});

describe("labelIsLiteral", () => {
  const identifiersOf = (type: string) => (type === "Phone" ? ["value_normalised", "msisdn"] : []);

  it("is true for a node named by its normalised value or by its id", () => {
    expect(labelIsLiteral(node("Phone", { value_normalised: "+441632960001" }), identifiersOf, {})).toBe(true);
    expect(labelIsLiteral(node("Thing", {}), identifiersOf, {})).toBe(true);
  });

  it("is false for a thing named by its name or a document by its title", () => {
    expect(labelIsLiteral(node("Organisation", { name: "BPA" }), identifiersOf, {})).toBe(false);
    expect(labelIsLiteral(node("Document", { title: "Urgent", value_normalised: "email:1" }), identifiersOf, {})).toBe(false);
  });

  it("is false for a person named by family and given names", () => {
    expect(labelIsLiteral(node("Person", { family_name: "Volkov", given_names: "Anna" }), identifiersOf, {})).toBe(false);
  });

  it("follows the analyst's chosen property: literal when it is one of the type's identifiers", () => {
    const n = node("Phone", { msisdn: "441632960001", nickname: "work" });
    expect(labelIsLiteral(n, identifiersOf, { Phone: "msisdn" })).toBe(true);
    expect(labelIsLiteral(n, identifiersOf, { Phone: "nickname" })).toBe(false);
  });
});

describe("labelStartX", () => {
  it("puts the label to the right of the node when it fits", () => {
    expect(labelStartX({ x: 100, size: 10, textWidth: 60, canvasWidth: 400 })).toBe(113);
  });

  it("puts it to the left when the right would run past the canvas edge", () => {
    expect(labelStartX({ x: 380, size: 10, textWidth: 60, canvasWidth: 400 })).toBe(380 - 10 - 3 - 60);
  });

  it("never starts before the left edge either", () => {
    expect(labelStartX({ x: 20, size: 10, textWidth: 300, canvasWidth: 310 })).toBeGreaterThanOrEqual(0);
  });
});
