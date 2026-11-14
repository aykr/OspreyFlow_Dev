// No copy in the Glass names a client, or a setting still to be confirmed (the owner, 14 November 2026:
// the Connection strength legend said "(the client's)" and "to be confirmed with the client"). The
// Conduit's words, and the data the legend shows, are held by the build folder's
// `tests/test_copy_says_no_client.py`.
//
// What is read is `copyTextsTestKit.ts`'s: every string, template and line of JSX text, with names
// (`client_id`, `client_parity`, `oidc-client`) dropped. A string that is one lowercase key alone
// (`"client"`, a scale's value compared in code) is a key, not copy.
import { readFileSync } from "node:fs";
import { relative } from "node:path";

import { describe, expect, it } from "vitest";

import { copyTexts, sourceFiles, SRC } from "./copyTextsTestKit";

const WORDS = /\bclients?\b|\bclient's\b|\bclients'|to be confirmed|\bTBC\b|\bunconfirmed\b|\bnot confirmed\b|\bplaceholder\b/i;
const KEY = /^[a-z][a-z0-9]*$/;

export function clientWords(name: string, source: string): { line: number; words: string }[] {
  return copyTexts(name, source)
    .filter((text) => !KEY.test(text.raw.trim()) && WORDS.test(text.words))
    .map(({ line, words }) => ({ line, words }));
}

describe("the Glass's copy names no client and no setting still to be confirmed", () => {
  it("in every string, template and line of JSX text a person can be shown", () => {
    const hits = sourceFiles().flatMap((path) =>
      clientWords(path, readFileSync(path, "utf-8")).map((hit) => `${relative(SRC, path)}:${hit.line}: ${hit.words}`),
    );
    expect(hits).toEqual([]);
  });

  it("is found in each shape the copy took before this change (rule 15)", () => {
    const planted = [
      "export const MEASURE = { share: \"share of pair links (the client's)\" };",
      "export const COMPOSITION = { client_parity: \"Client parity\" };",
      "const raw = (n: number) => `Raw sum ${n} on the client's scale; drawn on 0 to 1.`;",
      'const note = "to be confirmed with the client";',
      "export function Licence({ note }: { note?: string }) {",
      '  return <span>{`Licence not confirmed: ${note ?? "its terms are TBC"}.`}</span>;',
      "}",
      "export function Owner() {",
      "  return <label><span>The orchestrator's client</span></label>;",
      "}",
      'const unsure = "an unconfirmed setting";',
      'const later = "a placeholder value";',
    ].join("\n");
    expect(clientWords("Planted.tsx", planted).map((hit) => hit.line)).toEqual([1, 2, 3, 4, 6, 6, 9, 11, 12]);
  });

  it("leaves alone what is not copy: names, keys, imports and comments", () => {
    const clean = [
      'import { client } from "./client";',
      "// the client's own scale, in a comment",
      'const scale = draft.scale === "client" ? 1 : 0;',
      'const tag = { source: "oidc-client" };',
      "const body = JSON.stringify({ client_id: id });",
      'const composition: string = "client_parity";',
    ].join("\n");
    expect(clientWords("Clean.ts", clean)).toEqual([]);
  });
});
