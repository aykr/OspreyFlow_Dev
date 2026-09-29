// The static half of the keyboard-reachability gap — `apps/workspace/keyboard/registryCoverage.
// test.ts`'s own header has the full incident this pattern already fixed there. This is the same
// check, scoped to this directory's own files rather than to the shared `ALL_REGISTRIES` runtime
// array `actionRegistry.ts` exports.
//
// **Not `ALL_REGISTRIES` directly — found building this file, not assumed in advance.**
// `actionRegistry.ts` self-registers every one of `apps/workspace`'s own eight registries at
// module top level, so merely importing it (which declaring `SETUP_SCREENS_ACTIONS` in
// `actions.ts` requires) populates all eight into this process's own copy of `ALL_REGISTRIES` too
// — there is no per-package scoping in a flat, shared array. Enumerating `ALL_REGISTRIES` here
// the way `apps/workspace`'s own version of this file does would therefore demand this
// directory's own `*.spec.ts` files prove coverage for `apps/workspace`'s own registries as well,
// which nothing here can or should do. Enumerating `defineActionRegistry(` calls actually made in
// this directory's own non-spec `.ts` files (parallel to how `assertedRegistryNames` below already
// scans for `assertAllCovered(` calls) is scoped correctly regardless of what else gets imported.
import { readFileSync, readdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

const KEYBOARD_DIR = dirname(fileURLToPath(import.meta.url));

function namesMatching(pattern: RegExp, predicate: (file: string) => boolean): Set<string> {
  const names = new Set<string>();
  for (const file of readdirSync(KEYBOARD_DIR)) {
    if (!predicate(file)) continue;
    const contents = readFileSync(join(KEYBOARD_DIR, file), "utf8");
    for (const match of contents.matchAll(pattern)) {
      const name = match[1];
      if (name) names.add(name);
    }
  }
  return names;
}

describe("every registry this directory declares has a proving assertAllCovered call", () => {
  const declared = namesMatching(
    /defineActionRegistry\(\s*["'](\w+)["']/g,
    (file) => file.endsWith(".ts") && !file.endsWith(".spec.ts") && !file.endsWith(".test.ts"),
  );
  const asserted = namesMatching(/assertAllCovered\(\s*["'](\w+)["']/g, (file) =>
    file.endsWith(".spec.ts"),
  );

  it.each([...declared])("%s is asserted by some *.spec.ts in this directory", (name) => {
    expect(
      asserted.has(name),
      `${name} is declared in this directory but no *.spec.ts file calls ` +
        `assertAllCovered("${name}", ...) — its own coverage gate never runs.`,
    ).toBe(true);
  });

  it("this directory declares at least one registry", () => {
    expect(declared.size).toBeGreaterThan(0);
  });
});
