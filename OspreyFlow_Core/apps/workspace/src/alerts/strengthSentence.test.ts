// ADR-139 decision 8: a sentence rule's strength blank, from the builder's draft to the server's
// sentence and back, and what stops it being sent unfinished.
import { describe, expect, it } from "vitest";

import { emptyDraft, fromSentence, sentenceSummary, toSentence, unfinished } from "./sentence";

describe("the strength blank", () => {
  it("sends a connection-strength condition and reads it back", () => {
    const draft = { ...emptyDraft("Person"), strength: "connection_strength" as const, strengthLink: "IN_CONFLICT_WITH", strengthOther: "Person", reaches: "0.85" };
    const sentence = toSentence(draft);
    expect((sentence as unknown as { strength: unknown }).strength).toEqual({
      kind: "connection_strength", link_type: "IN_CONFLICT_WITH", other_type: "Person", reaches: 0.85,
    }); // prettier-ignore
    const back = fromSentence(sentence);
    expect([back.strength, back.strengthLink, back.strengthOther, back.reaches]).toEqual([
      "connection_strength", "IN_CONFLICT_WITH", "Person", "0.85",
    ]); // prettier-ignore
    expect(sentenceSummary(sentence)).toContain("the connection strength with a Person by IN_CONFLICT_WITH reaches 0.85");
  });

  it("sends a rarity condition with its scope, and none when the blank is empty", () => {
    const rare = toSentence({ ...emptyDraft("Person"), strength: "shared_attribute_rarity", reaches: "2.5", rarityScope: "case" });
    expect((rare as unknown as { strength: unknown }).strength).toEqual({ kind: "shared_attribute_rarity", reaches: 2.5, scope: "case" });
    expect((toSentence(emptyDraft("Person")) as unknown as { strength: unknown }).strength).toBeNull();
  });

  it("is not sent unfinished: a figure above 0, a strength at most 1, and after commit", () => {
    const base = { ...emptyDraft("Person"), strength: "connection_strength" as const };
    expect(unfinished({ ...base, reaches: "0" })).toMatch(/above 0/);
    expect(unfinished({ ...base, reaches: "1.5" })).toMatch(/at most 1/);
    expect(unfinished({ ...base, reaches: "0.8", runs: "pre_commit" })).toMatch(/after commit/);
    expect(unfinished({ ...base, reaches: "0.8" })).toBeNull();
  });
});
