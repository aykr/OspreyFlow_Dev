// The server files `build.mjs` bundles with the shared package: every `.ts` file under `server/` (not a `.d.ts`) that
// imports or re-exports a value from `@ospreyflow/glass-shared`, or imports it for its effect, found by reading the
// files, so that a page adding such a file adds no line to the build (the owner's word of 27 November 2026: page parts
// kept conflicting in the build's entry list).
// A file that names the package only in a comment, imports only its types (which `tsc` erases) or declares it
// (`server/types/glassShared.d.ts`) is not bundled. Sorted, so the build is the same whatever order the disk lists.
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";

const COMMENTS = /\/\*[\s\S]*?\*\/|(^|[^:"'`])\/\/.*$/gm;
// An import or re-export of a value (`import { a } from`, `import * as s from`, `export { a } from`; never `import type` or
// `export type`), or an import for its effect alone (`import "…"`): each leaves an import of the package in tsc's output.
const IMPORTS_THE_PACKAGE =
  /\b(?:import|export)\s+(?!type\b)[^;]*?\bfrom\s*["']@ospreyflow\/glass-shared["']|\bimport\s*["']@ospreyflow\/glass-shared["']/;

/** @param {string} serverDir @returns {string[]} */
export function sharedPackageEntries(serverDir) {
  const found = [];
  const walk = (dir) => {
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      const path = join(dir, entry.name);
      if (entry.isDirectory()) walk(path);
      else if (entry.name.endsWith(".ts") && !entry.name.endsWith(".d.ts")) {
        const code = readFileSync(path, "utf8").replace(COMMENTS, "$1");
        if (IMPORTS_THE_PACKAGE.test(code)) found.push(path);
      }
    }
  };
  walk(serverDir);
  return found.sort();
}
