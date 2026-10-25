// ADR-115 E6 (the reference's canvas toolbar): "Last change" names the case's latest history step and
// when, from the same history the History drawer lists; nothing when there is none.
import { describe, expect, it } from "vitest";

import { lastChangeText } from "./lastChange";

const NOW = new Date("2026-10-13T09:00:00Z");

describe("the canvas toolbar's last change", () => {
  it("names the latest step and when, whatever order the steps come in", () => {
    const steps = [
      { id: "s1", label: "Seeded", created_at: "2026-10-08T11:05:00Z" },
      { id: "s2", label: "Expanded", created_at: "2026-10-12T16:42:00Z" },
    ];
    expect(lastChangeText(steps, NOW)).toBe("Last change: Expanded, yesterday");
  });

  it("is nothing for a case with no history", () => {
    expect(lastChangeText([], NOW)).toBeNull();
  });
});
