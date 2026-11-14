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
const IS_TEST_FILE = /\.test\.(tsx?|mjs)$/;
/** The folders `npm test`'s parallel run takes test files from (`vitest.config.ts`'s `include`). */
const PARALLEL_FOLDERS = ["src", "keyboard", "compute-tier1"];
/**
 * A case that times the code under test: a monotonic clock read anywhere in the file (`performance
 * .now`, however it is reached, or Node's `hrtime`), or the wall clock compared against a limit on
 * one line. `Date.now()` alone is left alone: the test files use it for expiry stamps and deadline
 * polls, which time nothing. Fake timers are virtual time and time nothing either.
 */
const TIMES_SOMETHING = [
  /\bperformance\.now\s*\(/,
  /\{\s*now\s*\}\s*=\s*performance\b/,
  /\bprocess\.hrtime\b/,
  /\bDate\.now\s*\(.*\btoBeLessThan(OrEqual)?\s*\(/,
];

/**
 * The test files, outside the budget run, that time something. Under `src/`, each moves to a
 * `*.budget.test.*` file; `BUDGET_TESTS` covers `src/` only, so one in `keyboard/` or
 * `compute-tier1/` needs the budget run widened first, not this case relaxed.
 */
export function timedOutsideBudget(files: ReadonlyMap<string, string>): string[] {
  return [...files]
    .filter(
      ([name, text]) =>
        IS_TEST_FILE.test(name) &&
        !IS_BUDGET_FILE.test(name) &&
        TIMES_SOMETHING.some((times) => text.split("\n").some((line) => times.test(line))),
    )
    .map(([name]) => name);
}

function testFilesInTheParallelRun(): Map<string, string> {
  return new Map(
    PARALLEL_FOLDERS.flatMap((folder) =>
      readdirSync(join(ROOT, folder), { recursive: true, encoding: "utf8" })
        .filter((name) => IS_TEST_FILE.test(name) && !name.includes("node_modules"))
        .map((name): [string, string] => [join(folder, name), readFileSync(join(ROOT, folder, name), "utf8")]),
    ),
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
    // Each named, so a budget file deleted takes its timed case out of both runs only by a red here.
    for (const named of [
      join("src", "matrix", "MatrixView.budget.test.tsx"),
      join("src", "canvas", "settledAnchor.budget.test.ts"),
      join("src", "canvas", "communityLinks.budget.test.ts"),
    ])
      expect(files).toContain(named);
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
    expect(timedOutsideBudget(testFilesInTheParallelRun())).toEqual([]);
  });

  it("finds a timed case in an ordinary test file, in each shape a case times something", () => {
    // The clock's names are built, so this file does not read as timed to the case above.
    const perf = ["performance", "now"].join(".");
    const hr = ["process", "hrtime"].join(".");
    const wall = ["Date", "now"].join(".");
    const timed = (start: string, read: string) =>
      [`    const start = ${start};`, "    settledAnchors(nodes, edges, settled);", `    expect(${read} - start).toBeLessThan(1000);`].join("\n");
    const shapes: [string, string][] = [
      ["settledAnchor.test.ts", timed(`${perf}()`, `${perf}()`)],
      ["destructured.test.ts", `    const { now } = ${perf.split(".")[0]};\n${timed("now()", "now()")}`],
      ["hrtime.test.ts", timed(`${hr}.bigint()`, `${hr}.bigint()`)],
      ["wall.test.tsx", timed(`${wall}()`, `${wall}()`)],
      ["tier1.test.mjs", timed(`${perf}()`, `${perf}()`)],
    ];
    const files = new Map<string, string>([
      ...shapes.map(([name, text]): [string, string] => [join("src", "canvas", name), text]),
      [join("src", "canvas", "settledAnchor.budget.test.ts"), timed(`${perf}()`, `${perf}()`)],
      [join("src", "canvas", "settledAnchor.ts"), timed(`${perf}()`, `${perf}()`)],
      [join("src", "canvas", "expiry.test.ts"), `    const expires = ${wall}() + 60_000;\n    expect(expires).toBeGreaterThan(0);`],
      [join("src", "canvas", "untimed.test.tsx"), "expect(anchors.size).toBe(0);"],
    ]);
    expect(timedOutsideBudget(files).sort()).toEqual(shapes.map(([name]) => join("src", "canvas", name)).sort());
  });
});
