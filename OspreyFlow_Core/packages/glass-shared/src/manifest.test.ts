import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

// ADR-152 I1 and I13, at the manifest: the shared package declares no React and no drawing library, so
// installing it for `pages` brings none in. The bundle and the source are checked by the two scripts and the
// lint block for this folder; this is the first thing that fails if someone adds the dependency.
const BANNED = /^(react|react-dom|sigma|maplibre-gl|@sigma\/.+)$/;
const manifest = JSON.parse(readFileSync(new URL("../package.json", import.meta.url), "utf8")) as Record<
  string,
  Record<string, string> | undefined
>;

describe("the shared package's manifest", () => {
  for (const kind of ["dependencies", "devDependencies", "peerDependencies", "optionalDependencies"]) {
    it(`lists no React or drawing library under ${kind}`, () => {
      const banned = Object.keys(manifest[kind] ?? {}).filter((name) => BANNED.test(name));
      expect(banned).toEqual([]);
    });
  }

  it("has the pattern that finds a banned name (so the cases above can fail)", () => {
    for (const name of ["react", "react-dom", "sigma", "maplibre-gl", "@sigma/layer-maplibre"]) {
      expect(BANNED.test(name)).toBe(true);
    }
    for (const name of ["zustand", "graphology", "reactive-banana", "sigmoid"]) {
      expect(BANNED.test(name)).toBe(false);
    }
  });
});
