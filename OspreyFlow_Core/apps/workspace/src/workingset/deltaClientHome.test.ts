// GG2c, case 4: the delta client lives once, in `packages/glass-shared/src/workingset/deltaClient.ts`
// (ADR-152 decision 6, I11). A copy left in the workspace, or an importer still reaching a workspace copy, would
// type-check and pass every other suite, and the two copies would then drift apart unseen; this is the case
// that fails. Only the integration test stays here (it starts a real Conduit), importing the package's client.
// The whole of `apps/workspace` is walked, with no list of folders: a list leaves out the folder nobody added to it.
import { mkdirSync, mkdtempSync, readdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, relative } from "node:path";

import { describe, expect, it } from "vitest";

const WORKSPACE = new URL("../../", import.meta.url).pathname;
// Installed packages and built output: the only folders that hold no source of the workspace's own.
const NOT_SOURCE = new Set(["node_modules", "dist"]);
const SOURCE = /\.(ts|tsx|mts|cts|js|jsx|mjs|cjs)$/;
// An import, re-export or dynamic import of a module named `deltaClient` by a relative path: the package's is
// reached by its name, `@ospreyflow/glass-shared`, and never by a path.
const IMPORT_FORM = /(?:from\s+|import\s*\(\s*|import\s+)/;
const CLIENT_PATH = /["'](\.{1,2}\/[^"']*\/)?\.{0,2}\/?deltaClient(?:\.(?:ts|tsx|mts|cts|js|jsx|mjs|cjs))?["']/;
const RELATIVE_IMPORT = new RegExp(IMPORT_FORM.source + CLIENT_PATH.source);

function walk(dir: string, out: string[] = []): string[] {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    if (NOT_SOURCE.has(entry.name)) continue;
    const path = join(dir, entry.name);
    if (entry.isDirectory()) walk(path, out);
    else if (SOURCE.test(entry.name)) out.push(path);
  }
  return out;
}

// This file is left out of the scan: its last two cases hold the stale shapes as strings, on purpose.
const SELF = relative(WORKSPACE, new URL(import.meta.url).pathname);
function sourceFiles(root: string): string[] {
  return walk(root)
    .map((p) => relative(root, p))
    .filter((f) => f !== SELF);
}

function copiesIn(files: string[]): string[] {
  // `files` holds source files only, so any extensions after either name make it a copy (`.ts`, `.test.js`).
  return files.filter((f) => /(^|\/)(deltaClient|deltaOps)(\.[a-z]+)+$/.test(f));
}

function relativeImportersIn(root: string, files: string[]): string[] {
  return files.filter((f) => RELATIVE_IMPORT.test(readFileSync(join(root, f), "utf8")));
}

const files = sourceFiles(WORKSPACE);

describe("the delta client has one home, the shared package", () => {
  it("leaves no copy of the client or its unit tests in the workspace, only the integration test", () => {
    expect(copiesIn(files)).toEqual(["src/workingset/deltaClient.integration.test.ts"]);
  });

  it("has no workspace file importing a deltaClient module by a relative path", () => {
    expect(relativeImportersIn(WORKSPACE, files)).toEqual([]);
  });

  it("finds a stale copy or import wherever in the workspace it is left, a folder nobody has made yet included", () => {
    const stale = 'import { connectDeltaClient } from "../src/workingset/deltaClient";\n';
    const copies = [
      "compute-tier1/deltaClient.js",
      "deck-capture/deltaClient.ts",
      "deltaOps.test.ts",
      "scripts/deltaClient.cjs",
      "test/deltaClient.jsx",
    ];
    const importers: Record<string, string> = {
      "deck-capture/stale-harness.tsx": stale,
      "map-build/stale.ts": 'export * from "../src/workingset/deltaClient.js";\n',
      "a-folder-nobody-listed/deep/er/stale.mts": stale,
      "stale.config.ts": 'const m = await import("./src/workingset/deltaClient");\n',
    };
    // Installed and built output is not the workspace's source.
    const skipped = ["node_modules/some-package/deltaClient.ts", "map-build/dist/deltaClient.js"];

    const root = mkdtempSync(join(tmpdir(), "delta-client-home-"));
    try {
      const planted = [...copies, ...skipped].map((f) => [f, "export {};\n"]).concat(Object.entries(importers));
      for (const [file, text] of planted) {
        mkdirSync(dirname(join(root, file!)), { recursive: true });
        writeFileSync(join(root, file!), text!);
      }
      const found = sourceFiles(root);
      expect(copiesIn(found).sort()).toEqual([...copies].sort());
      expect(relativeImportersIn(root, found).sort()).toEqual(Object.keys(importers).sort());
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("has a pattern that finds each shape of a stale import (so the case above can fail)", () => {
    for (const line of [
      'import { connectDeltaClient } from "./workingset/deltaClient";',
      'import { connectDeltaClient, type SocketLike } from "../src/workingset/deltaClient";',
      'import type { DeltaClient } from "./deltaClient";',
      'export { isViewOverCap } from "./workingset/deltaClient.ts";',
      'const m = await import("./workingset/deltaClient");',
    ]) {
      expect(RELATIVE_IMPORT.test(line), line).toBe(true);
    }
    for (const line of [
      'import { connectDeltaClient } from "@ospreyflow/glass-shared";',
      'import { x } from "./deltaClientHome";',
      'import { x } from "./workingset/useDeltaClient";',
    ]) {
      expect(RELATIVE_IMPORT.test(line), line).toBe(false);
    }
  });
});
