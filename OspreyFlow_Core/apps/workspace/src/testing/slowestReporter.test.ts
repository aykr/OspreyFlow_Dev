// The slowest-tests list every vitest run ends with (admin's T1 part 1): the N slowest by their own duration,
// slowest first, each named by its file and full name. Red if the list is missing, unsorted, uncapped, or
// leaves out a test whose duration is the largest.
import { describe, expect, it } from "vitest";

import { slowestLines } from "./slowestReporter";

// The shape vitest 5 hands onTestRunEnd: a module with relativeModuleId and children.allTests() of test cases
// whose diagnostic() carries the duration (undefined for one not run).
function module(id: string, tests: [string, number | undefined][]) {
  return {
    relativeModuleId: id,
    children: {
      *allTests() {
        for (const [fullName, duration] of tests)
          yield { fullName, diagnostic: () => (duration === undefined ? undefined : { duration }) };
      },
    },
  };
}

describe("the slowest-tests list", () => {
  it("names the slowest first, by file and full name, and leaves out tests not run", () => {
    const lines = slowestLines(
      [module("src/a.test.ts", [["a > quick", 3], ["a > slow", 900]]), module("src/b.test.ts", [["b > mid", 120], ["b > skipped", undefined]])],
      30,
    );
    expect(lines).toEqual([
      "Slowest 3 tests:",
      "   900 ms  src/a.test.ts > a > slow",
      "   120 ms  src/b.test.ts > b > mid",
      "     3 ms  src/a.test.ts > a > quick",
    ]);
  });

  it("keeps only the N slowest", () => {
    const many = Array.from({ length: 40 }, (_, i) => [`t${i}`, i] as [string, number]);
    const lines = slowestLines([module("src/m.test.ts", many)], 30);
    expect(lines).toHaveLength(31);
    expect(lines[0]).toBe("Slowest 30 of 40 tests:");
    expect(lines[1]).toContain("t39");
    expect(lines.at(-1)).toContain("t10");
  });

  it("says nothing when no test ran", () => {
    expect(slowestLines([], 30)).toEqual([]);
  });
});
