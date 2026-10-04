import { describe, expect, it } from "vitest";

import type { EdgeTypeDef } from "../../../../packages/schemas/generated";
import { makeEdge } from "../testing/fixtures";
import {
  basisChoicesFor,
  initialDraft,
  retypeDraft,
  toChangeInput,
  typesFor,
  type LinkDraft,
} from "./linkChangeForm";

const EDGE_TYPES: EdgeTypeDef[] = [
  { name: "ASSOCIATE_OF", from: ["Person"], to: ["Person"], directed: false },
  {
    name: "FAMILY_OF",
    from: ["Person"],
    to: ["Person"],
    directed: false,
    properties: [{ name: "relation", type: "string", required: true }],
  },
  { name: "MEMBER_OF", from: ["Person"], to: ["Organisation"] },
  {
    name: "TRANSACTED",
    from: ["Person"],
    to: ["Person"],
    temporal: true,
    properties: [
      { name: "amount", type: "float" },
      { name: "kind", type: "enum", values: ["CASH_IN", "CASH_OUT"] },
      { name: "tags", type: "string[]" },
      { name: "count", type: "integer" },
      { name: "flagged", type: "boolean" },
    ],
  },
  { name: "SAME_AS", from: ["*"], to: ["*"], system: true },
  { name: "NOT_SAME_AS", from: ["*"], to: ["*"], system: true },
];

const link = makeEdge("e1", "a", "b", { type: "ASSOCIATE_OF", occurrences: 3 });
const REASON = "Told so";

function draft(over: Partial<LinkDraft> = {}): LinkDraft {
  return { ...initialDraft(link), reason: REASON, ...over };
}

describe("typesFor", () => {
  it("offers the types that join these two kinds of entity, and never a same-as type", () => {
    expect(typesFor(EDGE_TYPES, "Person", "Person").map((t) => t.name)).toEqual([
      "ASSOCIATE_OF",
      "FAMILY_OF",
      "TRANSACTED",
    ]);
    expect(typesFor(EDGE_TYPES, "Person", "Organisation").map((t) => t.name)).toEqual(["MEMBER_OF"]);
  });

  it("takes a wildcard end as joining anything", () => {
    const any: EdgeTypeDef[] = [{ name: "MENTIONED_IN", from: ["*"], to: ["Document"] }];
    expect(typesFor(any, "Person", "Document")).toHaveLength(1);
    expect(typesFor(any, "Person", "Person")).toHaveLength(0);
  });
});

describe("initialDraft", () => {
  it("starts from the link as it is, with no reason", () => {
    const d = initialDraft(
      makeEdge("e2", "a", "b", {
        type: "TRANSACTED",
        occurrences: 2,
        properties: { amount: 12.5, tags: ["x", "y"], flagged: true },
        interval: { valid_from: "2026-03-01T00:00:00Z", valid_to: "2026-03-09T00:00:00Z" },
      }),
    );
    expect(d).toEqual({
      type: "TRANSACTED",
      properties: { amount: "12.5", tags: "x, y", flagged: "true" },
      occurrences: "2",
      validFrom: "2026-03-01",
      validTo: "2026-03-09",
      reason: "",
      basis: "",
    });
  });
});

describe("toChangeInput", () => {
  it("is nothing to save when nothing differs", () => {
    expect(toChangeInput(link, draft(), EDGE_TYPES)).toEqual({ kind: "nothing" });
  });

  it("sends only what changed, with the reason", () => {
    const result = toChangeInput(link, draft({ occurrences: "7" }), EDGE_TYPES);
    expect(result).toEqual({ kind: "change", input: { reason: REASON, occurrences: 7 } });
  });

  it("sends a new type with the properties it declares", () => {
    const d = retypeDraft(draft(), "FAMILY_OF", EDGE_TYPES);
    d.properties.relation = "cousin";
    expect(toChangeInput(link, d, EDGE_TYPES)).toEqual({
      kind: "change",
      input: { reason: REASON, type: "FAMILY_OF", properties: { relation: "cousin" } },
    });
  });

  it("drops a property the new type does not declare when the type is changed", () => {
    const withProp = makeEdge("e3", "a", "b", { type: "FAMILY_OF", properties: { relation: "cousin" } });
    const d = retypeDraft({ ...initialDraft(withProp), reason: REASON }, "ASSOCIATE_OF", EDGE_TYPES);
    const result = toChangeInput(withProp, d, EDGE_TYPES);
    expect(result).toEqual({
      kind: "change",
      input: { reason: REASON, type: "ASSOCIATE_OF", properties: {} },
    });
  });

  it("requires a reason", () => {
    expect(toChangeInput(link, draft({ occurrences: "7", reason: "   " }), EDGE_TYPES)).toEqual({
      kind: "problem",
      message: "Say why the link is being changed.",
    });
  });

  it("refuses a missing required property, naming it", () => {
    const d = retypeDraft(draft(), "FAMILY_OF", EDGE_TYPES);
    expect(toChangeInput(link, d, EDGE_TYPES)).toEqual({
      kind: "problem",
      message: "relation is required for Family of.",
    });
  });

  it("refuses records behind it that are not a whole number of at least one", () => {
    for (const bad of ["0", "-2", "1.5", "many", ""]) {
      const r = toChangeInput(link, draft({ occurrences: bad }), EDGE_TYPES);
      expect(r).toMatchObject({ kind: "problem" });
    }
  });

  it("turns each kind of property into the value the server expects", () => {
    const base = makeEdge("e4", "a", "b", { type: "TRANSACTED", occurrences: 1 });
    const d: LinkDraft = {
      ...initialDraft(base),
      reason: REASON,
      properties: { amount: "12.5", kind: "CASH_IN", tags: "x, y ,", count: "4", flagged: "true" },
    };
    expect(toChangeInput(base, d, EDGE_TYPES)).toEqual({
      kind: "change",
      input: {
        reason: REASON,
        properties: { amount: 12.5, kind: "CASH_IN", tags: ["x", "y"], count: 4, flagged: true },
      },
    });
  });

  it("refuses a number that is not one, naming the property", () => {
    const base = makeEdge("e4", "a", "b", { type: "TRANSACTED" });
    const d: LinkDraft = {
      ...initialDraft(base),
      reason: REASON,
      properties: { amount: "twelve" },
    };
    expect(toChangeInput(base, d, EDGE_TYPES)).toEqual({
      kind: "problem",
      message: "amount must be a number.",
    });
  });

  it("sets a validity period, and clears it when the start is emptied", () => {
    const base = makeEdge("e4", "a", "b", { type: "TRANSACTED" });
    const set = toChangeInput(base, { ...initialDraft(base), reason: REASON, validFrom: "2026-03-01" }, EDGE_TYPES);
    expect(set).toEqual({
      kind: "change",
      input: { reason: REASON, interval: { valid_from: "2026-03-01T00:00:00Z", valid_to: null } },
    });
    const dated = makeEdge("e5", "a", "b", {
      type: "TRANSACTED",
      interval: { valid_from: "2026-03-01T00:00:00Z", valid_to: null },
    });
    const cleared = toChangeInput(dated, { ...initialDraft(dated), reason: REASON, validFrom: "" }, EDGE_TYPES);
    expect(cleared).toEqual({ kind: "change", input: { reason: REASON, interval: null } });
  });

  it("refuses an end date with no start date", () => {
    const base = makeEdge("e4", "a", "b", { type: "TRANSACTED" });
    expect(toChangeInput(base, { ...initialDraft(base), reason: REASON, validTo: "2026-03-09" }, EDGE_TYPES)).toEqual({
      kind: "problem",
      message: "A validity period needs a start date.",
    });
  });

  it("refuses an end date before the start date", () => {
    const base = makeEdge("e4", "a", "b", { type: "TRANSACTED" });
    const d = { ...initialDraft(base), reason: REASON, validFrom: "2026-03-09", validTo: "2026-03-01" };
    expect(toChangeInput(base, d, EDGE_TYPES)).toEqual({
      kind: "problem",
      message: "The end date is before the start date.",
    });
  });

  it("refuses a reason over the server's limit", () => {
    const r = toChangeInput(link, draft({ occurrences: "7", reason: "x".repeat(1001) }), EDGE_TYPES);
    expect(r).toEqual({ kind: "problem", message: "A reason can be at most 1000 characters." });
  });
});

// ADR-081 step B (Amendment 2): the form asks what stands behind the link, with no default, and
// offers Direct only where the link's type is Direct and the link is not already probabilistic.
describe("the basis question", () => {
  const BASIS_TYPES: EdgeTypeDef[] = [
    { name: "ASSOCIATE_OF", from: ["Person"], to: ["Person"], basis: "direct" },
    { name: "FAMILY_OF", from: ["Person"], to: ["Person"], basis: "direct" },
    { name: "LIKELY_ASSOCIATE_OF", from: ["Person"], to: ["Person"], basis: "probabilistic" },
  ];
  const direct = makeEdge("e1", "a", "b", { type: "ASSOCIATE_OF", occurrences: 3 });
  const marked = makeEdge("e2", "a", "b", { type: "ASSOCIATE_OF", occurrences: 3, basis: "probabilistic" });
  const likely = makeEdge("e3", "a", "b", { type: "LIKELY_ASSOCIATE_OF", occurrences: 3 });

  it("offers Direct and Probabilistic for a Direct link, Probabilistic alone for a probabilistic one", () => {
    expect(basisChoicesFor(direct, BASIS_TYPES[0])).toEqual(["direct", "probabilistic"]);
    expect(basisChoicesFor(marked, BASIS_TYPES[0])).toEqual(["probabilistic"]);
    expect(basisChoicesFor(likely, BASIS_TYPES[2])).toEqual(["probabilistic"]);
  });

  it("asks nothing for a type with no basis", () => {
    expect(basisChoicesFor(direct, undefined)).toEqual([]);
    expect(basisChoicesFor(direct, { name: "ODD", from: ["Person"], to: ["Person"] })).toEqual([]);
  });

  it("starts with no basis chosen", () => {
    expect(initialDraft(direct).basis).toBe("");
  });

  it("will not save a change until the basis is chosen", () => {
    const outcome = toChangeInput(direct, { ...initialDraft(direct), occurrences: "7", reason: REASON }, BASIS_TYPES);
    expect(outcome).toEqual({ kind: "problem", message: expect.stringMatching(/stands behind/i) });
  });

  it("sends the basis only when it differs from what stands behind the link now", () => {
    const same = toChangeInput(
      direct,
      { ...initialDraft(direct), occurrences: "7", basis: "direct", reason: REASON },
      BASIS_TYPES,
    );
    expect(same).toEqual({ kind: "change", input: { reason: REASON, occurrences: 7 } });
    const mark = toChangeInput(direct, { ...initialDraft(direct), basis: "probabilistic", reason: REASON }, BASIS_TYPES);
    expect(mark).toEqual({ kind: "change", input: { reason: REASON, basis: "probabilistic" } });
  });

  it("is nothing to save when only the basis the link already has is chosen", () => {
    expect(toChangeInput(direct, { ...initialDraft(direct), basis: "direct", reason: REASON }, BASIS_TYPES)).toEqual({
      kind: "nothing",
    });
  });

  it("takes the one possible basis as chosen when there is only one", () => {
    const outcome = toChangeInput(likely, { ...initialDraft(likely), occurrences: "7", reason: REASON }, BASIS_TYPES);
    expect(outcome).toEqual({ kind: "change", input: { reason: REASON, occurrences: 7 } });
  });

  it("keeps a chosen basis when the type changes to one that allows it, and clears it otherwise", () => {
    const chosen = { ...initialDraft(direct), basis: "direct" as const };
    expect(retypeDraft(chosen, "FAMILY_OF", BASIS_TYPES).basis).toBe("direct");
    expect(retypeDraft(chosen, "LIKELY_ASSOCIATE_OF", BASIS_TYPES).basis).toBe("");
  });
});
