import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { describe, expect, it } from "vitest";
import { rewriteAssetUrls } from "../../../scripts/sync_govuk_assets.mjs";

const stray = (css: string) => css.split("url(/assets/").length - 1 - (css.split("url(/assets/govuk/").length - 1);

describe("rewriteAssetUrls", () => {
  it("rewrites a font and an image URL", () => {
    const { css, count } = rewriteAssetUrls(
      "@font-face{src:url(/assets/fonts/a.woff2)}.x{background:url(/assets/images/b.svg)}",
    );
    expect(count).toBe(2);
    expect(css).toContain("url(/assets/govuk/fonts/a.woff2)");
    expect(css).toContain("url(/assets/govuk/images/b.svg)");
    expect(stray(css)).toBe(0);
  });

  it("does not rewrite an already-rewritten URL twice", () => {
    const { css, count } = rewriteAssetUrls("a{b:url(/assets/govuk/x)}");
    expect(count).toBe(0);
    expect(css).toBe("a{b:url(/assets/govuk/x)}");
  });

  it("handles the installed govuk-frontend stylesheet", () => {
    const path = createRequire(import.meta.url).resolve("govuk-frontend/dist/govuk/govuk-frontend.min.css");
    const { css, count } = rewriteAssetUrls(readFileSync(path, "utf8"));
    expect(count).toBeGreaterThan(0);
    expect(stray(css)).toBe(0);
  });
});
