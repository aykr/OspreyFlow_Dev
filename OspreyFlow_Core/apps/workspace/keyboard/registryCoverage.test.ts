// The static half of the keyboard-reachability gap, exposed by Phase 7 Stage 4's third registry
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

/**
 * The registry names one spec's source asserts: `assertAllCovered("<LITERAL>", …)`, or a name passed
 * through a string constant the same file declares (`const REGISTRY = "RULES_PLACE_ACTIONS";`, the
 * shape two lanes used on 10 November 2026 and this scan once read as "never asserted"). A first
 * argument it cannot resolve to a string is returned in `unread`, so the caller fails in words
 * rather than reading the registry as unasserted.
 */
export function assertedNamesIn(source: string): {
  names: string[];
  unread: string[];
} {
  const constants = new Map<string, string>();
  const declared =
    /\b(?:const|let)\s+(\w+)\s*(?::\s*string\s*)?=\s*["'](\w+)["']/g;
  for (const [, name, value] of source.matchAll(declared))
    constants.set(name, value);
  const names: string[] = [];
  const unread: string[] = [];
  for (const [, literal, identifier] of source.matchAll(
    /assertAllCovered\(\s*(?:["'](\w+)["']|([A-Za-z_$][\w$.]*))/g,
  )) {
    if (literal !== undefined) names.push(literal);
    else if (constants.has(identifier))
      names.push(constants.get(identifier) as string);
    else unread.push(identifier);
  }
  return { names, unread };
}

function unreadCalls(): string[] {
  const found: string[] = [];
  for (const file of readdirSync(KEYBOARD_DIR)) {
    if (!file.endsWith(".spec.ts")) continue;
    const contents = readFileSync(join(KEYBOARD_DIR, file), "utf8");
    for (const name of assertedNamesIn(contents).unread)
      found.push(`${file}: ${name}`);
  }
  return found;
}

function assertedRegistryNames(): Set<string> {
  const names = new Set<string>();
  for (const file of readdirSync(KEYBOARD_DIR)) {
    if (!file.endsWith(".spec.ts")) continue;
    const contents = readFileSync(join(KEYBOARD_DIR, file), "utf8");
    for (const name of assertedNamesIn(contents).names) names.add(name);
  }
  return names;
}

describe("the scan reads a registry's name however a spec passes it", () => {
  it("reads a literal", () => {
    expect(
      assertedNamesIn('assertAllCovered("PACKS_ACTIONS", PACKS_ACTIONS);')
        .names,
    ).toEqual(["PACKS_ACTIONS"]);
  });

  it("reads a name passed through a string constant (L2.7 and L2.11a, 10 November 2026)", () => {
    const spec =
      'const REGISTRY = "RULES_PLACE_ACTIONS";\n' +
      'registerCovered(REGISTRY, "rail-entries-by-keyboard");\n' +
      "assertAllCovered(REGISTRY, RULES_PLACE_ACTIONS);\n";
    expect(assertedNamesIn(spec)).toEqual({
      names: ["RULES_PLACE_ACTIONS"],
      unread: [],
    });
  });

  it("says which first argument it could not read, rather than reading it as unasserted", () => {
    const spec =
      "function check(name: string) {\n  assertAllCovered(name, PACKS_ACTIONS);\n}\n";
    expect(assertedNamesIn(spec)).toEqual({ names: [], unread: ["name"] });
  });

  it("every assertAllCovered call under keyboard/ names its registry in a way this scan reads", () => {
    expect(
      unreadCalls(),
      "pass the registry's name to assertAllCovered as a string literal, or through a " +
        'string constant declared in the same spec (const REGISTRY = "X_ACTIONS")',
    ).toEqual([]);
  });
});

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
