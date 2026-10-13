// ADR-115 (Phase E, stage E1): `DESIGN.md` is the contract and `tokens.css` its implementation. Every
// colour the contract declares is in the token layer under its name, in both themes; no colour is in
// the token layer that the contract does not declare; the contract's radius names and its §5a layout
// dimensions are tokens too. A value the product needs and the contract lacks is asked for, never
// added here quietly.
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

const DESIGN = readFileSync(join(__dirname, "../../../../DESIGN.md"), "utf-8");
const TOKENS = readFileSync(join(__dirname, "tokens.css"), "utf-8").replace(/\/\*[\s\S]*?\*\//g, "");

type Theme = "dark" | "light";

/** The custom properties a block declares, unresolved. */
function rawBlock(css: string, selector: string): Record<string, string> {
  const start = css.indexOf(`${selector} {`);
  if (start < 0) throw new Error(`no ${selector} block`);
  const body = css.slice(css.indexOf("{", start) + 1, css.indexOf("}", start));
  const own: Record<string, string> = {};
  for (const [, name, value] of body.matchAll(/(--[\w-]+)\s*:\s*([^;]+);/g)) own[name!] = value!.trim();
  return own;
}

/** Each property with `var(--x)` resolved within the same theme. */
function resolved(all: Record<string, string>): Record<string, string> {
  const resolve = (value: string, depth = 0): string => {
    const ref = /^var\((--[\w-]+)\)$/.exec(value);
    return ref && depth < 5 && all[ref[1]!] ? resolve(all[ref[1]!]!, depth + 1) : value;
  };
  return Object.fromEntries(Object.entries(all).map(([k, v]) => [k, resolve(v)]));
}

export function tokenLayer(css: string): Record<Theme, Record<string, string>> {
  const dark = rawBlock(css, ":root");
  return { dark: resolved(dark), light: resolved({ ...dark, ...rawBlock(css, '[data-theme="light"]') }) };
}

/** Every colour `DESIGN.md` declares, as token name → value per theme. */
export function contractColours(design: string): Record<Theme, Record<string, string>> {
  const out: Record<Theme, Record<string, string>> = { dark: {}, light: {} };
  for (const [, cell, dark, light] of design.matchAll(/^\|\s*`([\w-]+)`[^|]*\|\s*`(#[0-9a-f]{6})`\s*\|\s*`(#[0-9a-f]{6})`/gim)) {
    const name = cell!.startsWith("--") ? cell! : `--ch-${cell}`;
    out.dark[name] = dark!.toLowerCase();
    out.light[name] = light!.toLowerCase();
  }
  for (const [ramp, prefix] of [["3.5", "--seq"], ["3.6", "--div"]] as const) {
    const section = design.slice(design.indexOf(`### ${ramp}`), design.indexOf("###", design.indexOf(`### ${ramp}`) + 4));
    for (const theme of ["dark", "light"] as const) {
      const line = new RegExp(`- ${theme}: (.+)`, "i").exec(section)?.[1] ?? "";
      [...line.matchAll(/`(#[0-9a-f]{6})`/gi)].forEach(([, hex], i) => {
        out[theme][`${prefix}-${i + 1}`] = hex!.toLowerCase();
      });
    }
  }
  return out;
}

/** Colours in the token layer the contract does not declare, by theme. */
export function undeclared(css: string, design: string): string[] {
  const layer = tokenLayer(css);
  const declared = contractColours(design);
  const allowed = new Set([...Object.values(declared.dark), ...Object.values(declared.light)]);
  const found: string[] = [];
  for (const theme of ["dark", "light"] as const) {
    for (const [name, value] of Object.entries(layer[theme])) {
      for (const [hex] of value.matchAll(/#[0-9a-f]{3,8}\b/gi)) {
        if (!allowed.has(hex.toLowerCase())) found.push(`${theme} ${name} ${hex}`);
      }
    }
  }
  return found;
}

describe("DESIGN.md and tokens.css", () => {
  it("every colour the contract declares is a token of that name, in both themes", () => {
    const layer = tokenLayer(TOKENS);
    const declared = contractColours(DESIGN);
    expect(Object.keys(declared.dark).length).toBeGreaterThanOrEqual(12 + 4 + 3 + 9 + 6 + 7);
    for (const theme of ["dark", "light"] as const) {
      for (const [name, value] of Object.entries(declared[theme])) {
        expect(`${theme} ${name} ${layer[theme][name]?.toLowerCase()}`).toBe(`${theme} ${name} ${value}`);
      }
    }
  });

  it("no colour is in the token layer that the contract does not declare", () => {
    expect(undeclared(TOKENS, DESIGN)).toEqual([]);
  });

  it("the check finds a colour the contract lacks", () => {
    const planted = TOKENS.replace("--brass:#c08a34;", "--brass:#c08a35;");
    expect(undeclared(planted, DESIGN)).toEqual(["dark --brass #c08a35"]);
  });

  it("carries the contract's radius names (§5)", () => {
    const dark = tokenLayer(TOKENS).dark;
    expect([dark["--r-0"], dark["--r-1"], dark["--r-2"], dark["--r-3"], dark["--r-pill"]]).toEqual([
      "0", "2px", "4px", "6px", "999px",
    ]);
  });

  it("carries the contract's layout dimensions (§5a)", () => {
    const dark = tokenLayer(TOKENS).dark;
    expect({
      marking: dark["--h-marking"], topBar: dark["--h-top-bar"], topBarPage: dark["--h-top-bar-page"],
      rail: dark["--w-rail"], railButton: dark["--h-rail-button"], toolbar: dark["--h-canvas-toolbar"],
      panel: dark["--w-right-panel"], panelMin: dark["--w-right-panel-min"], panelMax: dark["--w-right-panel-max"],
      panelTabs: dark["--h-panel-tabs"], timeline: dark["--h-timeline"], timelinePlot: dark["--h-timeline-plot"],
      status: dark["--h-status-bar"], welcome: dark["--w-welcome-panel"], welcomeNarrow: dark["--w-welcome-panel-narrow"],
      signIn: dark["--w-sign-in-card"], signInMin: dark["--w-sign-in-card-min"],
      inspectorKeys: dark["--w-inspector-key"],
    }).toEqual({
      marking: "20px", topBar: "44px", topBarPage: "48px", rail: "48px", railButton: "36px", toolbar: "36px",
      panel: "340px", panelMin: "300px", panelMax: "480px", panelTabs: "36px", timeline: "34px", timelinePlot: "96px",
      status: "26px", welcome: "320px", welcomeNarrow: "280px", signIn: "360px", signInMin: "300px",
      inspectorKeys: "96px",
    });
    expect([24, 26, 28, 30, 32, 34, 36].map((h) => dark[`--h-control-${h}`])).toEqual(
      ["24px", "26px", "28px", "30px", "32px", "34px", "36px"],
    );
  });
});
