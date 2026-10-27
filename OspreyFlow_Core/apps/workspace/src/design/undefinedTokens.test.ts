// The font tokens the source reads are the ones `tokens.css` defines. A misspelt token
// (`--font-mono` for `--mono`) is not an error in CSS: the declaration is dropped and the browser
// falls back silently, so only a check like this finds it. Scoped to the font tokens: other reads
// of names no stylesheet defines (some with a fallback, some built up in code) are listed in the
// hand-back, not asserted here.
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const SRC = join(__dirname, "..");

function files(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return files(path);
    return /\.(tsx?|css)$/.test(name) && !/\.test\.tsx?$/.test(name) ? [path] : [];
  });
}

describe("font tokens", () => {
  it("every var(--font-…) or var(--mono) the source reads is defined in tokens.css", () => {
    const tokens = readFileSync(join(SRC, "design", "tokens.css"), "utf8");
    const defined = new Set([...tokens.matchAll(/(--[a-zA-Z0-9-]+)\s*:/g)].map((m) => m[1]!));
    expect(defined.has("--mono")).toBe(true);
    const missing: string[] = [];
    for (const path of files(SRC)) {
      for (const m of readFileSync(path, "utf8").matchAll(/var\((--(?:font[a-z0-9-]*|mono|sans|serif))\b/g)) {
        if (!defined.has(m[1]!)) missing.push(`${path.slice(SRC.length + 1)}: ${m[1]}`);
      }
    }
    expect(missing).toEqual([]);
  });
});
