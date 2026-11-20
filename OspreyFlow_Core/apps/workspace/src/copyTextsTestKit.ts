// For the copy guards only (`copyWords.test.ts`, `copyNoClient.test.ts`): never imported by the app.
//
// What is read: every string literal, template literal and line of JSX text in the Glass's source, by
// the TypeScript parser, so identifiers, imports and comments are never read as copy. A token holding a
// slash, a hyphen or an underscore (a route, a path, `oidc-client`, `client_id`) is a name, not a word on
// screen, and is dropped from the text. Tests and generated types are not on screen and are skipped.
import { cpSync, mkdtempSync, readdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, relative } from "node:path";

import ts from "typescript";

export const SRC = join(__dirname);
/** The shared package's source, where the plain modules that left the workspace live (slices PL4c to PL4d2):
 * the Conduit clients there hold copy a person is shown, so the guards read it as they read `SRC`. */
export const SHARED_SRC = join(__dirname, "..", "..", "..", "packages", "glass-shared", "src");
/** The roots the guards walk: the one list every copy guard and its reach test use. */
export const ROOTS: readonly string[] = [SRC, SHARED_SRC];

/** The files under `roots` (by default both), skipping tests, test kits and generated types. */
export function sourceFiles(roots: readonly string[] = ROOTS): string[] {
  return roots.flatMap((root) => filesUnder(root));
}

/** The path as the guards print it: relative to its own root, the shared package's marked. */
export function shown(path: string): string {
  return path.startsWith(SHARED_SRC) ? `glass-shared/${relative(SHARED_SRC, path)}` : relative(SRC, path);
}

/** The Conduit clients and the notice that live in the shared package: every file there under the two folders the
 * clients came from, found on disc rather than named, so a client added later is walked and checked too. */
export function movedClients(): string[] {
  return sourceFiles([SHARED_SRC]).filter((path) => /\/(ingest|admin)\//.test(path));
}

/** A copy of the shared package in a temporary folder, with `line` appended to its file named `basename`; returns the
 * folder, that file's path relative to it, and a cleanup. For the guards' plants (rule 15): the plant sits in a real
 * moved client, and the guard's own walk and test are run over the copy. */
export function plantedCopy(basename: string, line: string): { root: string; file: string; remove: () => void } {
  const root = mkdtempSync(join(tmpdir(), "copy-guard-"));
  cpSync(SHARED_SRC, root, { recursive: true });
  const target = sourceFiles([root]).find((path) => path.endsWith(`/${basename}`));
  if (!target) throw new Error(`no ${basename} in the shared package`);
  writeFileSync(target, `${readFileSync(target, "utf-8")}\n${line}\n`);
  return { root, file: relative(root, target), remove: () => rmSync(root, { recursive: true, force: true }) };
}

function filesUnder(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) return entry.name === "generated" || entry.name === "node_modules" ? [] : filesUnder(path);
    return /\.(ts|tsx)$/.test(entry.name) && !/\.(test|spec)\./.test(entry.name) && !/TestKit\.ts$/.test(entry.name)
      ? [path]
      : [];
  });
}

export type CopyText = { line: number; words: string; raw: string };

/** Each piece of copy in `source`: its line, its words without name-like tokens, and its raw text. */
export function copyTexts(name: string, source: string): CopyText[] {
  const tree = ts.createSourceFile(
    name,
    source,
    ts.ScriptTarget.Latest,
    true,
    name.endsWith(".tsx") ? ts.ScriptKind.TSX : ts.ScriptKind.TS,
  );
  const found: CopyText[] = [];
  const visit = (node: ts.Node): void => {
    let raw: string | null = null;
    if (ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node)) raw = node.text;
    else if (ts.isTemplateExpression(node))
      raw = [node.head.text, ...node.templateSpans.map((span) => span.literal.text)].join("");
    else if (ts.isJsxText(node)) raw = node.text;
    const quoted = node.parent && (ts.isImportDeclaration(node.parent) || ts.isExportDeclaration(node.parent));
    if (raw !== null && !quoted) {
      const words = raw
        .split(/\s+/)
        .filter((token) => token && !/[/_]/.test(token) && !/\w-\w/.test(token))
        .join(" ");
      found.push({ line: tree.getLineAndCharacterOfPosition(node.getStart()).line + 1, words, raw });
    }
    ts.forEachChild(node, visit);
  };
  visit(tree);
  return found;
}
