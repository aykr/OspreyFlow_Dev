// The contrast probe's guards, each shown red with that guard removed (the orchestrator's review of
// T3b at 9697ad3, items 1 and 2; the lane-reviewer's pass on d677105). Run through
// `node a11y/plants/run.mjs`, never by the a11y config.
//
// Every covering plant lays something over the right half of Show as BPMN's task label, "If a Person
// meets", whose own surfaces give it 13:1, and makes the covered half a real failure: its pixels are
// read from a screenshot and must give under 4.5:1 there, while the uncovered half's give the words'
// own figure. A probe that wrongly takes the cover as hiding the words judges only the uncovered half
// and passes them silently. Each plant names the outcome of the real probe and of every variant
// (`variants.mjs`): `silentWithout` lists the variants that must pass the words silently (the guard's
// red); every other variant must give the real probe's outcome. A guard the browser already enforces,
// or one stricter than it, cannot be shown red; its plant says why in `unreachable` and shows the real
// probe and the variants agree, or that removing it passes only what is truly seen. The clip check's
// other two narrowings (past an out-of-flow box, and an inline or `display: contents` ancestor) have no
// plant that reaches them: a modal's inertness, the one miss the probe cannot lift, misses every point
// alike, so every narrowing decides only between "a cover" and "hidden at every point", both flagged
// (rules-b's T3b red record).
import { createRequire } from "node:module";
import { join } from "node:path";
import { pathToFileURL } from "node:url";

import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

import { checkUndecidedContrast, type AxeIncomplete } from "../undecidedContrast";
import { VARIANTS } from "./variants.mjs";

const { PNG } = createRequire(import.meta.url)("playwright-core/lib/utilsBundle") as {
  PNG: { sync: { read(b: Buffer): { width: number; height: number; data: Buffer } } };
};

type Probe = typeof checkUndecidedContrast;
type Variant = keyof typeof VARIANTS;
const TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22a", "wcag22aa"];
const WORDS = "If a Person meets";

interface Plant {
  name: string;
  /** Lays the plant in the page; the words' tspan carries id `zz-words`. */
  lay: (page: Page) => Promise<void>;
  real: "flagged" | "passes";
  silentWithout: Variant[];
  unreachable?: string;
  /** A covering plant whose covered half must read under 4.5:1 in pixels (a real failure). */
  fails?: true;
  /** axe is read before the plant (a modal hides the words from it); otherwise after, as at the real call site. */
  axeFirst?: true;
}

/** A fixed element over the right half of the words, with `style` (`{H}` is the cover's height), inside `wrap` when given. */
const halfCover = (page: Page, style: string, wrap = "") =>
  page.evaluate(([style, wrap]) => {
    const r = document.getElementById("zz-words")!.getBoundingClientRect();
    const h = r.height + 12;
    const place = `position:fixed; z-index:1000; left:${r.left + r.width / 2}px; top:${r.top - 6}px; width:${r.width}px; height:${h}px;`;
    const cover = document.createElement("div");
    const own = style.replaceAll("{H}", String(h));
    if (wrap) {
      const outer = document.createElement("div");
      outer.style.cssText = `${place} ${wrap}`;
      cover.style.cssText = `position:absolute; inset:0; ${own}`;
      outer.append(cover);
      document.body.append(outer);
    } else {
      cover.style.cssText = `${place} ${own}`;
      document.body.append(cover);
    }
  }, [style, wrap] as const);

/** A translucent white SVG rect over the right half of the label, in its own drawing: bare, or in a nested <svg>, each with an opaque CSS background. */
const svgHalf = (page: Page, nested: boolean) =>
  page.evaluate((nested) => {
    const words = document.getElementById("zz-words") as unknown as SVGTSpanElement;
    const text = words.closest("text")!;
    const w = words.getBBox();
    const NS = "http://www.w3.org/2000/svg";
    const rect = document.createElementNS(NS, "rect");
    const box = { x: w.x + w.width / 2, y: w.y - 4, width: w.width, height: w.height + 8 };
    rect.setAttribute("fill", "rgba(255, 255, 255, 0.8)");
    if (nested) {
      const inner = document.createElementNS(NS, "svg");
      for (const [k, v] of Object.entries(box)) inner.setAttribute(k, String(v));
      inner.setAttribute("style", "background-color:#fff");
      rect.setAttribute("width", String(box.width));
      rect.setAttribute("height", String(box.height));
      inner.append(rect);
      text.after(inner);
    } else {
      for (const [k, v] of Object.entries(box)) rect.setAttribute(k, String(v));
      rect.setAttribute("style", "background-color:#fff");
      text.after(rect);
    }
  }, nested);

/** A modal dialog away from the words, so the browser's hit test misses them (modal inertness, no attribute to lift). */
const modalWith = (page: Page, change: { parent?: string }) =>
  page.evaluate((change) => {
    const words = document.getElementById("zz-words")!;
    const root = words.closest("svg")!;
    const targets = { parent: root.parentElement };
    for (const [k, css] of Object.entries(change)) (targets[k as keyof typeof targets] as HTMLElement | SVGElement).style.cssText += css;
    const st = document.createElement("style");
    st.textContent = "dialog.zz::backdrop { background: transparent; }";
    document.head.append(st);
    const d = document.createElement("dialog");
    d.className = "zz";
    d.textContent = "A modal far from the words";
    d.style.cssText = "margin:0; left:0; top:0; position:fixed";
    document.body.append(d);
    d.showModal();
  }, change);

const MODAL =
  "the modal makes the hit test miss every point of the words alike (inertness the probe cannot lift), so without the narrowing every point is clipped and the words are unmeasurable (hidden at every point): flagged either way";

const PLANTS: Plant[] = [
  { name: "a cover with its own opacity 0.5", lay: (p) => halfCover(p, "background:#fff; opacity:0.5"), real: "flagged", silentWithout: ["no-opacity-walk"], fails: true },
  { name: "a cover in a wrapper of opacity 0.5", lay: (p) => halfCover(p, "background:#fff", "opacity:0.5"), real: "flagged", silentWithout: ["no-opacity-walk", "own-opacity-only"], fails: true },
  {
    name: "a cover painted to its padding box, a 60% white border over the words",
    lay: (p) => halfCover(p, "background:#fff; background-clip:padding-box; box-sizing:content-box; height:0; border-top:{H}px solid rgba(255, 255, 255, 0.6)"),
    real: "flagged",
    silentWithout: ["no-background-clip"],
    fails: true,
  },
  { name: "a cover with filter: opacity(0.5)", lay: (p) => halfCover(p, "background:#fff; filter:opacity(0.5)"), real: "flagged", silentWithout: ["no-filter"], fails: true },
  { name: "a cover in a wrapper with filter: opacity(0.5)", lay: (p) => halfCover(p, "background:#fff", "filter:opacity(0.5)"), real: "flagged", silentWithout: ["cover-only-walk", "no-filter"], fails: true },
  { name: "a grey cover screened over the words", lay: (p) => halfCover(p, "background:#ccc; mix-blend-mode:screen"), real: "flagged", silentWithout: ["no-blend"], fails: true },
  { name: "a grey cover in a screened wrapper", lay: (p) => halfCover(p, "background:#ccc", "mix-blend-mode:screen"), real: "flagged", silentWithout: ["cover-only-walk", "no-blend"], fails: true },
  {
    name: "a cover with a 50% mask",
    lay: (p) => halfCover(p, "background:#fff; mask-image:linear-gradient(rgba(0,0,0,0.5), rgba(0,0,0,0.5)); -webkit-mask-image:linear-gradient(rgba(0,0,0,0.5), rgba(0,0,0,0.5))"),
    real: "flagged",
    silentWithout: ["no-mask"],
    fails: true,
  },
  {
    name: "a cover in a wrapper with a 50% mask",
    lay: (p) => halfCover(p, "background:#fff", "mask-image:linear-gradient(rgba(0,0,0,0.5), rgba(0,0,0,0.5)); -webkit-mask-image:linear-gradient(rgba(0,0,0,0.5), rgba(0,0,0,0.5))"),
    real: "flagged",
    silentWithout: ["cover-only-walk", "no-mask"],
    fails: true,
  },
  {
    name: "a cover under a 50% mask border (item 2)",
    lay: (p) => halfCover(p, "background:#fff; -webkit-mask-box-image:linear-gradient(rgba(0,0,0,0.5), rgba(0,0,0,0.5))"),
    real: "flagged",
    silentWithout: ["no-mask-border"],
    fails: true,
  },
  { name: "an SVG rect with a CSS background over half the label (item 2)", lay: (p) => svgHalf(p, false), real: "flagged", silentWithout: ["no-svg-exclusion"], fails: true },
  {
    name: "a nested SVG with a CSS background over half the label",
    lay: (p) => svgHalf(p, true),
    real: "flagged",
    silentWithout: [],
    fails: true,
    unreachable:
      "Chromium neither paints a nested <svg>'s CSS background (the covered half reads as the translucent rect alone) nor lists the nested <svg> in its hit test, so opaque() is never asked of it; the outermost-only test stays, the stricter reading",
  },
  {
    name: "a cover clipped away from the words",
    lay: (p) => halfCover(p, "background:#fff; clip-path:inset(0 0 0 100%)"),
    real: "passes",
    silentWithout: [],
    unreachable: "Chromium's hit test respects clip-path: the clipped cover is never found over the words, so hides() is never asked",
  },
  {
    name: "a cover in a wrapper clipped away from the words",
    lay: (p) => halfCover(p, "background:#fff", "clip-path:inset(0 0 0 100%)"),
    real: "passes",
    silentWithout: [],
    unreachable: "as above, for the wrapper's clip",
  },
  {
    name: "an opaque cover over half the words",
    lay: (p) => halfCover(p, "background:#fff"),
    real: "passes",
    silentWithout: [],
    unreachable: "the pixel of slack only widens the box hides() accepts; without it a point the browser hit-tests on the cover's edge stays a cover, flagged, never a silent pass",
  },
  {
    name: "a rounded opaque cover, its 12px corners over the words",
    lay: (p) => halfCover(p, "background:#fff; border-radius:12px"),
    real: "passes",
    silentWithout: [],
    unreachable: "Chromium's hit test respects border-radius: a point outside the curve never finds the cover, so the corner test never decides",
  },
  {
    name: "a rounded opaque cover, its 50% (elliptical) corners over the words",
    lay: (p) => halfCover(p, "background:#fff; border-radius:50%"),
    real: "flagged",
    silentWithout: ["no-corner-test"],
    unreachable:
      "the corner test reads each corner as a circle of the larger radius, stricter than the ellipse Chromium hit-tests, so the real probe's flag is its own false positive and the variant's pass is right: every point the hit test puts on the cover is under opaque white",
  },
  {
    name: "a modal elsewhere, the label's drawing overflowing a 1px box that clips nothing",
    lay: (p) => modalWith(p, { parent: "height:1px; overflow:visible;" }),
    real: "flagged",
    silentWithout: [],
    unreachable: MODAL,
    axeFirst: true,
  },
];

async function open(page: Page) {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/keyboard/rule-standards-harness.html?open=1");
  await page.waitForLoadState("networkidle");
  await page.evaluate(() => document.fonts.ready);
  await page.locator(".show-as-bpmn").first().waitFor();
  await page.evaluate((words) => {
    const t = [...document.querySelectorAll(".show-as-bpmn tspan")].find((e) => e.textContent === words);
    if (!t) throw new Error(`no tspan "${words}"`);
    t.id = "zz-words";
  }, WORDS);
}

/** axe's own result, narrowed to the words' node. */
async function axeOnWords(page: Page): Promise<AxeIncomplete> {
  const results = await new AxeBuilder({ page }).withTags(TAGS).analyze();
  const ours: AxeIncomplete["incomplete"][number]["nodes"] = [];
  for (const rule of results.incomplete.filter((r) => r.id === "color-contrast")) {
    for (const node of rule.nodes) {
      const [only] = node.target;
      if (node.target.length !== 1 || typeof only !== "string") continue;
      if (await page.evaluate((sel) => document.querySelector(sel)?.id === "zz-words", only)) ours.push(node);
    }
  }
  expect(ours, "axe leaves the words' contrast undecided, as at every-harness's own call site").toHaveLength(1);
  return { incomplete: [{ id: "color-contrast", nodes: ours }] };
}

/** The contrast the screenshot's pixels give on each half of the words: the lightest pixel against the darkest. */
async function pixelHalves(page: Page): Promise<[number, number]> {
  const r = await page.evaluate(() => {
    const b = document.getElementById("zz-words")!.getBoundingClientRect();
    return { x: b.left, y: b.top, width: b.width, height: b.height };
  });
  const png = PNG.sync.read(await page.screenshot({ clip: { x: Math.floor(r.x), y: Math.floor(r.y), width: Math.ceil(r.width), height: Math.ceil(r.height) } }));
  const lin = (c: number) => ((c /= 255) <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
  const half = (from: number, to: number) => {
    let [lo, hi] = [Infinity, -Infinity];
    for (let py = 0; py < png.height; py += 1) {
      for (let px = from; px < to; px += 1) {
        const i = (py * png.width + px) * 4;
        const l = 0.2126 * lin(png.data[i] as number) + 0.7152 * lin(png.data[i + 1] as number) + 0.0722 * lin(png.data[i + 2] as number);
        [lo, hi] = [Math.min(lo, l), Math.max(hi, l)];
      }
    }
    return (hi + 0.05) / (lo + 0.05);
  };
  const mid = Math.floor(png.width / 2);
  return [half(0, mid - 2), half(mid + 2, png.width)];
}

const probes: [string, Probe][] = [];
test.beforeAll(async () => {
  const dir = process.env.OSPREY_PLANT_VARIANTS;
  if (!dir) throw new Error("run the plants through node a11y/plants/run.mjs, which writes the variants");
  probes.push(["the probe", checkUndecidedContrast]);
  for (const name of Object.keys(VARIANTS)) {
    const mod = (await import(pathToFileURL(join(dir, `${name}.ts`)).href)) as { checkUndecidedContrast: Probe };
    probes.push([name, mod.checkUndecidedContrast]);
  }
});

for (const plant of PLANTS) {
  test(plant.name, async ({ page }) => {
    await open(page);
    let results = plant.axeFirst ? await axeOnWords(page) : null;
    await plant.lay(page);
    results ??= await axeOnWords(page);
    const lines = [`## ${plant.name}${plant.unreachable ? ` (unreachable: ${plant.unreachable})` : ""}`];
    const wrong: string[] = [];
    if (plant.fails) {
      const [shown, covered] = await pixelHalves(page);
      lines.push(`  pixels: ${shown.toFixed(2)}:1 on the uncovered half, ${covered.toFixed(2)}:1 under the cover`);
      if (!(covered < 4.5)) wrong.push(`the covered half reads ${covered.toFixed(2)}:1 in pixels, no real failure`);
      if (!(shown >= 9)) wrong.push(`the uncovered half reads ${shown.toFixed(2)}:1 in pixels, so the glyphs never reach their ink and the reading proves nothing`);
    }
    for (const [name, probe] of probes) {
      const found = (await probe(page, results, {})).unlisted.filter((u) => u.includes(WORDS));
      const got = found.length ? "flagged" : "passes";
      const want = name === "the probe" ? plant.real : plant.silentWithout.includes(name as Variant) ? "passes" : plant.real;
      lines.push(`  ${got === want ? "  " : "!!"} ${name}: ${got}${found.length ? ` (${found.join(" | ")})` : ""}`);
      if (got !== want) wrong.push(`${name}: ${got}, the plant records ${want}`);
    }
    console.log(lines.join("\n"));
    expect(wrong, plant.name).toEqual([]);
  });
}
