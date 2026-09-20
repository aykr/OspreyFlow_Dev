// The static half of `CLAUDE.md` rule 13's own gap, exposed by Phase 7 Stage 4's third registry
// (`actionRegistry.ts`'s own module docstring has the full incident). `assertAllCovered` proves a
// *declared* registry's own actions each got a proving test case — but nothing before this proved
// a registry *itself* ever got an `assertAllCovered` call written for it at all. A registry with
// zero such calls anywhere silently covers nothing, and the runtime gate cannot detect its own
// absence: this is a `Vitest` test (`npm test`, already `make test`'s own frontend tier) rather
// than a fourth Playwright spec, deliberately — it needs no browser, only `actionRegistry.ts`'s
// own real `ALL_REGISTRIES` export and a text scan of this directory's `*.spec.ts` files, and
// runs in the fast, no-infra tier every commit already exercises rather than only under
// `make glass-keyboard`.
import { readFileSync, readdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import { ALL_REGISTRIES } from "./actionRegistry";

const KEYBOARD_DIR = dirname(fileURLToPath(import.meta.url));

function assertedRegistryNames(): Set<string> {
  const names = new Set<string>();
  const pattern = /assertAllCovered\(\s*["'](\w+)["']/g;
  for (const file of readdirSync(KEYBOARD_DIR)) {
    if (!file.endsWith(".spec.ts")) continue;
    const contents = readFileSync(join(KEYBOARD_DIR, file), "utf8");
    for (const match of contents.matchAll(pattern)) {
      names.add(match[1]);
    }
  }
  return names;
}

describe("every declared keyboard action registry has a proving assertAllCovered call", () => {
  const asserted = assertedRegistryNames();

  it.each(ALL_REGISTRIES.map((registry) => registry.name))(
    "%s is asserted by some *.spec.ts in this directory",
    (name) => {
      expect(
        asserted.has(name),
        `${name} is declared in actionRegistry.ts but no *.spec.ts file under keyboard/ calls ` +
          `assertAllCovered("${name}", ...) — its own coverage gate never runs, so it is ` +
          `silently proving nothing (the exact gap this test exists to catch).`,
      ).toBe(true);
    },
  );

  it("ALL_REGISTRIES is not itself empty", () => {
    // A vacuous pass (nothing declared, so nothing to assert) would defeat the point above —
    // guard against `actionRegistry.ts` regressing to export nothing at all.
    expect(ALL_REGISTRIES.length).toBeGreaterThan(0);
  });
});
