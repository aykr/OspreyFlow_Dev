/**
 * The alert monitoring page's plain helpers are held to the shared package's (slice GR3a; scenario AM1).
 *
 * `server/views/alertMonitoringWords.ts` writes a few functions once more than `packages/glass-shared` has them (`formatNumber`,
 * `plural`, `formatDay`, `typologyLabel`, `closingReasonLabel`, and the React board's `groupName`), because the server's `NodeNext`
 * build cannot import the shared package's extension-less source (`studioShared.test.ts` says why at greater length). This test is
 * what keeps the copies honest: each is run on the same inputs as the shared one, and a copy that drifts is red; the planted case at
 * the end shows the comparison itself can fail (rule 15).
 */
import { beforeAll, describe, expect, it } from "vitest";

import { closingReasonLabel, formatDay, formatNumber, groupName, plural, typologyLabel } from "../../server/views/alertMonitoringWords.js";

interface Shared {
  formatNumber(n: number): string;
  plural(n: number, one: string, many?: string): string;
  formatDay(iso: string): string;
  typologyLabel(typology: string | null | undefined): string;
  closingReasonLabel(reason: string | null | undefined): string;
  TYPOLOGY_LABELS: Record<string, string>;
  CLOSING_REASONS: Record<string, string>;
}

const SHARED = "@ospreyflow/glass-shared";
let shared: Shared;
beforeAll(async () => {
  shared = (await import(/* @vite-ignore */ SHARED)) as Shared;
});

describe("the alert monitoring page's helpers answer as the shared package's do", () => {
  it("AM1: formatNumber, plural and formatDay say what the shared ones say", () => {
    for (const n of [0, 1, 2, 999, 1000, 1234567]) {
      expect(formatNumber(n)).toBe(shared.formatNumber(n));
      expect(plural(n, "alert")).toBe(shared.plural(n, "alert"));
      expect(plural(n, "match", "matches")).toBe(shared.plural(n, "match", "matches"));
    }
    for (const iso of ["2026-11-09", "2026-11-23T09:00:00Z", "2026-01-01T00:00:00+05:00", "not a day", ""]) {
      expect(formatDay(iso)).toBe(shared.formatDay(iso));
    }
  });

  it("AM1: every typology and closing reason the shared package names is said the same, and one it does not know as the shared one says it", () => {
    for (const key of [...Object.keys(shared.TYPOLOGY_LABELS), "unknown_kind", "", null, undefined]) {
      expect(typologyLabel(key)).toBe(shared.typologyLabel(key));
    }
    for (const key of [...Object.keys(shared.CLOSING_REASONS), "something_new", "", null, undefined]) {
      expect(closingReasonLabel(key)).toBe(shared.closingReasonLabel(key));
    }
  });

  it("AM1: a rule group is said as the React board says it", () => {
    expect(groupName("typology", "rapid_movement")).toBe("Rapid movement");
    expect(groupName("typology", "")).toBe("Alert");
    expect(groupName("hotlists", "")).toBe("Hotlists");
    expect(groupName("monitors", "")).toBe("Monitors");
    expect(groupName("drawn_items", "")).toBe("Drawn items");
    expect(groupName("new_kind_of_rule", "")).toBe("New kind of rule");
  });

  it("AM1: the comparison can fail: a copy with one label changed is not the shared one", () => {
    const drifted = (key: string): string => (key === "structuring" ? "Structured" : typologyLabel(key));
    expect(drifted("structuring")).not.toBe(shared.typologyLabel("structuring"));
  });
});
