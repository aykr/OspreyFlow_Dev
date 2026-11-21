// The Glass's copy says "pipeline", the Ingest Studio's word, never "recipe", the code's (CARRIES 234; the
// owner, 13 November 2026: the screens' word is Pipeline). The Conduit's words are held by
// the build folder's `tests/test_copy_says_pipeline.py`.
//
// What is scanned: every string literal, template literal and JSX text in the Glass's source, read with
// the TypeScript parser, so identifiers (`recipeId`), imports and comments are never read as copy.
// Every such text is copy, the word alone too (`plural(n, "recipe", "recipes")` builds a sentence from
// it), except a route or a path: a request's own description ("POST /v1/ingest/recipes") and any token
// with a slash in it name a route, not a word on screen.
// Tests and generated types are not on screen and are skipped. Two roots are read: the workspace's source
// and `packages/glass-shared/src`, where the Conduit clients now live (the copy kit's `ROOTS`).
import { readFileSync } from "node:fs";
import { relative } from "node:path";

import ts from "typescript";
import { describe, expect, it } from "vitest";

import { movedClients, plantedCopy, shown, sourceFiles } from "./copyTextsTestKit";

const WORD = /\brecipes?\b/i;
const ROUTE = /^(GET|POST|PUT|PATCH|DELETE)\s+\/|\/v1\//;

export function copyWords(name: string, source: string): { line: number; words: string }[] {
  const tree = ts.createSourceFile(
    name,
    source,
    ts.ScriptTarget.Latest,
    true,
    name.endsWith(".tsx") ? ts.ScriptKind.TSX : ts.ScriptKind.TS,
  );
  const hits: { line: number; words: string }[] = [];
  const visit = (node: ts.Node): void => {
    let words: string | null = null;
    if (ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node)) words = node.text;
    else if (ts.isTemplateExpression(node))
      words = [node.head.text, ...node.templateSpans.map((span) => span.literal.text)].join("");
    else if (ts.isJsxText(node)) words = node.text;
    const quoted = node.parent && (ts.isImportDeclaration(node.parent) || ts.isExportDeclaration(node.parent));
    if (words !== null && !quoted) {
      // A token with a slash in it is a route or a path, never a word on screen.
      const text = words
        .split(/\s+/)
        .filter((token) => token && !token.includes("/"))
        .join(" ");
      if (WORD.test(text) && !ROUTE.test(words.trim())) {
        hits.push({ line: tree.getLineAndCharacterOfPosition(node.getStart()).line + 1, words: text });
      }
    }
    ts.forEachChild(node, visit);
  };
  visit(tree);
  return hits;
}

describe("the Glass's copy says pipeline", () => {
  it("in every string, template and line of JSX text a person can be shown", () => {
    const hits = sourceFiles().flatMap((path) =>
      copyWords(path, readFileSync(path, "utf-8")).map((hit) => `${shown(path)}:${hit.line}: ${hit.words}`),
    );
    expect(hits).toEqual([]);
  });

  it("reads the Conduit clients that moved to packages/glass-shared/src (rule 15)", () => {
    const walked = sourceFiles();
    const clients = movedClients();
    expect(clients.length).toBeGreaterThanOrEqual(6);
    for (const client of clients) expect(walked, shown(client)).toContain(client);
    // A plant in a copy of a moved client, in the shape of a line of the update notice, is found by the same walk.
    const planted = plantedCopy("updateNotice.ts", 'export const PLANTED = { headline: "Recipe not checked yet" };');
    try {
      const hits = sourceFiles([planted.root]).flatMap((path) =>
        copyWords(path, readFileSync(path, "utf-8")).map((hit) => `${relative(planted.root, path)}: ${hit.words}`),
      );
      expect(hits).toEqual([`${planted.file}: Recipe not checked yet`]);
    } finally {
      planted.remove();
    }
  });

  it("is found in each shape the Glass's copy took before this change (rule 15)", () => {
    const planted = [
      "export function Runs() {",
      "  return (",
      "    <section>",
      "      <h3>Runs of this recipe</h3>",
      '      <p title="The graph this recipe would produce">x</p>',
      "    </section>",
      "  );",
      "}",
      "const WORDS = { stale: \"This recipe doesn't match the active ontology.\" };",
      "const failed = (name: string) => `The recipes of ${name} could not be read`;",
      'const label = "Recipe";',
    ].join("\n");
    expect(copyWords("Planted.tsx", planted).map((hit) => hit.line)).toEqual([4, 5, 9, 10, 11]);
  });

  it("leaves alone what is not copy: identifiers, imports, comments, keys and routes", () => {
    const clean = [
      'import { recipeApi } from "./recipes";',
      "// a recipe in a comment",
      "const recipeId = props.recipe_id;",
      'const key = "recipe_id";',
      'const route = "POST /v1/ingest/recipes/{id}/run";',
      "const url = `${base}/v1/ingest/recipes/${recipeId}`;",
    ].join("\n");
    expect(copyWords("Clean.ts", clean)).toEqual([]);
  });
});
