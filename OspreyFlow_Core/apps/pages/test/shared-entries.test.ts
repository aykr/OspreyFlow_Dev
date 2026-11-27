// What `apps/pages/scripts/build.mjs` bundles with the shared package: the server files that import it, found by reading them,
// so a page that adds such a file adds no line to the build (the owner's word of 27 November 2026: page parts kept
// conflicting in the build's entry list).
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";

import { afterEach, describe, expect, it } from "vitest";

import { sharedPackageEntries } from "../scripts/sharedEntries.mjs";

const PAGES_DIR = join(dirname(fileURLToPath(import.meta.url)), "..");
const made: string[] = [];

function server(files: Record<string, string>): string {
  const root = mkdtempSync(join(tmpdir(), "shared-entries-"));
  made.push(root);
  for (const [name, text] of Object.entries(files)) {
    mkdirSync(dirname(join(root, name)), { recursive: true });
    writeFileSync(join(root, name), text);
  }
  return root;
}

afterEach(() => {
  for (const root of made.splice(0)) rmSync(root, { recursive: true, force: true });
});

describe("the files the build bundles with the shared package", () => {
  it("are the real server's four words files that import it, today", () => {
    const server = join(PAGES_DIR, "server");
    expect(sharedPackageEntries(server).map((f) => relative(server, f))).toEqual([
      join("views", "boardsWords.ts"),
      join("views", "casesWords.ts"),
      join("views", "helpWords.ts"),
      join("views", "packTrendsWords.ts"),
    ]);
  });

  it("take a new page's file that imports it, on one line or several, with no line added anywhere", () => {
    const root = server({
      "views/oneWords.ts": 'import { a } from "@ospreyflow/glass-shared";\nexport const x = a;\n',
      "views/manyWords.ts": 'import {\n  a,\n  b,\n} from "@ospreyflow/glass-shared";\nexport const y = [a, b];\n',
      "views/deeper/newWords.ts": "import { c } from '@ospreyflow/glass-shared';\nexport const z = c;\n",
    });
    expect(sharedPackageEntries(root).map((f) => relative(root, f))).toEqual([
      join("views", "deeper", "newWords.ts"),
      join("views", "manyWords.ts"),
      join("views", "oneWords.ts"),
    ]);
  });

  it("leave out a file that only names the package in a comment, imports only its types, or declares it", () => {
    const root = server({
      "views/commentWords.ts": '// The words are `@ospreyflow/glass-shared`\'s, from "@ospreyflow/glass-shared" in the end.\nexport const x = 1;\n',
      "views/blockWords.ts": '/* import { a } from "@ospreyflow/glass-shared"; */\nexport const y = 1;\n',
      "views/typesOnly.ts": 'import type { A } from "@ospreyflow/glass-shared";\nexport type B = A;\n',
      "types/glassShared.d.ts": 'declare module "@ospreyflow/glass-shared" {\n  export const a: string;\n}\n',
      "types/more.d.ts": 'import { A } from "@ospreyflow/glass-shared";\nexport declare const b: A;\n',
      "views/other.ts": 'import { b } from "./elsewhere.js";\nexport const z = b;\n',
    });
    expect(sharedPackageEntries(root)).toEqual([]);
  });
});
