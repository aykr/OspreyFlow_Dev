// DESIGN.md §5: "No other radius" than the tokens. A radius set inline as a number cannot follow a
// deployment brand (ADR-132: the GOV.UK brand squares every corner by token), so it stayed rounded
// on a GOV.UK page — five were found in the spike's hand-back. Inline radii are tokens; a circle
// ("50%") is a shape, not a corner, and the canvas's own overlay is the data layer, which no brand
// changes.
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";

import { describe, expect, it } from "vitest";

const SRC = join(__dirname, "..");
const ALLOWED = new Set(["canvas/JudgementBadgeOverlay.tsx"]);
const NUMERIC_RADIUS = /borderRadius:\s*(?:["'](?!50%)[\d.]+(?:px)?["']|\d+)/g;

function sources(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return sources(path);
    return path.endsWith(".tsx") && !path.includes(".test.") ? [path] : [];
  });
}

export function numericRadii(files: Record<string, string>): string[] {
  return Object.entries(files).flatMap(([file, text]) =>
    ALLOWED.has(file) ? [] : [...text.matchAll(NUMERIC_RADIUS)].map((m) => `${file}: ${m[0]}`),
  );
}

describe("radii in the Glass's components", () => {
  it("are tokens, never a number set inline", () => {
    const files = Object.fromEntries(sources(SRC).map((p) => [relative(SRC, p), readFileSync(p, "utf-8")]));
    expect(numericRadii(files)).toEqual([]);
  });

  it("finds a number set inline, in the shapes the code uses", () => {
    expect(
      numericRadii({
        "a.tsx": 'style={{ borderRadius: 4 }} style={{ borderRadius: "999px" }} style={{ borderRadius: "50%" }}',
      }),
    ).toEqual(["a.tsx: borderRadius: 4", 'a.tsx: borderRadius: "999px"']);
  });
});
