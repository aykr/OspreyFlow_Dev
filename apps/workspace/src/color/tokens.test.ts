import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

import {
  BORDER_STRONG_DARK_HEX,
  BRASS_HEX,
  CHANNEL_HEX,
  SURFACE_PANEL_DARK_HEX,
  TEXT_PRIMARY_DARK_HEX,
} from "./tokens";

// Parses `docs/design/tokens.css` directly — this is the enforcement half
// of `tokens.ts`'s "kept in sync by hand, cross-checked here" contract.
// If someone edits a channel hue in the authoritative CSS file without
// updating this module, this test fails instead of the drift sitting
// unnoticed until a node renders the wrong colour.
const TOKENS_CSS_PATH = new URL(
  "../../../../docs/design/tokens.css",
  import.meta.url,
).pathname;

function readTokensCss(): string {
  return readFileSync(TOKENS_CSS_PATH, "utf8");
}

function cssVar(css: string, name: string): string {
  const match = css.match(new RegExp(`--${name}:\\s*(#[0-9a-fA-F]{3,6})`));
  const hex = match?.[1];
  if (!hex) throw new Error(`--${name} not found in tokens.css`);
  return hex.toLowerCase();
}

describe("CHANNEL_HEX matches docs/design/tokens.css (dark theme)", () => {
  const css = readTokensCss();

  it.each(Object.entries(CHANNEL_HEX))("channel %s", (channel, hex) => {
    expect(hex.toLowerCase()).toBe(cssVar(css, `ch-${channel}`));
  });

  it("brass matches", () => {
    expect(BRASS_HEX.toLowerCase()).toBe(cssVar(css, "brass"));
  });

  it("text-primary (n11, dark) matches", () => {
    expect(TEXT_PRIMARY_DARK_HEX.toLowerCase()).toBe(cssVar(css, "n11"));
  });

  it("border-strong (n7, dark) matches", () => {
    expect(BORDER_STRONG_DARK_HEX.toLowerCase()).toBe(cssVar(css, "n7"));
  });

  it("surface-panel (n2, dark) matches", () => {
    expect(SURFACE_PANEL_DARK_HEX.toLowerCase()).toBe(cssVar(css, "n2"));
  });
});
