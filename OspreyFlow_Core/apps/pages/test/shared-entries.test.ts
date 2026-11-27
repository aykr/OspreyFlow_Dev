// What `apps/pages/scripts/build.mjs` bundles with the shared package: the server files that import it, found by reading them,
// so a page that adds such a file adds no line to the build (the owner's word of 27 November 2026: page parts kept
// conflicting in the build's entry list).
import { mkdirSync, mkdtempSync, readdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";

import ts from "typescript";
import { afterEach, describe, expect, it } from "vitest";

import { sharedPackageEntries } from "../scripts/sharedEntries.mjs";

const PAGES_DIR = join(dirname(fileURLToPath(import.meta.url)), "..");
const PACKAGE = "@ospreyflow/glass-shared";
const made: string[] = [];

/** Every `.ts` file under `dir` but a declaration file, sorted. */
function serverFiles(dir: string): string[] {
  const out: string[] = [];
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) out.push(...serverFiles(path));
    else if (entry.name.endsWith(".ts") && !entry.name.endsWith(".d.ts")) out.push(path);
  }
  return out.sort();
}

/** Whether the compiler keeps a run-time reference to the shared package in `file`: an import or re-export of a value
 * (not `import type`/`export type`, and not only type specifiers), or an import for its effect alone. Read by
 * TypeScript's parser, independently of `sharedEntries.mjs`'s pattern. */
function importsAValueFromThePackage(file: string): boolean {
  const source = ts.createSourceFile(file, readFileSync(file, "utf8"), ts.ScriptTarget.Latest, false, ts.ScriptKind.TS);
  return source.statements.some((s) => {
    if (ts.isImportDeclaration(s) && ts.isStringLiteral(s.moduleSpecifier) && s.moduleSpecifier.text === PACKAGE) {
      const clause = s.importClause;
      if (!clause) return true; // import "pkg": for its effect
      if (clause.isTypeOnly) return false;
      if (clause.name) return true;
      const bindings = clause.namedBindings;
      if (!bindings) return false;
      return ts.isNamespaceImport(bindings) || bindings.elements.some((e) => !e.isTypeOnly);
    }
    if (ts.isExportDeclaration(s) && s.moduleSpecifier && ts.isStringLiteral(s.moduleSpecifier) && s.moduleSpecifier.text === PACKAGE) {
      if (s.isTypeOnly) return false;
      const clause = s.exportClause;
      return !clause || !ts.isNamedExports(clause) || clause.elements.some((e) => !e.isTypeOnly);
    }
    return false;
  });
}

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
  it("are every server file that imports a value from it, read by TypeScript's own parser, with no list or count", () => {
    // Each file is read by the compiler's parser, not by the finder's pattern, so the two are told apart; a page that adds a
    // file importing the package edits nothing here (the owner's 66b, 27 November 2026: this test pinned four files, and
    // every new page's words file would have had to edit it). The finder may also take a file that imports only type
    // specifiers (bundling it is harmless); it must never leave out one the compiler keeps an import of.
    const server = join(PAGES_DIR, "server");
    const imports = serverFiles(server).filter(importsAValueFromThePackage);
    expect(imports.length, "no server file imports the shared package: the parser or the walk is wrong").toBeGreaterThan(0);
    const found = new Set(sharedPackageEntries(server));
    expect(imports.filter((f) => !found.has(f)).map((f) => relative(server, f))).toEqual([]);
  });

  it("take a new page's file that imports it, on one line or several, with no line added anywhere", () => {
    const root = server({
      "views/oneWords.ts": 'import { a } from "@ospreyflow/glass-shared";\nexport const x = a;\n',
      "views/manyWords.ts": 'import {\n  a,\n  b,\n} from "@ospreyflow/glass-shared";\nexport const y = [a, b];\n',
      "views/deeper/newWords.ts": "import { c } from '@ospreyflow/glass-shared';\nexport const z = c;\n",
      "views/passedOn.ts": 'export { d } from "@ospreyflow/glass-shared";\n',
      "views/allOf.ts": 'import * as shared from "@ospreyflow/glass-shared";\nexport const e = shared.e;\n',
      "views/forItsEffect.ts": 'import "@ospreyflow/glass-shared";\nexport const f = 1;\n',
    });
    const taken = sharedPackageEntries(root).map((f) => relative(root, f));
    expect(taken).toEqual([
      join("views", "allOf.ts"),
      join("views", "deeper", "newWords.ts"),
      join("views", "forItsEffect.ts"),
      join("views", "manyWords.ts"),
      join("views", "oneWords.ts"),
      join("views", "passedOn.ts"),
    ]);
    // the parser agrees on each of them
    expect(serverFiles(root).filter(importsAValueFromThePackage).map((f) => relative(root, f))).toEqual(taken);
  });

  it("leave out a file that only names the package in a comment, imports only its types, or declares it", () => {
    const root = server({
      "views/commentWords.ts": '// The words are `@ospreyflow/glass-shared`\'s, from "@ospreyflow/glass-shared" in the end.\nexport const x = 1;\n',
      "views/blockWords.ts": '/* import { a } from "@ospreyflow/glass-shared"; */\nexport const y = 1;\n',
      "views/typesOnly.ts": 'import type { A } from "@ospreyflow/glass-shared";\nexport type B = A;\n',
      "types/glassShared.d.ts": 'declare module "@ospreyflow/glass-shared" {\n  export const a: string;\n}\n',
      "types/more.d.ts": 'import { A } from "@ospreyflow/glass-shared";\nexport declare const b: A;\n',
      "views/other.ts": 'import { b } from "./elsewhere.js";\nexport const z = b;\n',
      "views/typesPassedOn.ts": 'export type { A } from "@ospreyflow/glass-shared";\n',
    });
    expect(sharedPackageEntries(root)).toEqual([]);
    expect(serverFiles(root).filter(importsAValueFromThePackage)).toEqual([]);
  });
});
