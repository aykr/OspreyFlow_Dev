import { describe, expect, it } from "vitest";

import type { LinkChangeRecord, LinkSnapshot } from "./linkChangeApi";
import { describeChange } from "./describeChange";

const base: LinkSnapshot = { type: "ASSOCIATE_OF", properties: {}, interval: null, occurrences: 3 };

function record(before: LinkSnapshot, after: LinkSnapshot): LinkChangeRecord {
  return {
    id: "c1",
    investigation_id: "inv-1",
    edge_id: "e2",
    previous_edge_id: "e1",
    changed_by: "analyst-1",
    changed_at: "2026-10-01T09:00:00Z",
    reason: "Told so",
    before,
    after,
  };
}

describe("describeChange", () => {
  it("says what the type was and became", () => {
    expect(describeChange(record(base, { ...base, type: "FAMILY_OF" }))).toEqual([
      "Type: Associate of → Family of",
    ]);
  });

  it("says each property that was added, changed or removed", () => {
    const lines = describeChange(
      record(
        { ...base, properties: { relation: "cousin", note: "x" } },
        { ...base, properties: { relation: "sister", amount: 5 } },
      ),
    );
    expect(lines).toEqual(["amount: (none) → 5", "note: x → (none)", "relation: cousin → sister"]);
  });

  it("says the records behind it and the dates", () => {
    const lines = describeChange(
      record(
        base,
        {
          ...base,
          occurrences: 7,
          interval: { valid_from: "2026-03-01T00:00:00Z", valid_to: null },
        },
      ),
    );
    expect(lines).toEqual(["Records behind it: 3 → 7", "Dates: none → 2026-03-01 – present"]);
  });

  it("reads a list property as one comma-separated value", () => {
    const lines = describeChange(
      record({ ...base, properties: { tags: ["a"] } }, { ...base, properties: { tags: ["a", "b"] } }),
    );
    expect(lines).toEqual(["tags: a → a, b"]);
  });

  it("says nothing for what did not change", () => {
    expect(describeChange(record(base, base))).toEqual([]);
  });
});
