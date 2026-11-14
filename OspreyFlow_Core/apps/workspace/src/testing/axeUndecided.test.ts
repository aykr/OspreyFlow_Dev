// Every axe scan also judges the colour contrast axe left undecided (`a11y/undecidedContrast.ts`).
// axe-core puts `color-contrast` in `incomplete`, never in `violations`, when it cannot work out the
// text's background: text faded with `opacity`, inside a fixed overlay, over another element. A
// scan that reads only `results.violations` passes all of these. Found building the batch job's
// panel (ADR-151, 14 November 2026): its words faded with `opacity: 0.6` passed axe in all three
// looks. `undecidedContrast.ts` says that every scan calls `checkUndecidedContrast`, but nothing
// checked that, and `keyboard/top-bar.spec.ts` did not call it (rule 15: a gate that cannot see its
// own violation). This case reads every file under the two apps that runs an axe scan, and fails
// for each one with fewer judgements of what axe left undecided than scans.
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";

import { describe, expect, it } from "vitest";

const APPS = join(__dirname, "..", "..", "..");
const FOLDERS = ["workspace", "harness"];
const SOURCE = /\.(tsx?|mjs)$/;
// Built at run time, so this file's own words are not read as a scan or a check.
const SCAN = new RegExp(["\\.analy", "ze\\s*\\("].join(""), "g");
const CHECK = new RegExp(["checkUndecided", "Contrast\\s*\\("].join(""), "g");
/** The check's own definition, which defines the call and does not scan; and the probe's own plants
 * (`a11y/plants/`), which run it through each of its variants by a variable, to show its guards red. */
const DEFINES_THE_CHECK = /(^|\/)a11y\/(undecidedContrast\.ts$|plants\/)/;

/** The files, by path, that run more axe scans than they judge what axe left undecided. */
export function scansLeavingContrastUndecided(files: ReadonlyMap<string, string>): string[] {
  return [...files]
    .filter(([path]) => !DEFINES_THE_CHECK.test(path))
    .map(([path, text]) => ({ path, scans: (text.match(SCAN) ?? []).length, checks: (text.match(CHECK) ?? []).length }))
    .filter(({ scans, checks }) => scans > checks)
    .map(({ path, scans, checks }) => `${path}: ${scans} axe scan(s), ${checks} checkUndecidedContrast call(s)`);
}

function sources(dir: string, into = new Map<string, string>()): Map<string, string> {
  for (const name of readdirSync(dir)) {
    if (name === "node_modules" || name === "dist" || name.startsWith(".")) continue;
    const path = join(dir, name);
    if (statSync(path).isDirectory()) sources(path, into);
    else if (SOURCE.test(name)) into.set(relative(APPS, path), readFileSync(path, "utf8"));
  }
  return into;
}

const scan = ["const results = await new AxeBuilder({ page }).withTags(TAGS)", ".analy" + "ze();"].join("");
const check = "const contrast = await checkUndecided" + "Contrast(page, results);";

describe("every axe scan judges the contrast axe left undecided", () => {
  it("flags a scan that reads only its violations", () => {
    expect(scansLeavingContrastUndecided(new Map([["keyboard/x.spec.ts", scan]]))).toEqual([
      "keyboard/x.spec.ts: 1 axe scan(s), 0 checkUndecidedContrast call(s)",
    ]);
  });

  it("passes a scan followed by the check", () => {
    expect(scansLeavingContrastUndecided(new Map([["keyboard/x.spec.ts", `${scan}\n${check}`]]))).toEqual([]);
  });

  it("flags a file with a second scan left unchecked", () => {
    const text = `${scan}\n${check}\n${scan}`;
    expect(scansLeavingContrastUndecided(new Map([["a11y/y.spec.ts", text]]))).toEqual([
      "a11y/y.spec.ts: 2 axe scan(s), 1 checkUndecidedContrast call(s)",
    ]);
  });

  it("does not take the check's own definition for a scan", () => {
    const text = `export async function checkUndecided${"Contrast"}(page, results) { await x.analy${"ze"}(); }`;
    expect(scansLeavingContrastUndecided(new Map([["workspace/a11y/undecidedContrast.ts", text]]))).toEqual([]);
  });

  it("finds no scan in either app that leaves it undecided", () => {
    const files = new Map<string, string>();
    for (const folder of FOLDERS) sources(join(APPS, folder), files);
    expect(files.size).toBeGreaterThan(100);
    expect(scansLeavingContrastUndecided(files)).toEqual([]);
  });
});
