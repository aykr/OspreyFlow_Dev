// @vitest-environment node
// The keyboard lists' proved set survives a worker restart (CO3e; GitHub run 46012575717, 27 November
// 2026). Playwright replaces a worker after a failed case. The set was kept in the worker's memory, so
// the list at the end of `admin.spec.ts` named 53 actions, nearly all proved in the replaced worker: it
// could not tell "never proved" from "proved before the restart".
//
// Each case is a real Playwright run in a subprocess, with no browser and no server. Its spec takes
// `registerCovered` and `assertAllCovered` from wherever a real spec of the suite takes them, and runs
// under that suite's real `globalSetup`. So what is proved here is what the suites use, and on the
// in-memory set these cases fail for the reason they name.
//
// Which test fails if the invariant is broken (rules 12 and 15):
//  - (a) a proof is lost with its worker: "keeps a proof made in a worker that was replaced";
//  - (b) a registered action with no proving case passes the list: "still names an action no case proved";
//  - a folder an earlier run left behind counts: "never counts a proof an earlier run left behind";
//  - a run with no folder of its own falls back to memory: "refuses in words, with no run folder";
//  - a caller keeps a store of its own: "every caller takes the two from the one store".
import { execFile } from "node:child_process";
import {
  existsSync,
  mkdtempSync,
  readFileSync,
  readdirSync,
  rmSync,
  symlinkSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { afterEach, describe, expect, it } from "vitest";

const KEYBOARD_DIR = dirname(fileURLToPath(import.meta.url));
const CORE = resolve(KEYBOARD_DIR, "../../..");
const HARNESS_KEYBOARD_DIR = join(CORE, "apps/harness/keyboard");
const STORE = join(CORE, "apps/provedActions.ts");
const PLAYWRIGHT = join(CORE, "node_modules/@playwright/test/cli.js");
const SLOW = 120_000; // a subprocess run, beside a unit suite using every core

const SUITES = [
  {
    suite: "the workspace's keyboard suite",
    folder: KEYBOARD_DIR,
    specimen: "admin.spec.ts",
  },
  {
    suite: "the harness's keyboard suite",
    folder: HARNESS_KEYBOARD_DIR,
    specimen: "setup-screens.spec.ts",
  },
] as const;
type Suite = (typeof SUITES)[number];

const BEFORE = "proved-before-the-failure";
const AFTER = "proved-after-the-failure";
const NEVER = "no-case-proves-this";

const NAMED_IMPORT = /\bimport\s*\{([^}]*)\}\s*from\s*["']([^"']+)["']/g;

/** Where `source` imports `name` from, or undefined. */
function importedFrom(source: string, name: string): string | undefined {
  for (const [, names, from] of source.matchAll(NAMED_IMPORT)) {
    if (new RegExp(`\\b${name}\\b`).test(names!)) return from;
  }
  return undefined;
}

/** A specifier as a spec in `folder` writes it, written for a spec anywhere. */
function fromAnywhere(folder: string, specifier: string): string {
  return specifier.startsWith(".")
    ? `${resolve(folder, specifier)}.ts`
    : specifier;
}

const scratch: string[] = [];
afterEach(() => {
  for (const folder of scratch.splice(0))
    rmSync(folder, { recursive: true, force: true });
});

/** A throwaway Playwright project that takes the store as `suite` does. */
function project(suite: Suite, options: { withSetup: boolean }): string {
  const root = mkdtempSync(join(tmpdir(), "osprey-registry-restart-"));
  scratch.push(root);
  symlinkSync(join(CORE, "node_modules"), join(root, "node_modules"), "dir");
  writeFileSync(join(root, "package.json"), '{ "type": "module" }\n');

  const specimen = readFileSync(join(suite.folder, suite.specimen), "utf8");
  const specifier = importedFrom(specimen, "registerCovered");
  expect(
    specifier,
    `${suite.specimen} imports registerCovered`,
  ).toBeDefined();
  expect(importedFrom(specimen, "assertAllCovered")).toBe(specifier);

  writeFileSync(
    join(root, "probe.spec.ts"),
    `import { cpSync } from "node:fs";
import { test } from "@playwright/test";
import { assertAllCovered, registerCovered } from ${JSON.stringify(fromAnywhere(suite.folder, specifier!))};

const REGISTRY = "RESTART_PROBE_ACTIONS";

test("proves one before the failure", () => {
  registerCovered(REGISTRY, "${BEFORE}");
});
test("fails, so Playwright replaces the worker", () => {
  throw new Error("planted failure");
});
test("proves one after the failure", () => {
  registerCovered(REGISTRY, "${AFTER}");
});
test("the list", () => {
  assertAllCovered(REGISTRY, JSON.parse(process.env.PROBE_ACTIONS!));
});
test("keeps a copy of the run's folder, as a run that was killed would leave it", () => {
  cpSync(process.env.OSPREY_PROVED_DIR!, process.env.PROBE_KEEP!, { recursive: true });
  console.log("RUN_FOLDER=" + process.env.OSPREY_PROVED_DIR);
});
`,
  );

  const real = join(suite.folder, "playwright.config.ts");
  writeFileSync(
    join(root, "playwright.config.ts"),
    `import { resolve } from "node:path";
import real from ${JSON.stringify(real)};

const setup = [real.globalSetup ?? []].flat().map((path) => resolve(${JSON.stringify(suite.folder)}, path));

export default {
  testDir: ".",
  testMatch: /probe\\.spec\\.ts$/,
  workers: 1,
  ${options.withSetup ? "globalSetup: setup.length ? setup : undefined," : ""}
};
`,
  );
  return root;
}

interface Case {
  status: string;
  worker: number;
  error: string;
  output: string;
}

interface JsonSuite {
  suites?: JsonSuite[];
  specs?: {
    title: string;
    tests: {
      results: {
        status: string;
        workerIndex: number;
        error?: { message?: string };
        stdout?: { text?: string }[];
      }[];
    }[];
  }[];
}

/** One run of the project; each case that ran, by its title. */
async function run(
  root: string,
  env: Record<string, string>,
  only?: string,
): Promise<Map<string, Case>> {
  const args = [
    PLAYWRIGHT,
    "test",
    "--config",
    join(root, "playwright.config.ts"),
    "--reporter=json",
    ...(only ? ["--grep", only] : []),
  ];
  const stdout = await new Promise<string>((done) => {
    execFile(
      process.execPath,
      args,
      {
        cwd: root,
        encoding: "utf8",
        maxBuffer: 10_000_000,
        env: {
          ...process.env,
          // No port is opened here; the real configs only need a slot to be loaded.
          OSPREY_PORTS_SLOT: process.env.OSPREY_PORTS_SLOT ?? "0",
          FORCE_COLOR: "0",
          ...env,
        },
      },
      // A run with the planted failure exits 1: the report says what happened.
      (_error, out) => done(out),
    );
  });
  const report = JSON.parse(stdout) as {
    suites: JsonSuite[];
    errors: { message?: string }[];
  };
  expect(report.errors, "the run itself had no error").toEqual([]);
  const cases = new Map<string, Case>();
  const walk = (suite: JsonSuite) => {
    for (const spec of suite.specs ?? []) {
      const result = spec.tests[0]!.results[0]!;
      cases.set(spec.title, {
        status: result.status,
        worker: result.workerIndex,
        error: result.error?.message ?? "",
        output: (result.stdout ?? []).map((line) => line.text ?? "").join(""),
      });
    }
    (suite.suites ?? []).forEach(walk);
  };
  report.suites.forEach(walk);
  return cases;
}

const probeEnv = (root: string, actions: string[]) => ({
  PROBE_ACTIONS: JSON.stringify(actions),
  PROBE_KEEP: join(root, "kept"),
});

const unproved = (ids: string[]) =>
  `RESTART_PROBE_ACTIONS: keyboard action(s) registered with no proving test case: ${ids.join(", ")}`;

/** The planted failure did what it is for: the two proofs were made in two workers. */
function expectAReplacedWorker(cases: Map<string, Case>): void {
  expect(cases.get("fails, so Playwright replaces the worker")?.status).toBe(
    "failed",
  );
  const first = cases.get("proves one before the failure")!;
  const second = cases.get("proves one after the failure")!;
  expect([first.status, second.status]).toEqual(["passed", "passed"]);
  expect(second.worker).not.toBe(first.worker);
  expect(cases.get("the list")?.worker).toBe(second.worker);
}

describe.each(SUITES)("$suite", (suite) => {
  it(
    "(a) keeps a proof made in a worker that was replaced",
    async () => {
      const root = project(suite, { withSetup: true });
      const cases = await run(root, probeEnv(root, [BEFORE, AFTER]));
      expectAReplacedWorker(cases);
      expect(cases.get("the list")?.error).toBe("");
      expect(cases.get("the list")?.status).toBe("passed");
    },
    SLOW,
  );

  it(
    "(b) still names an action no case proved, and only that one, across the same restart",
    async () => {
      const root = project(suite, { withSetup: true });
      const cases = await run(root, probeEnv(root, [BEFORE, NEVER, AFTER]));
      expectAReplacedWorker(cases);
      expect(cases.get("the list")?.status).toBe("failed");
      expect(cases.get("the list")?.error).toBe(`Error: ${unproved([NEVER])}`);
    },
    SLOW,
  );

  it(
    "never counts a proof an earlier run left behind, even when the environment points at it",
    async () => {
      const root = project(suite, { withSetup: true });
      const env = probeEnv(root, [BEFORE, AFTER]);
      const first = await run(root, env);
      const kept = first.get(
        "keeps a copy of the run's folder, as a run that was killed would leave it",
      )!;
      expect(kept.error).toBe("");
      const used = /RUN_FOLDER=(.+)/.exec(kept.output)![1]!.trim();
      expect(existsSync(used), "a finished run removes its folder").toBe(false);
      expect(readdirSync(env.PROBE_KEEP).length).toBeGreaterThan(0);

      // The list alone, so nothing is proved in this run.
      const second = await run(
        root,
        { ...env, OSPREY_PROVED_DIR: env.PROBE_KEEP },
        "the list",
      );
      expect([...second.keys()]).toEqual(["the list"]);
      expect(second.get("the list")?.error).toBe(
        `Error: ${unproved([BEFORE, AFTER])}`,
      );
    },
    SLOW,
  );

  it(
    "refuses in words, with no run folder, rather than keeping proofs in memory",
    async () => {
      const root = project(suite, { withSetup: false });
      const cases = await run(
        root,
        { ...probeEnv(root, [BEFORE]), OSPREY_PROVED_DIR: "" },
        "proves one before the failure",
      );
      const proving = cases.get("proves one before the failure")!;
      expect(proving.status).toBe("failed");
      expect(proving.error).toContain("globalSetup");
    },
    SLOW,
  );
});

describe("every caller takes the two from the one store", () => {
  const NAMES = ["registerCovered", "assertAllCovered"];

  /** Whether `specifier`, written in `folder`, reaches the store, directly or by a re-export. */
  function reachesTheStore(folder: string, specifier: string): boolean {
    if (!specifier.startsWith(".")) return false;
    const target = `${resolve(folder, specifier)}.ts`;
    if (target === STORE) return true;
    const source = readFileSync(target, "utf8");
    return [
      ...source.matchAll(/\bexport\s*\{([^}]*)\}\s*from\s*["']([^"']+)["']/g),
    ].some(
      ([, names, from]) =>
        NAMES.every((name) => names!.includes(name)) &&
        resolve(dirname(target), `${from}.ts`) === STORE,
    );
  }

  it.each(SUITES)("$suite", ({ folder }) => {
    let callers = 0;
    const elsewhere: string[] = [];
    for (const file of readdirSync(folder)) {
      if (!file.endsWith(".spec.ts")) continue;
      const source = readFileSync(join(folder, file), "utf8");
      for (const name of NAMES) {
        if (!new RegExp(`^\\s*${name}\\(`, "m").test(source)) continue;
        callers += 1;
        const from = importedFrom(source, name);
        if (from === undefined || !reachesTheStore(folder, from))
          elsewhere.push(`${file}: ${name} from ${from}`);
      }
    }
    expect(callers).toBeGreaterThan(0);
    expect(elsewhere).toEqual([]);
  });

  it("the shared package, which the browser bundles, keeps the declarations and no proved set", async () => {
    const shared = await import("@ospreyflow/glass-shared");
    expect(shared.ALL_REGISTRIES.length).toBeGreaterThan(0);
    expect(Object.keys(shared)).not.toEqual(
      expect.arrayContaining([expect.stringMatching(/Covered/)]),
    );
  });
});
