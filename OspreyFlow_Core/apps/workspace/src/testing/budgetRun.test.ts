// The performance-budget tests run on their own, after the rest of `npm test`
// (`vitest.config.ts`'s `exclude` has why), and are never dropped from both runs by the split. Each
// case fails for one way the split could go wrong: a budget file left in the parallel run (timed
// against 369 neighbours, as CI run 43426503300 was), a budget file in neither run, a budget run
// that is parallel, an `npm test` that never starts it, or a timed case written in an ordinary test
// file, where the parallel run times its neighbours (`settledAnchor.test.ts` read 1535 ms against
// its 1000 ms in `make test` on a loaded server, 14 November 2026).
import { readdirSync, readFileSync } from "node:fs";
import { join, relative } from "node:path";

import { describe, expect, it } from "vitest";

import budget from "../../vitest.budget.config";
import base, { BUDGET_TESTS } from "../../vitest.config";

const ROOT = join(__dirname, "..", "..");
const IS_BUDGET_FILE = /\.budget\.test\.tsx?$/;
const IS_TEST_FILE = /\.test\.tsx?$/;
/** A case that reads the clock to time the code under test. */
const READS_THE_CLOCK = /\bperformance\.now\s*\(/;

/** The test files, outside the budget run, that time something; each must move to a budget file. */
export function timedOutsideBudget(files: ReadonlyMap<string, string>): string[] {
  return [...files]
    .filter(([name, text]) => IS_TEST_FILE.test(name) && !IS_BUDGET_FILE.test(name) && READS_THE_CLOCK.test(text))
    .map(([name]) => name);
}

function testFilesUnderSrc(): Map<string, string> {
  return new Map(
    readdirSync(join(ROOT, "src"), { recursive: true, encoding: "utf8" })
      .filter((name) => IS_TEST_FILE.test(name))
      .map((name) => [join("src", name), readFileSync(join(ROOT, "src", name), "utf8")]),
  );
}

function budgetFiles(): string[] {
  return readdirSync(join(ROOT, "src"), { recursive: true, encoding: "utf8" })
    .filter((name) => IS_BUDGET_FILE.test(name))
    .map((name) => relative(ROOT, join(ROOT, "src", name)));
}

describe("the performance-budget tests run alone", () => {
  it("names every budget file under src/, the folder its pattern covers", () => {
    expect(BUDGET_TESTS).toBe("src/**/*.budget.test.{ts,tsx}");
    const files = budgetFiles();
    expect(files).toContain(
      join("src", "matrix", "MatrixView.budget.test.tsx"),
    );
    for (const file of files)
      expect(file.startsWith("src/"), file).toBe(true);
  });

  it("leaves them out of the parallel run", () => {
    expect(base.test?.exclude).toContain(BUDGET_TESTS);
  });

  it("runs exactly them in the budget run, one file at a time", () => {
    expect(budget.test?.include).toEqual([BUDGET_TESTS]);
    expect(budget.test?.exclude ?? []).not.toContain(BUDGET_TESTS);
    expect(budget.test?.fileParallelism).toBe(false);
  });

  it("is started by npm test, after the parallel run", () => {
    const pkg = JSON.parse(
      readFileSync(join(ROOT, "package.json"), "utf8"),
    ) as {
      scripts: Record<string, string>;
    };
    expect(pkg.scripts.test).toBe(
      "vitest run && vitest run --config vitest.budget.config.ts",
    );
  });

  it("has no timed case left in the parallel run", () => {
    expect(timedOutsideBudget(testFilesUnderSrc())).toEqual([]);
  });

  it("finds a timed case in an ordinary test file, in the shape the timed cases are written", () => {
    // The clock's name is built, so this file does not read as timed to the case above.
    const clock = ["performance", "now"].join(".");
    const timed = [
      `    const start = ${clock}();`,
      "    settledAnchors(nodes, edges, settled);",
      `    expect(${clock}() - start).toBeLessThan(1000);`,
    ].join("\n");
    const files = new Map([
      [join("src", "canvas", "settledAnchor.test.ts"), timed],
      [join("src", "canvas", "settledAnchor.budget.test.ts"), timed],
      [join("src", "canvas", "settledAnchor.ts"), timed],
      [join("src", "canvas", "untimed.test.tsx"), "expect(anchors.size).toBe(0);"],
    ]);
    expect(timedOutsideBudget(files)).toEqual([join("src", "canvas", "settledAnchor.test.ts")]);
  });
});
