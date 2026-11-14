// For the copy guards only (`copyWords.test.ts`, `copyNoClient.test.ts`): never imported by the app.
//
// What is read: every string literal, template literal and line of JSX text in the Glass's source, by
// the TypeScript parser, so identifiers, imports and comments are never read as copy. A token holding a
// slash, a hyphen or an underscore (a route, a path, `oidc-client`, `client_id`) is a name, not a word on
// screen, and is dropped from the text. Tests and generated types are not on screen and are skipped.
import { readdirSync } from "node:fs";
import { join } from "node:path";

import ts from "typescript";

export const SRC = join(__dirname);

export function sourceFiles(dir: string = SRC): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) return entry.name === "generated" ? [] : sourceFiles(path);
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
