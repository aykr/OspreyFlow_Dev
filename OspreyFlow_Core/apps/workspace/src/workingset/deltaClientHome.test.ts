// GG2c, case 4: the delta client lives once, in `packages/glass-shared/src/workingset/deltaClient.ts`
// (ADR-152 decision 6, I11). A copy left in the workspace, or an importer still reaching a workspace copy, would
// type-check and pass every other suite, and the two copies would then drift apart unseen; this is the case
// that fails. Only the integration test stays here (it starts a real Conduit), importing the package's client.
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";

import { describe, expect, it } from "vitest";

const WORKSPACE = new URL("../../", import.meta.url).pathname;
const SCANNED = ["src", "keyboard", "a11y", "perf", "live", "map-verify", "export-capture"];
const SOURCE = /\.(ts|tsx|mts|cts|js|mjs)$/;
// An import, re-export or dynamic import of a module named `deltaClient` by a relative path: the package's is
// reached by its name, `@ospreyflow/glass-shared`, and never by a path.
const RELATIVE_IMPORT = /(?:from\s+|import\s*\(\s*|import\s+)["'](\.{1,2}\/[^"']*\/)?\.{0,2}\/?deltaClient(?:\.ts)?["']/;

function walk(dir: string, out: string[] = []): string[] {
  let names: string[];
  try {
    names = readdirSync(dir);
  } catch {
    return out;
  }
  for (const name of names) {
    if (name === "node_modules" || name === "dist") continue;
    const path = join(dir, name);
    if (statSync(path).isDirectory()) walk(path, out);
    else if (SOURCE.test(name)) out.push(path);
  }
  return out;
}

const files = SCANNED.flatMap((d) => walk(join(WORKSPACE, d))).map((p) => relative(WORKSPACE, p));

describe("the delta client has one home, the shared package", () => {
  it("leaves no copy of the client or its unit tests in the workspace, only the integration test", () => {
    const left = files.filter((f) => /(^|\/)(deltaClient|deltaOps)(\.[a-z]+)*\.(ts|tsx)$/.test(f));
    expect(left).toEqual(["src/workingset/deltaClient.integration.test.ts"]);
  });

  it("has no workspace file importing a deltaClient module by a relative path", () => {
    const importers = files.filter((f) => RELATIVE_IMPORT.test(readFileSync(join(WORKSPACE, f), "utf8")));
    expect(importers).toEqual([]);
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
