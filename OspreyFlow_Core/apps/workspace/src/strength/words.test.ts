import { describe, expect, it } from "vitest";

import type { LinkStrength, StrengthInfluencer } from "../../../../packages/schemas/generated";
import { andList, influencerWords, ruleWords, strengthExplanation, strengthValues, triggerWords } from "./words";

// ADR-139 decisions 7 and 9: what an influencer does, and what a link's strength rests on, in words.

const SOURCE = {
  id: "incident-source",
  label: "Evidenced by an assault, disorder or find",
  trigger: { entity_type: "Incident", property: "category", values: ["assault", "disorder", "find"] },
  link_types: ["ROLE_IN", "IN_CONFLICT_WITH"],
  change: "add",
  size: 0.1348,
} as unknown as StrengthInfluencer;

const LABELS: Record<string, string> = { ROLE_IN: "Role in", IN_CONFLICT_WITH: "In conflict with" };

describe("influencer words", () => {
  it("says the links it changes, the change and its size, and what triggers it", () => {
    expect(influencerWords(SOURCE, (t) => LABELS[t] ?? t)).toBe(
      "Role in and In conflict with: adds 0.13 to the score before the curve, when an Incident's category is assault, disorder or find",
    );
  });

  it("says a direct-links influencer always applies", () => {
    expect(triggerWords({ ...SOURCE, trigger: null } as StrengthInfluencer)).toBe("always (these are direct links)");
  });

  it("lists with 'and'", () => {
    expect(andList(["a", "b", "c"])).toBe("a, b and c");
  });
});

const LINK: LinkStrength = {
  edge_id: "e1",
  edge_type: "IN_CONFLICT_WITH",
  base_weight: 0.81,
  strength: 0.87,
  parameter_set: "3/IN_CONFLICT_WITH",
  heavy: 2,
  fixed: null,
  occurrences: 2,
  last_seen: "2025-11-20T00:00:00Z",
  applied: [
    { id: "incident-source", label: "Evidenced by an assault", change: "add", size: 0.1348, layer: "file", record_kind: "Incident" },
  ],
};

describe("strengthExplanation", () => {
  it("names the count against what is heavy, the recency, the rule and version, and the evidencing kind", () => {
    const lines = strengthExplanation(LINK, (t) => LABELS[t] ?? t);
    expect(lines).toEqual([
      "Seen 2 times; 2 is heavy for “In conflict with”.",
      "Last seen on 20 November 2025.",
      "Worked out under weights version 3, the rule for “In conflict with”: stored weight 0.81.",
      "Evidenced by an assault (shipped with OspreyFlow), because an Incident you can see evidences it: adds 0.13 to the score before the curve.",
      "Connection strength 0.87.",
    ]);
  });

  it("says a structural link's fixed strength", () => {
    const lines = strengthExplanation({ ...LINK, fixed: 0.75, heavy: null, applied: [], strength: 0.75, base_weight: 0.75 });
    expect(lines[0]).toBe("A fixed strength of 0.75 for “IN_CONFLICT_WITH”, whatever its count or age.");
    expect(ruleWords("3/default")).toBe("weights version 3, the default rule");
  });
});

describe("strengthValues", () => {
  it("gives each link its strength and each node its strongest link's", () => {
    const ends: Record<string, [string, string]> = { e1: ["a", "b"], e2: ["b", "c"] };
    const found = strengthValues(
      [
        { ...LINK, edge_id: "e1", strength: 0.4 },
        { ...LINK, edge_id: "e2", strength: 0.9 },
      ],
      (id) => ends[id] ?? null,
    );
    expect(found.edges).toEqual({ e1: 0.4, e2: 0.9 });
    expect(found.nodes).toEqual({ a: 0.4, b: 0.9, c: 0.9 });
  });
});
