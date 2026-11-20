import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

// ADR-152 I1 and I13, at the manifest: the shared package declares no React and no drawing library, so
// installing it for `pages` brings none in. The bundle and the source are checked by the two scripts and the
// lint block for this folder; this is the first thing that fails if someone adds the dependency.
const BANNED = /^(react|react-dom|sigma|maplibre-gl|@sigma\/.+)$/;
const manifest = JSON.parse(readFileSync(new URL("../package.json", import.meta.url), "utf8")) as Record<
  string,
  Record<string, string> | boolean | undefined
>;

describe("the shared package's manifest", () => {
  for (const kind of ["dependencies", "devDependencies", "peerDependencies", "optionalDependencies"]) {
    it(`lists no React or drawing library under ${kind}`, () => {
      const banned = Object.keys((manifest[kind] as Record<string, string> | undefined) ?? {}).filter((name) => BANNED.test(name));
      expect(banned).toEqual([]);
    });
  }

  // `workingset/store.ts` and the keyboard registry are exported by one index, and the registry registers
  // itself at import (`defineActionRegistry` pushes into `ALL_REGISTRIES`), which a bundler reads as a side
  // effect it must keep. Without this flag every bundle that imports the package for one function carries the
  // whole registry: measured on the workspace's build in PL4 slice C, whose output then differed from the
  // baseline by exactly that module (`scripts/dist_compare.mjs`).
  it("declares itself free of side effects, so a bundle keeps only the modules it imports", () => {
    expect(manifest.sideEffects).toBe(false);
  });

  it("has the pattern that finds a banned name (so the cases above can fail)", () => {
    for (const name of ["react", "react-dom", "sigma", "maplibre-gl", "@sigma/layer-maplibre"]) {
      expect(BANNED.test(name)).toBe(true);
    }
    for (const name of ["zustand", "graphology", "reactive-banana", "sigmoid"]) {
      expect(BANNED.test(name)).toBe(false);
    }
  });
});
