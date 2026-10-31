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

/** Each `[data-brand="…"]` block's own custom properties, by brand (ADR-132). */
export function brandBlocks(css: string): Record<string, Record<string, string>> {
  const out: Record<string, Record<string, string>> = {};
  for (const [, brand] of css.matchAll(/\[data-brand="([\w-]+)"\]\s*\{/g)) {
    out[brand!] = rawBlock(css, `[data-brand="${brand}"]`);
  }
  return out;
}

/** Each brand's colours as `DESIGN.md` §11 declares them: token → value, under `### <brand>`. */
export function contractBrands(design: string): Record<string, Record<string, string>> {
  const start = design.indexOf("## 11. Deployment brands");
  const section = start < 0 ? "" : design.slice(start);
  const out: Record<string, Record<string, string>> = {};
  for (const part of section.split(/^### /m).slice(1)) {
    const brand = part.slice(0, part.indexOf("\n")).trim();
    out[brand] = {};
    for (const [, name, hex] of part.matchAll(/^\|\s*`(--[\w-]+)`\s*\|\s*`(#[0-9a-f]{6})`\s*\|/gim)) {
      out[brand]![name!] = hex!.toLowerCase();
    }
  }
  return out;
}

const DATA_TOKEN = /^--(ch|chart|seq|div)-/;

/** Where a brand block breaks `DESIGN.md` §11: a data token redefined, a colour §11 does not declare
 * for that brand, a declared colour the block lacks, or a brand with no section. */
export function brandFindings(css: string, design: string): string[] {
  const declared = contractBrands(design);
  const found: string[] = [];
  for (const [brand, block] of Object.entries(brandBlocks(css))) {
    const own = declared[brand];
    if (!own) {
      found.push(`${brand} has no section in DESIGN.md §11`);
      continue;
    }
    for (const [name, value] of Object.entries(block)) {
      if (DATA_TOKEN.test(name)) found.push(`${brand} ${name} redefines a data token`);
      for (const [hex] of value.matchAll(/#[0-9a-f]{3,8}\b/gi)) {
        if (own[name] !== hex.toLowerCase()) found.push(`${brand} ${name} ${hex} is not in §11`);
      }
    }
    for (const name of Object.keys(own)) {
      if (!(name in block)) found.push(`${brand} ${name} is in §11 but not in the block`);
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
    // `--focus` is the brass under the OspreyFlow brand (ADR-132), so the planted value shows twice.
    expect(undeclared(planted, DESIGN)).toEqual(["dark --brass #c08a35", "dark --focus #c08a35"]);
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

// ADR-132: a deployment brand is one block in tokens.css, declared in DESIGN.md §11, and it never
// redefines a data token. Each planted case is the shape the real block has.
describe("deployment brands (DESIGN.md §11)", () => {
  it("the GOV.UK block sets exactly the colours §11 declares for it", () => {
    expect(Object.keys(brandBlocks(TOKENS))).toEqual(["govuk"]);
    expect(Object.keys(contractBrands(DESIGN).govuk ?? {}).length).toBeGreaterThanOrEqual(20);
    expect(brandFindings(TOKENS, DESIGN)).toEqual([]);
  });

  it("finds a brand block that redefines a data token", () => {
    const planted = TOKENS.replace("--brass:#1d70b8;", "--brass:#1d70b8; --ch-ochre:#b34917;");
    expect(brandFindings(planted, DESIGN)).toContain("govuk --ch-ochre redefines a data token");
  });

  it("finds a colour in a brand block that §11 does not declare", () => {
    const planted = TOKENS.replace("--error:#ca3535;", "--error:#ca3536;");
    expect(brandFindings(planted, DESIGN)).toEqual(["govuk --error #ca3536 is not in §11"]);
  });

  it("finds a brand with no section in §11", () => {
    const planted = `${TOKENS}\n[data-brand="other"] {\n  --n0:#ffffff;\n}\n`;
    expect(brandFindings(planted, DESIGN)).toEqual(["other has no section in DESIGN.md §11"]);
  });
});

// ADR-132, the owner's ruling 3: under GOV.UK the welcome, start and Admin pages take GOV.UK's type
// scale, as DESIGN.md §11's table says; the workspace keeps the 13px base.
const GOVUK_PAGES = '[data-brand="govuk"] :is(.welcome, .home, .admin-place)';

/** DESIGN.md §11's type table: token → "size / line-height". */
export function contractGovukType(design: string): Record<string, string> {
  const section = design.slice(design.indexOf("## 11. Deployment brands"));
  const out: Record<string, string> = {};
  for (const [, name, value] of section.matchAll(/^\|\s*`(--fs-\d+)`\s*\|\s*(\d+ \/ \d+)\s*\|/gm)) out[name!] = value!;
  return out;
}

/** The GOV.UK pages' block in tokens.css, as "size / line-height" per token. */
export function tokenGovukType(css: string): Record<string, string> {
  const block = rawBlock(css, GOVUK_PAGES);
  const out: Record<string, string> = {};
  for (const [name, value] of Object.entries(block)) {
    const lh = block[name.replace("--fs-", "--lh-")];
    if (name.startsWith("--fs-")) out[name] = `${value.replace("px", "")} / ${lh?.replace("px", "")}`;
  }
  return out;
}

describe("GOV.UK type on the GOV.UK brand's pages (DESIGN.md §11)", () => {
  it("is the scale §11 declares, 19px body", () => {
    expect(tokenGovukType(TOKENS)).toEqual(contractGovukType(DESIGN));
    expect(tokenGovukType(TOKENS)["--fs-13"]).toBe("19 / 25");
  });

  it("applies to the welcome, start and Admin pages and never to the workspace", () => {
    expect(TOKENS).toContain(`${GOVUK_PAGES} {`);
    for (const workspace of [".app-header", ".network-canvas", ".top-bar", "#main-content"]) {
      expect(GOVUK_PAGES).not.toContain(workspace);
    }
  });

  it("finds a size that differs from §11", () => {
    const planted = TOKENS.replace("--fs-13:19px;", "--fs-13:18px;");
    expect(tokenGovukType(planted)["--fs-13"]).toBe("18 / 25");
    expect(tokenGovukType(planted)).not.toEqual(contractGovukType(DESIGN));
  });
});
