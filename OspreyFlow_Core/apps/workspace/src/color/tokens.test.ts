import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

import {
  BORDER_STRONG_DARK_HEX,
  BORDER_SUBTLE_DARK_HEX,
  BRASS_HEX,
  CHANNEL_HEX,
  SEQ_HEX,
  SURFACE_APP_DARK_HEX,
  SURFACE_PANEL_DARK_HEX,
  SURFACE_RAISED_DARK_HEX,
  SURFACE_SUNKEN_DARK_HEX,
  TEXT_PRIMARY_DARK_HEX,
  TEXT_SECONDARY_DARK_HEX,
} from "./tokens";

// Parses `tokens.css` directly — this is the enforcement half of
// `tokens.ts`'s "kept in sync by hand, cross-checked here" contract.
// If someone edits a channel hue in the authoritative CSS file without
// updating this module, this test fails instead of the drift sitting
// unnoticed until a node renders the wrong colour.
const TOKENS_CSS_PATH = new URL("../design/tokens.css", import.meta.url).pathname;

function readTokensCss(): string {
  return readFileSync(TOKENS_CSS_PATH, "utf8");
}

function cssVar(css: string, name: string): string {
  const match = css.match(new RegExp(`--${name}:\\s*(#[0-9a-fA-F]{3,6})`));
  const hex = match?.[1];
  if (!hex) throw new Error(`--${name} not found in tokens.css`);
  return hex.toLowerCase();
}

describe("CHANNEL_HEX matches spec/design/tokens.css (dark theme)", () => {
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

  it("surface-sunken (n0, dark) matches", () => {
    expect(SURFACE_SUNKEN_DARK_HEX.toLowerCase()).toBe(cssVar(css, "n0"));
  });

  it("surface-app (n1, dark) matches", () => {
    expect(SURFACE_APP_DARK_HEX.toLowerCase()).toBe(cssVar(css, "n1"));
  });

  it("surface-raised (n3, dark) matches", () => {
    expect(SURFACE_RAISED_DARK_HEX.toLowerCase()).toBe(cssVar(css, "n3"));
  });

  it("text-secondary (n10, dark) matches", () => {
    expect(TEXT_SECONDARY_DARK_HEX.toLowerCase()).toBe(cssVar(css, "n10"));
  });

  it("border-subtle (n5, dark) matches", () => {
    expect(BORDER_SUBTLE_DARK_HEX.toLowerCase()).toBe(cssVar(css, "n5"));
  });

  it.each(SEQ_HEX.map((hex, i) => [i + 1, hex]))("seq-%s matches", (n, hex) => {
    expect((hex as string).toLowerCase()).toBe(cssVar(css, `seq-${n}`));
  });
});

// Light theme (ADR-070): the palette the canvas and the charts use when the page is light must be
// the light block of tokens.css, not a copy that drifts.
import { paletteFor } from "./palette";

function lightBlock(css: string): string {
  const start = css.indexOf('[data-theme="light"]');
  if (start < 0) throw new Error("no light block in tokens.css");
  return css.slice(start, css.indexOf("}", start));
}

function lightVar(name: string): string {
  const match = lightBlock(readTokensCss()).match(new RegExp(`--${name}:\\s*(#[0-9a-fA-F]{3,6})`));
  const hex = match?.[1];
  if (!hex) throw new Error(`--${name} not found in the light block of tokens.css`);
  return hex.toLowerCase();
}

describe("the light palette matches tokens.css ([data-theme=light])", () => {
  const light = paletteFor("light");

  it.each(Object.keys(CHANNEL_HEX))("channel %s", (channel) => {
    expect(light.channel(channel).toLowerCase()).toBe(lightVar(`ch-${channel}`));
  });

  it("the neutrals and the accent", () => {
    expect(light.textPrimary.toLowerCase()).toBe(lightVar("n11"));
    expect(light.textSecondary.toLowerCase()).toBe(lightVar("n10"));
    expect(light.borderStrong.toLowerCase()).toBe(lightVar("n7"));
    expect(light.borderSubtle.toLowerCase()).toBe(lightVar("n5"));
    expect(light.surfacePanel.toLowerCase()).toBe(lightVar("n2"));
    expect(light.surfaceApp.toLowerCase()).toBe(lightVar("n1"));
    expect(light.brass.toLowerCase()).toBe(lightVar("brass"));
  });

  it("the sequential ramp", () => {
    light.seq.forEach((hex, i) => expect(hex.toLowerCase()).toBe(lightVar(`seq-${i + 1}`)));
  });
});

describe("the dark palette is the constants already here", () => {
  it("is unchanged", () => {
    const dark = paletteFor("dark");
    expect(dark.textPrimary).toBe(TEXT_PRIMARY_DARK_HEX);
    expect(dark.borderStrong).toBe(BORDER_STRONG_DARK_HEX);
    expect(dark.surfacePanel).toBe(SURFACE_PANEL_DARK_HEX);
    expect(dark.channel("indigo")).toBe(CHANNEL_HEX.indigo);
    expect(dark.seq).toEqual(SEQ_HEX);
  });
});
