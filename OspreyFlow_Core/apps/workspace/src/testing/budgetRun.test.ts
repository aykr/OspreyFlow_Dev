// The performance-budget tests run on their own, after the rest of `npm test`
// (`vitest.config.ts`'s `exclude` has why), and are never dropped from both runs by the split. Each
// case fails for one way the split could go wrong: a budget file left in the parallel run (timed
// against 369 neighbours, as CI run 43426503300 was), a budget file in neither run, a budget run
// that is parallel, or an `npm test` that never starts it.
import { readdirSync, readFileSync } from "node:fs";
import { join, relative } from "node:path";

import { describe, expect, it } from "vitest";

import budget from "../../vitest.budget.config";
import base, { BUDGET_TESTS } from "../../vitest.config";

const ROOT = join(__dirname, "..", "..");
const IS_BUDGET_FILE = /\.budget\.test\.tsx?$/;

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
});
